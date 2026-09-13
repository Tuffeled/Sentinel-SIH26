"""Image forensic / tampering analysis (multi-signal).

Design (honest about what blind forensics can and cannot do):

* When an enrolled REFERENCE image exists for the document (the "photo on file"
  for this identifier), a **difference analysis** localises exactly what changed.
  This is the decisive, reliable tamper signal — mirroring real secondary
  inspection against a reference scan.

* Without a reference, the service still computes genuine blind signals
  (Error-Level Analysis, noise inconsistency, copy-move, edges, metadata) and
  renders an ELA visualisation, but treats them as *informational* — blind
  passive forensics is noisy on clean documents, so it is capped and never on
  its own declares a document tampered. (A trained ML tampering model is not
  configured — see the Settings page.)

Findings are always phrased as "potential"/"possible" and carry
score + confidence + regions. ``TamperingDetector.analyze`` is the stable
interface a trained model could later replace.
"""
from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ExifTags

from ..utils import images as imgutil

_EDITOR_SIGNATURES = ("photoshop", "gimp", "affinity", "paint.net", "pixelmator",
                      "lightroom", "snapseed", "facetune", "canva", "imagemagick")

BLIND_CAP = 0.35            # blind (no-reference) forensics cannot exceed this
SUSPICIOUS_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Reference difference analysis (decisive when a reference is available)
# ---------------------------------------------------------------------------
def _align_to(ref: np.ndarray, img: np.ndarray) -> np.ndarray:
    if ref.shape[:2] == img.shape[:2]:
        return ref
    return cv2.resize(ref, (img.shape[1], img.shape[0]))


def _reference_diff(img: np.ndarray, ref: np.ndarray) -> dict:
    ref = _align_to(ref, img)
    ga = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.int16)
    gb = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.int16)
    diff = np.abs(ga - gb).astype(np.uint8)
    _, mask = cv2.threshold(diff, 40, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=1)

    changed_fraction = float((mask > 0).mean())
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 150:
            continue
        boxes.append({"x": int(stats[i, cv2.CC_STAT_LEFT]), "y": int(stats[i, cv2.CC_STAT_TOP]),
                      "w": int(stats[i, cv2.CC_STAT_WIDTH]), "h": int(stats[i, cv2.CC_STAT_HEIGHT]),
                      "area": area})
    boxes = sorted(boxes, key=lambda b: b["area"], reverse=True)[:8]
    score = float(np.clip(changed_fraction / 0.02, 0, 1)) if boxes else 0.0
    return {
        "signal": "reference_diff",
        "label": "Reference Difference",
        "score": round(score, 3),
        "confidence": round(0.75 + 0.2 * score, 3),
        "regions": boxes,
        "description": (
            f"Document differs from the enrolled reference image in "
            f"{len(boxes)} region(s) (~{changed_fraction*100:.1f}% of pixels)."
            if boxes else
            "Document matches the enrolled reference image — no altered regions detected."),
    }


# ---------------------------------------------------------------------------
# Blind signals (informational)
# ---------------------------------------------------------------------------
def _robust_boxes(block_means: np.ndarray, bh: int, bw: int, z_thresh: float = 4.0):
    med = float(np.median(block_means))
    mad = float(np.median(np.abs(block_means - med)))
    if mad < 1e-3:  # near-uniform: avoid divide-by-zero blow-ups
        return 0.0, []
    z = (block_means - med) / (1.4826 * mad)
    ys, xs = np.where(z >= z_thresh)
    boxes = [{"x": int(x * bw), "y": int(y * bh), "w": int(bw), "h": int(bh),
              "z": round(float(z[y, x]), 2)} for y, x in zip(ys.tolist(), xs.tolist())]
    boxes = sorted(boxes, key=lambda b: b["z"], reverse=True)[:6]
    frac = len(boxes) / max(z.size, 1)
    peak = float(np.clip((float(z.max()) - z_thresh) / 8.0, 0, 1))
    return float(np.clip(0.5 * peak + 0.5 * min(frac * 10, 1.0), 0, 1)), boxes


def _ela(bgr: np.ndarray):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "JPEG", quality=90)
    buf.seek(0)
    recompressed = np.array(Image.open(buf).convert("RGB"))
    mag = np.abs(rgb.astype(np.int16) - recompressed.astype(np.int16)).max(axis=2).astype(np.float32)
    h, w = mag.shape
    gy, gx = 24, 24
    bh, bw = max(h // gy, 1), max(w // gx, 1)
    bm = np.array([[mag[i*bh:(i+1)*bh, j*bw:(j+1)*bw].mean() for j in range(gx)]
                   for i in range(gy)], dtype=np.float32)
    score, boxes = _robust_boxes(bm, bh, bw)
    amp = np.clip(mag * 14, 0, 255).astype(np.uint8)
    vis = cv2.applyColorMap(amp, cv2.COLORMAP_JET)
    return {"signal": "ela", "label": "Error Level Analysis", "score": round(score, 3),
            "confidence": round(0.5 + 0.3 * score, 3), "regions": boxes,
            "description": ("Localised error-level variation present — inspect highlighted regions."
                            if score >= 0.5 else
                            "Error levels are broadly consistent across the document.")}, vis


def _noise(bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    residual = gray - cv2.medianBlur(gray.astype(np.uint8), 3).astype(np.float32)
    h, w = residual.shape
    gy, gx = 16, 16
    bh, bw = max(h // gy, 1), max(w // gx, 1)
    stds = np.array([[residual[i*bh:(i+1)*bh, j*bw:(j+1)*bw].std() for j in range(gx)]
                     for i in range(gy)], dtype=np.float32)
    score, boxes = _robust_boxes(stds, bh, bw, z_thresh=4.5)
    return {"signal": "noise", "label": "Noise Inconsistency", "score": round(score, 3),
            "confidence": round(0.5 + 0.3 * score, 3), "regions": boxes,
            "description": ("Local noise levels vary between regions."
                            if score >= 0.5 else "Noise levels are consistent.")}


def _copy_move(bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    roi = gray[0:int(h * 0.84), :]  # exclude MRZ band (repetitive '<')
    orb = cv2.ORB_create(nfeatures=2500)
    kps, desc = orb.detectAndCompute(roi, None)
    boxes: list[dict] = []
    score = 0.0
    if desc is not None and len(kps) > 20:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(desc, desc, k=4)
        clusters: dict[tuple, list] = {}
        for mlist in matches:
            for m in mlist:
                if m.queryIdx == m.trainIdx:
                    continue
                p1 = np.array(kps[m.queryIdx].pt)
                p2 = np.array(kps[m.trainIdx].pt)
                d = p2 - p1
                if m.distance < 22 and np.hypot(*d) > 64:
                    key = (round(d[0] / 16), round(d[1] / 16))
                    clusters.setdefault(key, []).append((p1, p2))
        if clusters:
            best_key = max(clusters, key=lambda k: len(clusters[k]))
            best = clusters[best_key]
            # Require a strong, translation-consistent cluster (real clone).
            if len(best) >= 14:
                pts = np.array([p for pair in best for p in pair])
                x, y, bw2, bh2 = cv2.boundingRect(pts.astype(np.int32))
                boxes.append({"x": int(x), "y": int(y), "w": int(bw2), "h": int(bh2),
                              "z": len(best)})
                score = float(np.clip((len(best) - 14) / 30.0, 0, 1))
    return {"signal": "copy_move", "label": "Copy-Move Duplication", "score": round(score, 3),
            "confidence": round(0.5 + 0.3 * score, 3), "regions": boxes,
            "description": ("A translation-consistent duplicated region was detected."
                            if score >= 0.5 else "No consistent duplicated regions detected.")}


def _edges(bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    edges = cv2.Canny(gray, 80, 200)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=140,
                            minLineLength=int(min(h, w) * 0.4), maxLineGap=4)
    interior, boxes = 0, []
    if lines is not None:
        for l in lines[:200]:
            x1, y1, x2, y2 = l[0]
            if not (abs(y2 - y1) < 3 or abs(x2 - x1) < 3):
                continue
            near_border = (min(x1, x2) < w*0.06 or max(x1, x2) > w*0.94 or
                           min(y1, y2) < h*0.06 or max(y1, y2) > h*0.9)
            if not near_border:
                interior += 1
                boxes.append({"x": int(min(x1, x2)), "y": int(min(y1, y2)),
                              "w": int(abs(x2-x1)) or 2, "h": int(abs(y2-y1)) or 2, "z": 1})
    score = float(np.clip(interior / 8.0, 0, 1))
    return {"signal": "edges", "label": "Boundary Anomaly", "score": round(score, 3),
            "confidence": round(0.4 + 0.2 * score, 3), "regions": boxes[:4],
            "description": ("Unusual interior straight edges detected."
                            if score >= 0.5 else "No suspicious splice boundaries detected.")}


def _metadata(image_path: Path):
    findings, software = [], None
    try:
        with Image.open(image_path) as im:
            exif = getattr(im, "_getexif", lambda: None)() or {}
            tagmap = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()} if exif else {}
            software = tagmap.get("Software")
            info = getattr(im, "info", {}) or {}
            for key in ("Software", "software", "parameters"):
                if isinstance(info.get(key), str):
                    software = software or info[key]
    except Exception:
        pass
    score = 0.0
    if software:
        low = str(software).lower()
        if any(sig in low for sig in _EDITOR_SIGNATURES):
            score = 0.7
            findings.append({"type": "editor_signature",
                             "detail": f"Metadata references editing software: '{software}'."})
        else:
            findings.append({"type": "software_tag", "detail": f"Software tag: '{software}'."})
    return {"signal": "metadata", "label": "Metadata Analysis", "score": round(score, 3),
            "confidence": 0.8 if score else 0.5, "regions": [],
            "description": (findings[0]["detail"] if findings else
                            "No editing-software signatures found in metadata.")}, findings


# ---------------------------------------------------------------------------
class TamperingDetector:
    """Swappable forensic detector interface."""

    def analyze(self, image_path, document_id=None, reference_image_path=None) -> dict:
        path = Path(image_path)
        try:
            bgr = imgutil.load_bgr(path)
        except Exception as exc:
            return {"available": False, "signals": [], "overall_score": 0.0,
                    "suspicious": False, "visualization_path": None, "ela_path": None,
                    "metadata_findings": [], "has_reference": False,
                    "error": f"Forensic analysis unavailable: {exc}"}

        ela_signal, ela_vis = _ela(bgr)
        noise_signal = _noise(bgr)
        copymove_signal = _copy_move(bgr)
        edge_signal = _edges(bgr)
        meta_signal, meta_findings = _metadata(path)

        has_reference = False
        diff_signal = None
        if reference_image_path and Path(reference_image_path).exists():
            try:
                ref = imgutil.load_bgr(reference_image_path)
                diff_signal = _reference_diff(bgr, ref)
                has_reference = True
            except Exception:
                diff_signal = None

        signals = []
        if diff_signal is not None:
            signals.append(diff_signal)
        signals += [ela_signal, noise_signal, copymove_signal, edge_signal, meta_signal]

        if has_reference:
            overall = diff_signal["score"]
        else:
            blind = 0.5 * ela_signal["score"] + 0.3 * copymove_signal["score"] + \
                    0.2 * edge_signal["score"]
            overall = min(blind, BLIND_CAP)
        overall = float(max(overall, meta_signal["score"] if meta_signal["score"] >= 0.6 else 0))
        overall = float(np.clip(overall, 0, 1))
        suspicious = overall >= SUSPICIOUS_THRESHOLD

        # Visualisations
        stem = f"doc{document_id or 'x'}"
        ela_path = imgutil.save_bgr(ela_vis, f"{stem}_ela.png")
        overlay = bgr.copy()
        decisive_regions = (diff_signal["regions"] if has_reference else
                            (ela_signal["regions"] if ela_signal["score"] >= 0.5 else []))
        for r in decisive_regions:
            cv2.rectangle(overlay, (r["x"], r["y"]), (r["x"] + r["w"], r["y"] + r["h"]),
                          (0, 0, 255), 3)
        vis_path = imgutil.save_bgr(overlay, f"{stem}_forensic.png")

        return {"available": True, "signals": signals, "overall_score": round(overall, 3),
                "suspicious": suspicious, "has_reference": has_reference,
                "visualization_path": imgutil.to_relative(vis_path),
                "ela_path": imgutil.to_relative(ela_path),
                "metadata_findings": meta_findings}


tampering_detector = TamperingDetector()


def analyze(image_path, document_id=None, reference_image_path=None) -> dict:
    return tampering_detector.analyze(image_path, document_id, reference_image_path)
