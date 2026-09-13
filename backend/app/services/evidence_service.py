"""Evidence engine.

Turns the structured output of each analysis module into typed evidence items.
Each item carries: type, severity, confidence, risk_contribution, title,
description, source, details. Evidence is descriptive — it explains *what* was
observed; the risk engine decides how it aggregates.
"""
from __future__ import annotations

from ..config import settings
from ..core.constants import (
    EvidenceType,
    Severity,
    WATCHLIST_STATUS_SEVERITY,
)
from ..services.face_service import Status as FaceStatus

W = settings.risk_weights


def _weight(key: str) -> int:
    return int(W.get(key, 0))


def from_classification(classification: dict) -> list[dict]:
    if not classification:
        return []
    conf = classification.get("confidence", 0)
    dtype = classification.get("document_type")
    if dtype == "UNKNOWN" or conf < 0.6:
        return [{
            "type": EvidenceType.CLASSIFICATION_UNCERTAIN,
            "severity": Severity.MEDIUM if dtype == "UNKNOWN" else Severity.LOW,
            "confidence": round(1 - conf, 3),
            "risk_contribution": _weight("CLASSIFICATION_UNCERTAIN"),
            "title": "Document type uncertain",
            "description": f"Classifier returned '{dtype}' at {conf*100:.0f}% confidence.",
            "source": "DOCUMENT_CLASSIFIER",
            "details": {"document_type": dtype, "confidence": conf},
        }]
    return []


def from_ocr(ocr: dict) -> list[dict]:
    if not ocr:
        return []
    conf = ocr.get("confidence", 0)
    if ocr.get("available") and conf and conf < 0.5:
        return [{
            "type": EvidenceType.OCR_LOW_CONFIDENCE,
            "severity": Severity.LOW,
            "confidence": round(1 - conf, 3),
            "risk_contribution": _weight("OCR_LOW_CONFIDENCE"),
            "title": "Low OCR confidence",
            "description": f"Average OCR confidence was {conf*100:.0f}%. Extracted fields may be unreliable.",
            "source": ocr.get("engine", "OCR"),
            "details": {"confidence": conf},
        }]
    return []


def from_mrz(mrz: dict) -> list[dict]:
    if not mrz:
        return []
    if not mrz.get("detected"):
        return [{
            "type": EvidenceType.MRZ_NOT_DETECTED,
            "severity": Severity.LOW,
            "confidence": 0.6,
            "risk_contribution": 0,
            "title": "MRZ not detected",
            "description": "No machine-readable zone was detected — MRZ validation skipped.",
            "source": "MRZ_VALIDATOR",
            "details": {},
        }]
    failed = [k for k, v in (mrz.get("checks") or {}).items() if v == "FAIL"]
    if failed:
        pretty = ", ".join(k.replace("_", " ") for k in failed)
        return [{
            "type": EvidenceType.MRZ_CHECKSUM_FAILURE,
            "severity": Severity.HIGH,
            "confidence": 0.98,
            "risk_contribution": _weight("MRZ_CHECKSUM_FAILURE"),
            "title": "MRZ checksum mismatch",
            "description": f"MRZ check digit(s) failed validation for: {pretty}.",
            "source": "MRZ_VALIDATOR",
            "details": {"failed_checks": failed, "checks": mrz.get("checks")},
        }]
    return []


def from_consistency(consistency: dict) -> list[dict]:
    out = []
    for mm in (consistency or {}).get("mismatches", []):
        sev = mm.get("severity", Severity.MEDIUM)
        out.append({
            "type": EvidenceType.FIELD_MISMATCH,
            "severity": sev,
            "confidence": 0.9,
            "risk_contribution": _weight("FIELD_MISMATCH"),
            "title": f"Field mismatch: {mm.get('label')}",
            "description": (f"{mm.get('label')} differs between the visual zone "
                            f"('{mm.get('ocr')}') and the MRZ ('{mm.get('mrz')}')."),
            "source": "FIELD_CONSISTENCY",
            "details": mm,
        })
    return out


def from_forensic(forensic: dict) -> list[dict]:
    if not forensic or not forensic.get("available"):
        return []
    out = []
    score = forensic.get("overall_score", 0)
    if forensic.get("suspicious") and score > 0:
        strong = [s for s in forensic.get("signals", [])
                  if s.get("signal") in ("ela", "noise", "copy_move", "edges") and s.get("score", 0) >= 0.5]
        names = ", ".join(s["label"] for s in strong) or "multiple signals"
        out.append({
            "type": EvidenceType.FORENSIC_ANOMALY,
            "severity": Severity.HIGH if score >= 0.7 else Severity.MEDIUM,
            "confidence": round(min(0.95, 0.5 + score / 2), 3),
            "risk_contribution": int(round(_weight("FORENSIC_ANOMALY") * min(score, 1.0))),
            "title": "Forensic anomaly detected",
            "description": f"Image forensic signals indicate potential manipulation ({names}).",
            "source": "FORENSIC_ENGINE",
            "details": {"overall_score": score,
                        "signals": [{"signal": s["signal"], "score": s["score"]} for s in strong]},
        })
    # Metadata anomaly is its own evidence type.
    for finding in forensic.get("metadata_findings", []):
        if finding.get("type") == "editor_signature":
            out.append({
                "type": EvidenceType.METADATA_ANOMALY,
                "severity": Severity.MEDIUM,
                "confidence": 0.8,
                "risk_contribution": _weight("METADATA_ANOMALY"),
                "title": "Metadata anomaly",
                "description": finding.get("detail", "Editing-software signature found in metadata."),
                "source": "FORENSIC_ENGINE",
                "details": finding,
            })
    return out


def from_face(face: dict) -> list[dict]:
    if not face:
        return []
    status = face.get("status")
    if status == FaceStatus.NO_MATCH and face.get("similarity") is not None:
        sim = face["similarity"]
        return [{
            "type": EvidenceType.FACE_LOW_SIMILARITY,
            "severity": Severity.HIGH,
            "confidence": face.get("confidence") or 0.7,
            "risk_contribution": _weight("FACE_LOW_SIMILARITY"),
            "title": "Face does not match reference",
            "description": f"Face similarity {sim:.2f} is below the match threshold.",
            "source": "FACE_VERIFIER",
            "details": {"similarity": sim},
        }]
    if status == FaceStatus.NOT_DETECTED:
        return [{
            "type": EvidenceType.FACE_NOT_DETECTED,
            "severity": Severity.LOW,
            "confidence": 0.6,
            "risk_contribution": 0,
            "title": "No face detected",
            "description": "No face was detected in the document photo — face verification skipped.",
            "source": "FACE_VERIFIER",
            "details": {},
        }]
    return []


def from_watchlist(watchlist: dict) -> list[dict]:
    if not watchlist or not watchlist.get("match"):
        return []
    rec = watchlist["record"]
    severity = WATCHLIST_STATUS_SEVERITY.get(rec.get("status"), Severity.HIGH)
    return [{
        "type": EvidenceType.WATCHLIST_MATCH,
        "severity": severity,
        "confidence": 0.99,
        "risk_contribution": _weight("WATCHLIST_MATCH"),
        "title": "Synthetic watchlist match",
        "description": ("Document identifier matched an active synthetic watchlist record "
                        f"(status: {rec.get('status')})."),
        "source": "WATCHLIST",
        "details": rec,
    }]


def from_cross_document(cross: dict) -> list[dict]:
    out = []
    for conflict in (cross or {}).get("conflicts", []):
        out.append({
            "type": EvidenceType.CROSS_DOCUMENT_CONFLICT,
            "severity": conflict.get("severity", Severity.MEDIUM),
            "confidence": 0.85,
            "risk_contribution": _weight("CROSS_DOCUMENT_CONFLICT"),
            "title": f"Cross-document conflict: {conflict.get('attribute')}",
            "description": conflict.get("description", "Attribute conflicts across documents."),
            "source": "IDENTITY_CONSISTENCY",
            "details": conflict,
        })
    return out


def build_all(context: dict) -> list[dict]:
    """Assemble every evidence item from the full analysis context."""
    evidence: list[dict] = []
    evidence += from_classification(context.get("classification"))
    evidence += from_ocr(context.get("ocr"))
    evidence += from_mrz(context.get("mrz"))
    evidence += from_consistency(context.get("consistency"))
    evidence += from_forensic(context.get("forensic"))
    evidence += from_face(context.get("face"))
    evidence += from_watchlist(context.get("watchlist"))
    evidence += from_cross_document(context.get("cross_document"))
    return evidence
