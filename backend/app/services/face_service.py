"""Face detection & verification (OpenCV YuNet + SFace).

Detection : YuNet ONNX face detector (cv2.FaceDetectorYN)
Embedding : SFace ONNX recogniser (cv2.FaceRecognizerSF) -> 128-d descriptor
Matching  : cosine similarity (SFace convention; >= threshold => same person)

This is a genuine modern face-recognition pipeline that is numpy-2 compatible and
runs fully offline once the two model files are present. The service NEVER
fabricates a similarity value — with no engine / no face / no reference it reports
an honest status (UNAVAILABLE / NOT_DETECTED / NO_REFERENCE).

The ``FaceVerifier`` interface is stable so a different model (e.g. ArcFace /
DeepFace / dlib on a compatible stack) can be swapped in later.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from ..config import settings
from ..utils import images as imgutil

# SFace recommended cosine decision threshold.
COSINE_THRESHOLD = float(settings.face_match_threshold or 0.363)


class Status:
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    NOT_DETECTED = "NOT_DETECTED"
    NO_REFERENCE = "NO_REFERENCE"
    UNAVAILABLE = "UNAVAILABLE"


@lru_cache
def _models():
    """Return (detector, recognizer) or (None, None) if unavailable."""
    if settings.face_engine == "off":
        return None, None
    if not (settings.yunet_path.exists() and settings.sface_path.exists()):
        return None, None
    if not hasattr(cv2, "FaceDetectorYN"):
        return None, None
    try:
        det = cv2.FaceDetectorYN.create(str(settings.yunet_path), "", (320, 320), 0.7, 0.3, 5000)
        rec = cv2.FaceRecognizerSF.create(str(settings.sface_path), "")
        return det, rec
    except Exception:
        return None, None


def available() -> bool:
    det, rec = _models()
    return det is not None and rec is not None


def engine_status() -> dict:
    return {
        "selected": settings.face_engine,
        "active": "opencv-yunet-sface" if available() else "none",
        "threshold": COSINE_THRESHOLD,
        "models_present": bool(settings.yunet_path.exists() and settings.sface_path.exists()),
    }


def cosine(a, b) -> float:
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


class FaceVerifier:
    def __init__(self) -> None:
        self.threshold = COSINE_THRESHOLD

    # --- detection + embedding ---
    def detect(self, image_path: str | Path, document_id: int | None = None) -> dict:
        det, rec = _models()
        if det is None:
            return {"available": False, "face_detected": False, "num_faces": 0,
                    "box": None, "crop_path": None, "encoding": None}
        try:
            bgr = imgutil.load_bgr(image_path)
        except Exception:
            return {"available": True, "face_detected": False, "num_faces": 0,
                    "box": None, "crop_path": None, "encoding": None}

        h, w = bgr.shape[:2]
        det.setInputSize((w, h))
        _, faces = det.detect(bgr)
        if faces is None or len(faces) == 0:
            return {"available": True, "face_detected": False, "num_faces": 0,
                    "box": None, "crop_path": None, "encoding": None}

        # Largest face.
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        top = faces[0]
        x, y, fw, fh = (int(max(0, top[0])), int(max(0, top[1])), int(top[2]), int(top[3]))

        try:
            aligned = rec.alignCrop(bgr, np.asarray(top, dtype=np.float32))
            embedding = rec.feature(aligned).ravel().astype(float).tolist()
        except Exception:
            embedding = None

        crop_path = None
        crop = bgr[y:y + fh, x:x + fw]
        if crop.size:
            p = imgutil.save_bgr(crop, f"doc{document_id or 'x'}_face.png")
            crop_path = imgutil.to_relative(p)

        return {"available": True, "face_detected": True, "num_faces": len(faces),
                "box": {"x": x, "y": y, "w": fw, "h": fh}, "crop_path": crop_path,
                "encoding": embedding}

    def verify_encodings(self, enc_a, enc_b) -> dict:
        cos = cosine(enc_a, enc_b)
        similarity = round(max(0.0, min(1.0, (cos + 1) / 2 if cos < 0 else cos)), 4)
        match = cos >= self.threshold
        margin = abs(cos - self.threshold)
        confidence = round(float(0.5 + 0.5 * min(margin / max(self.threshold, 1e-3), 1.0)), 3)
        return {"cosine": round(cos, 4), "similarity": similarity,
                "match": bool(match), "confidence": confidence}

    def analyze(self, document_path: str | Path, document_id: int | None = None,
                reference_path: str | Path | None = None,
                reference_encoding=None, reference_document_id: int | None = None) -> dict:
        if not available():
            return {"engine": "none", "face_detected": False, "num_faces": 0,
                    "face_crop_path": None, "similarity": None, "match": None,
                    "confidence": None, "status": Status.UNAVAILABLE,
                    "reference_document_id": reference_document_id, "encoding": None,
                    "detail": "Face engine not configured — face verification unavailable."}

        det = self.detect(document_path, document_id)
        if not det["face_detected"]:
            return {"engine": "opencv-yunet-sface", "face_detected": False, "num_faces": 0,
                    "face_crop_path": None, "similarity": None, "match": None,
                    "confidence": None, "status": Status.NOT_DETECTED,
                    "reference_document_id": reference_document_id, "encoding": None,
                    "detail": "No face detected in the document image."}

        base = {"engine": "opencv-yunet-sface", "face_detected": True,
                "num_faces": det["num_faces"], "face_crop_path": det["crop_path"],
                "encoding": det["encoding"], "reference_document_id": reference_document_id}

        ref_enc = reference_encoding
        if ref_enc is None and reference_path is not None:
            ref_enc = self.detect(reference_path).get("encoding")

        if ref_enc is None or det["encoding"] is None:
            base.update({"similarity": None, "match": None, "confidence": None,
                         "status": Status.NO_REFERENCE,
                         "detail": "Face detected; no enrolled reference face to compare against."})
            return base

        result = self.verify_encodings(det["encoding"], ref_enc)
        base.update({
            "similarity": result["similarity"], "match": result["match"],
            "confidence": result["confidence"],
            "status": Status.MATCH if result["match"] else Status.NO_MATCH,
            "detail": (f"Face cosine similarity {result['cosine']:.2f} "
                       f"(threshold {self.threshold:.2f}) vs enrolled reference.")})
        return base


face_verifier = FaceVerifier()
