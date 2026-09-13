"""Dataset evaluation.

Runs the real detection modules over the synthetic paired dataset (which carries
GENUINE/ALTERED ground truth) and computes confusion-matrix + metrics. Nothing is
hard-coded — every number comes from executing the pipeline. Failures (a missed
altered document) are reported honestly as false negatives.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..core.constants import GroundTruth
from ..core.security import new_uuid
from . import (
    document_classifier as classifier_mod,
    evidence_service,
    forensic_service,
    mrz_service,
    ocr_service,
    risk_service,
    validation_service,
    watchlist_service,
)

_classifier = classifier_mod.document_classifier

# Predicted ALTERED when the risk score reaches this (MEDIUM band and above).
DECISION_THRESHOLD = 25.0

# In-process registry of evaluation runs (also persisted to disk).
_RUNS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------
def _infer_ground_truth(name: str) -> str | None:
    low = name.lower()
    if "genuine" in low:
        return GroundTruth.GENUINE
    if "altered" in low or "tampered" in low or "fake" in low:
        return GroundTruth.ALTERED
    return None


def load_dataset() -> list[dict]:
    """Return [{file, path, ground_truth, identity, type}] from manifest or names."""
    manifest = settings.synthetic_dir / "manifest.json"
    items: list[dict] = []
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for d in data.get("documents", []):
                path = settings.synthetic_dir / d["file"]
                if path.exists() and d.get("ground_truth"):
                    items.append({
                        "file": d["file"], "path": path,
                        "ground_truth": d["ground_truth"],
                        "identity": d.get("identity"), "type": d.get("type", "PASSPORT"),
                    })
            if items:
                return items
        except Exception:
            pass
    # Fallback: scan directory.
    for path in sorted(settings.synthetic_dir.glob("*")):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        gt = _infer_ground_truth(path.name)
        if gt:
            m = re.search(r"(\d{3,})", path.stem)
            items.append({"file": path.name, "path": path, "ground_truth": gt,
                          "identity": m.group(1) if m else None, "type": "PASSPORT"})
    return items


# ---------------------------------------------------------------------------
# Single-document evaluation (runs modules directly, no dashboard pollution)
# ---------------------------------------------------------------------------
def _evaluate_one(db: Session, path: Path) -> dict:
    ocr = ocr_service.run_ocr(path)
    mrz = mrz_service.detect_and_parse(path, ocr.get("raw_text"))
    classification = _classifier.classify(ocr.get("raw_text", ""), mrz)
    ocr_fields = (ocr_service.extract_fields(ocr.get("raw_text", ""), image_path=path)
                  if ocr.get("available") else {})
    consistency = validation_service.check_consistency(ocr_fields, mrz.get("fields", {}))
    forensic = forensic_service.analyze(path, None)

    number = (mrz.get("fields", {}) or {}).get("document_number") or ocr_fields.get("document_number")
    rec = watchlist_service.lookup(db, number)
    watchlist = {"match": bool(rec), "record": (
        {"id": rec.id, "document_number": rec.document_number, "status": rec.status,
         "reason": rec.reason, "source": rec.source} if rec else None)}

    context = {
        "classification": classification, "ocr": ocr, "mrz": mrz,
        "consistency": consistency, "forensic": forensic, "watchlist": watchlist,
    }
    evidence = evidence_service.build_all(context)
    risk = risk_service.calculate(evidence)

    detectors = {
        "MRZ": bool(mrz.get("detected") and not mrz.get("valid")),
        "Forensics": bool(forensic.get("suspicious")),
        "Field Consistency": consistency.get("overall") == "MISMATCH",
        "Watchlist": watchlist["match"],
        "Metadata": any(f.get("type") == "editor_signature"
                        for f in forensic.get("metadata_findings", [])),
    }
    return {"risk": risk, "detectors": detectors,
            "predicted": GroundTruth.ALTERED if risk["score"] >= DECISION_THRESHOLD
            else GroundTruth.GENUINE}


def _metrics(tp: int, tn: int, fp: int, fn: int) -> dict:
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    return {
        "accuracy": round(accuracy, 4), "precision": round(precision, 4),
        "recall": round(recall, 4), "f1": round(f1, 4),
        "false_positive_rate": round(fpr, 4), "false_negative_rate": round(fnr, 4),
    }


def run_evaluation(db: Session) -> dict:
    dataset = load_dataset()
    run_id = new_uuid()[:12]
    if not dataset:
        result = {
            "id": run_id, "created_at": datetime.utcnow().isoformat() + "Z",
            "documents_tested": 0, "genuine": 0, "altered": 0,
            "error": "No labelled synthetic dataset found in data/synthetic/. "
                     "Run generate_synthetic_docs.py first.",
            "metrics": _metrics(0, 0, 0, 0),
            "confusion_matrix": {"tp": 0, "tn": 0, "fp": 0, "fn": 0},
            "detector_breakdown": [], "samples": [],
        }
        _RUNS[run_id] = result
        return result

    tp = tn = fp = fn = 0
    det_stats: dict[str, dict] = {}
    samples = []
    genuine = altered = 0

    for item in dataset:
        truth = item["ground_truth"]
        genuine += truth == GroundTruth.GENUINE
        altered += truth == GroundTruth.ALTERED
        out = _evaluate_one(db, item["path"])
        pred = out["predicted"]

        if truth == GroundTruth.ALTERED and pred == GroundTruth.ALTERED:
            tp += 1; outcome = "TP"
        elif truth == GroundTruth.GENUINE and pred == GroundTruth.GENUINE:
            tn += 1; outcome = "TN"
        elif truth == GroundTruth.GENUINE and pred == GroundTruth.ALTERED:
            fp += 1; outcome = "FP"
        else:
            fn += 1; outcome = "FN"

        for name, fired in out["detectors"].items():
            st = det_stats.setdefault(name, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
            if truth == GroundTruth.ALTERED:
                st["tp" if fired else "fn"] += 1
            else:
                st["fp" if fired else "tn"] += 1

        samples.append({
            "file": item["file"], "identity": item.get("identity"),
            "ground_truth": truth, "predicted": pred, "outcome": outcome,
            "risk_score": out["risk"]["score"], "risk_level": out["risk"]["level"],
            "detectors": [k for k, v in out["detectors"].items() if v],
        })

    detector_breakdown = []
    for name, st in sorted(det_stats.items()):
        m = _metrics(st["tp"], st["tn"], st["fp"], st["fn"])
        detector_breakdown.append({
            "detector": name, **st,
            "recall": m["recall"], "precision": m["precision"],
            "false_positive_rate": m["false_positive_rate"],
        })

    result = {
        "id": run_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "documents_tested": len(dataset),
        "genuine": genuine, "altered": altered,
        "decision_threshold": DECISION_THRESHOLD,
        "metrics": _metrics(tp, tn, fp, fn),
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "detector_breakdown": detector_breakdown,
        "samples": samples,
    }
    _RUNS[run_id] = result
    try:
        (settings.reports_dir / "evaluation_latest.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
    except Exception:
        pass
    return result


def get_run(run_id: str) -> dict | None:
    if run_id in _RUNS:
        return _RUNS[run_id]
    latest = settings.reports_dir / "evaluation_latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            if data.get("id") == run_id:
                return data
        except Exception:
            pass
    return None


def latest_run() -> dict | None:
    if _RUNS:
        return max(_RUNS.values(), key=lambda r: r["created_at"])
    latest = settings.reports_dir / "evaluation_latest.json"
    if latest.exists():
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None
