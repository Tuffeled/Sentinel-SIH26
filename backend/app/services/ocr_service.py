"""OCR service.

A pluggable engine abstraction:

* TesseractEngine  — reliable default (requires the Tesseract binary)
* PaddleEngine     — used automatically if paddleocr is importable

The service returns the raw text, an average confidence and a first pass of
structured fields parsed from the visual-inspection zone. MRZ-derived fields are
merged later by the analysis orchestrator (MRZ is authoritative).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from ..config import settings
from ..utils import images as imgutil
from ..utils.text import clean_text, normalize_date

# ---------------------------------------------------------------------------
# Engine setup
# ---------------------------------------------------------------------------
_TESSERACT_AVAILABLE = False
try:
    import pytesseract

    if settings.tesseract_cmd and Path(settings.tesseract_cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    # Probe once.
    pytesseract.get_tesseract_version()
    _TESSERACT_AVAILABLE = True
except Exception:
    _TESSERACT_AVAILABLE = False


@lru_cache
def _paddle():
    """Lazily construct a PaddleOCR instance (None if unavailable)."""
    try:
        from paddleocr import PaddleOCR

        return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    except Exception:
        return None


def available_engine() -> str:
    pref = settings.ocr_engine
    if pref == "paddle":
        return "paddle" if _paddle() is not None else ("tesseract" if _TESSERACT_AVAILABLE else "none")
    if pref == "tesseract":
        return "tesseract" if _TESSERACT_AVAILABLE else "none"
    # auto
    if _paddle() is not None:
        return "paddle"
    if _TESSERACT_AVAILABLE:
        return "tesseract"
    return "none"


def engine_status() -> dict:
    return {
        "selected": settings.ocr_engine,
        "active": available_engine(),
        "tesseract_available": _TESSERACT_AVAILABLE,
        "paddle_available": _paddle() is not None,
    }


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------
def _preprocess(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if w < 1400:
        scale = 1400 / max(w, 1)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 5, 40, 40)
    return gray


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------
def _tesseract_ocr(bgr: np.ndarray) -> dict:
    proc = _preprocess(bgr)
    config = "--oem 3 --psm 3"
    text = pytesseract.image_to_string(proc, config=config)
    try:
        data = pytesseract.image_to_data(
            proc, config=config, output_type=pytesseract.Output.DICT
        )
        confs = [int(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
        confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    except Exception:
        confidence = 0.0
    return {"engine": "tesseract", "raw_text": clean_text(text), "confidence": round(confidence, 3)}


def _paddle_ocr(bgr: np.ndarray) -> dict:
    ocr = _paddle()
    result = ocr.ocr(bgr, cls=True)
    lines, confs = [], []
    for block in result or []:
        for entry in block or []:
            try:
                txt, conf = entry[1][0], float(entry[1][1])
                lines.append(txt)
                confs.append(conf)
            except Exception:
                continue
    confidence = (sum(confs) / len(confs)) if confs else 0.0
    return {
        "engine": "paddle",
        "raw_text": clean_text("\n".join(lines)),
        "confidence": round(confidence, 3),
    }


def run_ocr(image_path: str | Path) -> dict:
    """Run OCR on a document image. Never fabricates text.

    Returns {engine, raw_text, confidence, available}.
    """
    eng = available_engine()
    if eng == "none":
        return {
            "engine": "none",
            "raw_text": "",
            "confidence": 0.0,
            "available": False,
            "error": "No OCR engine available (install Tesseract or PaddleOCR).",
        }
    try:
        bgr = imgutil.load_bgr(image_path)
    except Exception as exc:
        return {"engine": eng, "raw_text": "", "confidence": 0.0, "available": True,
                "error": f"Image could not be decoded: {exc}"}

    if eng == "paddle":
        out = _paddle_ocr(bgr)
    else:
        out = _tesseract_ocr(bgr)
    out["available"] = True
    return out


# ---------------------------------------------------------------------------
# Structured field extraction from the visual-inspection zone
# ---------------------------------------------------------------------------
_LABELS = {
    "surname": r"(?:surname|nom|last\s*name)",
    "given_names": r"(?:given\s*names?|pr[eé]noms?|first\s*name)",
    "document_number": r"(?:passport\s*n[o0]\.?|document\s*n[o0]\.?|card\s*n[o0]\.?|id\s*n[o0]\.?|no\.?)",
    "nationality": r"(?:nationality|nationalit[eé])",
    "dob": r"(?:date\s*of\s*birth|birth|d\.?o\.?b\.?)",
    "sex": r"(?:sex|sexe|gender)",
    "place_of_birth": r"(?:place\s*of\s*birth|lieu)",
    "issue_date": r"(?:date\s*of\s*issue|issue|d[eé]livrance)",
    "expiry_date": r"(?:date\s*of\s*expiry|expiry|expiration|expir)",
    "country_code": r"(?:country\s*code|code)",
}

_VALUE = r"[^\n:]{0,40}"


def _find(label_regex: str, text: str) -> str:
    pattern = re.compile(label_regex + r"\s*[:.\-]?\s*(" + _VALUE + r")", re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return ""
    val = clean_text(m.group(1))
    # Trim trailing label words that leak in.
    val = re.split(r"\s{2,}", val)[0]
    return val.strip(" .:-/")


# Anchor tokens that identify each field label row (matched case-insensitively).
# Restricted to the fields that positional OCR reads reliably on the VIZ; the MRZ
# remains the authoritative source and covers the rest.
_ANCHORS = {
    "surname": r"^SURNAME$|^NOM$",
    "given_names": r"^GIVEN$|GIVEN\s*NAMES",
    "document_number": r"PASSPORT\s*NO|DOCUMENT\s*NO|CARD\s*NO",
    "nationality": r"^NATIONALITY$",
    "dob": r"DATE\s*OF\s*BIRTH",
}


def _words_and_lines(data: dict):
    """Return (words, lines). words: [{text,x,y,w,h,bottom}]; lines group words."""
    groups: dict[tuple, list[int]] = {}
    words = []
    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        try:
            conf = int(float(data["conf"][i]))
        except (TypeError, ValueError):
            conf = -1
        if not txt or conf < 0:
            continue
        w = {"text": txt, "x": data["left"][i], "y": data["top"][i],
             "w": data["width"][i], "h": data["height"][i],
             "bottom": data["top"][i] + data["height"][i]}
        words.append(w)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append(w)
    lines = []
    for ws in groups.values():
        ws.sort(key=lambda w: w["x"])
        lines.append({"text": " ".join(w["text"] for w in ws),
                      "x": min(w["x"] for w in ws), "y": min(w["y"] for w in ws),
                      "bottom": max(w["bottom"] for w in ws)})
    return words, sorted(lines, key=lambda l: (l["y"], l["x"]))


def extract_fields_positional(image_path: str | Path) -> dict:
    """Positional extraction: read the value words directly below each label,
    bounded to the label's column. Robust to multi-column layouts."""
    if available_engine() != "tesseract":
        return {}
    try:
        bgr = imgutil.load_bgr(image_path)
    except Exception:
        return {}
    proc = _preprocess(bgr)
    try:
        data = pytesseract.image_to_data(proc, config="--oem 3 --psm 3",
                                         output_type=pytesseract.Output.DICT)
    except Exception:
        return {}
    words, lines = _words_and_lines(data)
    fields: dict[str, str] = {}
    for key, pattern in _ANCHORS.items():
        label = next((L for L in lines if re.search(pattern, L["text"], re.IGNORECASE)), None)
        if not label:
            continue
        # Collect value words just below the label, within the label's column.
        value_words = [
            w for w in words
            if label["bottom"] - 4 <= w["y"] <= label["bottom"] + 44
            and (label["x"] - 30) <= w["x"] <= (label["x"] + 320)
        ]
        if value_words:
            value_words.sort(key=lambda w: w["x"])
            fields[key] = clean_text(" ".join(w["text"] for w in value_words))
    return _normalize_fields(fields)


def _normalize_fields(fields: dict) -> dict:
    fields = dict(fields)
    for dkey in ("dob", "issue_date", "expiry_date"):
        if fields.get(dkey):
            fields[dkey] = normalize_date(fields[dkey])
    if fields.get("sex"):
        m = re.search(r"\b([MF])\b", fields["sex"].upper())
        fields["sex"] = m.group(1) if m else fields["sex"].upper()[:1]
    if fields.get("nationality"):
        m = re.search(r"[A-Z]{3}", fields["nationality"].upper())
        if m:
            fields["nationality"] = m.group(0)
    if fields.get("document_number"):
        fields["document_number"] = re.sub(r"[^A-Za-z0-9]", "", fields["document_number"]).upper()
    for nkey in ("surname", "given_names"):
        if fields.get(nkey):
            fields[nkey] = re.sub(r"[^A-Za-z' -]", "", fields[nkey]).upper().strip()
    if fields.get("surname") or fields.get("given_names"):
        fields["full_name"] = " ".join(
            p for p in [fields.get("given_names", ""), fields.get("surname", "")] if p).strip()
    return fields


def extract_fields(raw_text: str, image_path: str | Path | None = None) -> dict:
    """Extract VIZ fields. Prefers positional extraction (needs the image);
    falls back to flat-text regex parsing."""
    if image_path is not None:
        positional = extract_fields_positional(image_path)
        if positional:
            return positional
    text = raw_text or ""
    fields: dict[str, str] = {}
    for key, label in _LABELS.items():
        val = _find(label, text)
        if val:
            fields[key] = val

    # Normalise a few fields.
    for dkey in ("dob", "issue_date", "expiry_date"):
        if fields.get(dkey):
            fields[dkey] = normalize_date(fields[dkey])
    if fields.get("sex"):
        s = fields["sex"].upper()
        m = re.search(r"\b([MF])\b", s)
        fields["sex"] = m.group(1) if m else s[:1]
    if fields.get("nationality"):
        m = re.search(r"[A-Z]{3}", fields["nationality"].upper())
        if m:
            fields["nationality"] = m.group(0)
    if fields.get("surname"):
        fields["surname"] = fields["surname"].upper()
    if fields.get("given_names"):
        fields["given_names"] = fields["given_names"].upper()

    # Compose a full name when possible.
    if fields.get("surname") or fields.get("given_names"):
        fields["full_name"] = " ".join(
            p for p in [fields.get("given_names", ""), fields.get("surname", "")] if p
        ).strip()
    return fields
