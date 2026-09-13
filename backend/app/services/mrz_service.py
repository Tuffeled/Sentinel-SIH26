"""MRZ detection, parsing and ICAO 9303 checksum validation.

Supports TD3 (passport, 2x44), TD1 (ID card, 3x30) and TD2 (2x36). All checksum
maths is deterministic pure-Python. When a checksum fails we report *which* field
failed rather than a blanket "MRZ INVALID".
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import cv2

from ..config import settings
from ..utils import images as imgutil

try:
    import pytesseract

    if settings.tesseract_cmd and Path(settings.tesseract_cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    _HAS_TESS = True
except Exception:
    _HAS_TESS = False

_MRZ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
PASS = "PASS"
FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Check-digit maths
# ---------------------------------------------------------------------------
def _char_value(ch: str) -> int:
    if ch.isdigit():
        return int(ch)
    if "A" <= ch <= "Z":
        return ord(ch) - 55  # A=10 .. Z=35
    return 0  # '<' and anything else


def check_digit(data: str) -> int:
    weights = [7, 3, 1]
    total = 0
    for i, ch in enumerate(data):
        total += _char_value(ch) * weights[i % 3]
    return total % 10


def _verify(field: str, expected: str) -> str:
    if expected in ("", "<"):
        return "N/A"
    if not expected.isdigit():
        return FAIL
    return PASS if check_digit(field) == int(expected) else FAIL


def _yymmdd_to_iso(val: str, *, is_expiry: bool = False) -> str:
    if not re.fullmatch(r"\d{6}", val or ""):
        return val or ""
    yy, mm, dd = int(val[0:2]), val[2:4], val[4:6]
    pivot = (datetime.now().year % 100) + 10
    century = 2000 if (is_expiry or yy <= pivot) else 1900
    return f"{century + yy:04d}-{mm}-{dd}"


def _clean_name(part: str) -> str:
    return re.sub(r"\s+", " ", part.replace("<", " ")).strip()


# Alpha MRZ fields (country, nationality, names) occasionally OCR a digit for a
# letter; correct the common confusions. Numeric fields keep their raw OCR so the
# checksum genuinely validates them.
_ALPHA_FIX = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"})


def _alpha(s: str) -> str:
    return s.translate(_ALPHA_FIX)


# ---------------------------------------------------------------------------
# Parsers (each returns fields + per-field checks + validity)
# ---------------------------------------------------------------------------
def parse_td3(lines: list[str]) -> dict:
    l1, l2 = lines[0].ljust(44, "<")[:44], lines[1].ljust(44, "<")[:44]
    names = l1[5:44]
    surname, _, given = names.partition("<<")
    doc_number = l2[0:9].replace("<", "")
    checks = {
        "document_number": _verify(l2[0:9], l2[9]),
        "date_of_birth": _verify(l2[13:19], l2[19]),
        "expiry_date": _verify(l2[21:27], l2[27]),
    }
    composite_src = l2[0:10] + l2[13:20] + l2[21:43]
    checks["composite"] = _verify(composite_src, l2[43])
    fields = {
        "document_type": l1[0].replace("<", ""),
        "issuing_country": _alpha(l1[2:5].replace("<", "")),
        "surname": _clean_name(_alpha(surname)).upper(),
        "given_names": _clean_name(_alpha(given)).upper(),
        "document_number": doc_number,
        "nationality": _alpha(l2[10:13].replace("<", "")),
        "dob": _yymmdd_to_iso(l2[13:19]),
        "sex": l2[20].replace("<", ""),
        "expiry_date": _yymmdd_to_iso(l2[21:27], is_expiry=True),
        "personal_number": l2[28:42].replace("<", ""),
    }
    fields["full_name"] = f"{fields['given_names']} {fields['surname']}".strip()
    return {"mrz_type": "TD3", "fields": fields, "checks": checks}


def parse_td2(lines: list[str]) -> dict:
    l1, l2 = lines[0].ljust(36, "<")[:36], lines[1].ljust(36, "<")[:36]
    surname, _, given = l1[5:36].partition("<<")
    checks = {
        "document_number": _verify(l2[0:9], l2[9]),
        "date_of_birth": _verify(l2[13:19], l2[19]),
        "expiry_date": _verify(l2[21:27], l2[27]),
    }
    composite_src = l2[0:10] + l2[13:20] + l2[21:35]
    checks["composite"] = _verify(composite_src, l2[35])
    fields = {
        "document_type": l1[0].replace("<", ""),
        "issuing_country": _alpha(l1[2:5].replace("<", "")),
        "surname": _clean_name(_alpha(surname)).upper(),
        "given_names": _clean_name(_alpha(given)).upper(),
        "document_number": l2[0:9].replace("<", ""),
        "nationality": _alpha(l2[10:13].replace("<", "")),
        "dob": _yymmdd_to_iso(l2[13:19]),
        "sex": l2[20].replace("<", ""),
        "expiry_date": _yymmdd_to_iso(l2[21:27], is_expiry=True),
    }
    fields["full_name"] = f"{fields['given_names']} {fields['surname']}".strip()
    return {"mrz_type": "TD2", "fields": fields, "checks": checks}


def parse_td1(lines: list[str]) -> dict:
    l1 = lines[0].ljust(30, "<")[:30]
    l2 = lines[1].ljust(30, "<")[:30]
    l3 = lines[2].ljust(30, "<")[:30]
    surname, _, given = l3.partition("<<")
    checks = {
        "document_number": _verify(l1[5:14], l1[14]),
        "date_of_birth": _verify(l2[0:6], l2[6]),
        "expiry_date": _verify(l2[8:14], l2[14]),
    }
    composite_src = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29]
    checks["composite"] = _verify(composite_src, l2[29])
    fields = {
        "document_type": l1[0:2].replace("<", ""),
        "issuing_country": _alpha(l1[2:5].replace("<", "")),
        "document_number": l1[5:14].replace("<", ""),
        "dob": _yymmdd_to_iso(l2[0:6]),
        "sex": l2[7].replace("<", ""),
        "expiry_date": _yymmdd_to_iso(l2[8:14], is_expiry=True),
        "nationality": _alpha(l2[15:18].replace("<", "")),
        "surname": _clean_name(_alpha(surname)).upper(),
        "given_names": _clean_name(_alpha(given)).upper(),
    }
    fields["full_name"] = f"{fields['given_names']} {fields['surname']}".strip()
    return {"mrz_type": "TD1", "fields": fields, "checks": checks}


# ---------------------------------------------------------------------------
# MRZ line detection from an image / text
# ---------------------------------------------------------------------------
def _candidate_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", "", raw.upper())
        line = re.sub(rf"[^{re.escape(_MRZ_CHARS)}]", "", line)
        if len(line) < 20:
            continue
        ratio = sum(1 for c in line if c in _MRZ_CHARS) / len(line)
        if ratio > 0.9 and ("<" in line or sum(c.isdigit() for c in line) >= 5):
            out.append(line)
    return out


def _ocr_mrz_zone(image_path: str | Path) -> list[str]:
    if not _HAS_TESS:
        return []
    try:
        bgr = imgutil.load_bgr(image_path)
    except Exception:
        return []
    h, w = bgr.shape[:2]
    crop = bgr[int(h * 0.72):h, 0:w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] < 1000:
        scale = 1000 / gray.shape[1]
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cfg = f"--oem 3 --psm 6 -c tessedit_char_whitelist={_MRZ_CHARS}"
    try:
        text = pytesseract.image_to_string(thr, config=cfg)
    except Exception:
        return []
    return _candidate_lines(text)


def _select_mrz(lines: list[str]) -> tuple[str, list[str]] | None:
    """Pick the most plausible MRZ block + type from candidate lines.

    Tolerates a truncated names line (line 1), which frequently loses its
    trailing filler '<' characters during OCR — it is padded to full width.
    """
    # TD3: a ~44-char data line (line 2) preceded by the names line (line 1).
    td3 = [l for l in lines if 40 <= len(l) <= 46]
    if td3:
        line2 = td3[-1]
        idx = lines.index(line2)
        line1 = lines[idx - 1] if idx > 0 else ""
        return "TD3", [line1.ljust(44, "<")[:44], line2.ljust(44, "<")[:44]]
    # TD1: three lines ~30
    td1 = [l for l in lines if 26 <= len(l) <= 32]
    if len(td1) >= 3:
        return "TD1", [l.ljust(30, "<")[:30] for l in td1[-3:]]
    # TD2: two lines ~36
    td2 = [l for l in lines if 33 <= len(l) <= 38]
    if len(td2) >= 2:
        return "TD2", [l.ljust(36, "<")[:36] for l in td2[-2:]]
    return None


def detect_and_parse(image_path: str | Path, ocr_raw_text: str | None = None) -> dict:
    """Detect + parse + validate the MRZ. Never claims validity it didn't check.

    Returns a dict matching the MrzResult model fields.
    """
    candidates = _ocr_mrz_zone(image_path)
    if not candidates and ocr_raw_text:
        candidates = _candidate_lines(ocr_raw_text)

    selected = _select_mrz(candidates)
    if not selected:
        return {
            "detected": False,
            "mrz_type": None,
            "raw_lines": [],
            "fields": {},
            "checks": {},
            "valid": False,
            "message": "MRZ not detected — MRZ validation skipped.",
        }

    mrz_type, lines = selected
    try:
        if mrz_type == "TD3":
            parsed = parse_td3(lines)
        elif mrz_type == "TD1":
            parsed = parse_td1(lines)
        else:
            parsed = parse_td2(lines)
    except Exception as exc:  # malformed MRZ
        return {
            "detected": True,
            "mrz_type": mrz_type,
            "raw_lines": lines,
            "fields": {},
            "checks": {},
            "valid": False,
            "message": f"MRZ detected but could not be parsed: {exc}",
        }

    checks = parsed["checks"]
    real_checks = [v for v in checks.values() if v in (PASS, FAIL)]
    valid = bool(real_checks) and all(v == PASS for v in real_checks)
    return {
        "detected": True,
        "mrz_type": parsed["mrz_type"],
        "raw_lines": lines,
        "fields": parsed["fields"],
        "checks": checks,
        "valid": valid,
        "message": "MRZ validated." if valid else "One or more MRZ checksums failed.",
    }
