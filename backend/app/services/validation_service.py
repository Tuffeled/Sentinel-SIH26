"""Field consistency: compare OCR (visual inspection zone) vs MRZ fields.

Only fields present in *both* sources are compared, so a missing OCR read never
fabricates a mismatch. MRZ is treated as the authoritative reference.
"""
from __future__ import annotations

from ..utils.text import normalize_date, normalize_doc_number, normalize_name, similarity

MATCH = "MATCH"
MISMATCH = "MISMATCH"
NA = "N/A"

# field key -> (label, comparison type, severity-if-mismatch)
_FIELDS = [
    ("surname", "Surname", "name", "HIGH"),
    ("given_names", "Given names", "name", "MEDIUM"),
    ("document_number", "Document number", "docnum", "HIGH"),
    ("dob", "Date of birth", "date", "HIGH"),
    ("expiry_date", "Date of expiry", "date", "MEDIUM"),
    ("nationality", "Nationality", "code", "MEDIUM"),
    ("sex", "Sex", "code", "LOW"),
]


def _compare(kind: str, ocr_val: str, mrz_val: str) -> str:
    if kind == "name":
        return MATCH if similarity(ocr_val, mrz_val) >= 0.8 else MISMATCH
    if kind == "date":
        return MATCH if normalize_date(ocr_val) == normalize_date(mrz_val) else MISMATCH
    if kind == "docnum":
        a, b = normalize_doc_number(ocr_val), normalize_doc_number(mrz_val)
        if a == b:
            return MATCH
        # tolerate a single OCR character error on long numbers
        if len(a) == len(b) and len(a) >= 7:
            diff = sum(1 for x, y in zip(a, b) if x != y)
            return MATCH if diff <= 1 else MISMATCH
        return MISMATCH
    # code (nationality / sex)
    return MATCH if (ocr_val or "").strip().upper() == (mrz_val or "").strip().upper() else MISMATCH


def check_consistency(ocr_fields: dict, mrz_fields: dict) -> dict:
    comparisons = []
    mismatches = []
    compared = 0

    for key, label, kind, severity in _FIELDS:
        ocr_val = (ocr_fields or {}).get(key, "")
        mrz_val = (mrz_fields or {}).get(key, "")
        if not ocr_val or not mrz_val:
            comparisons.append({
                "field": key, "label": label,
                "ocr": ocr_val or None, "mrz": mrz_val or None, "result": NA,
            })
            continue
        compared += 1
        result = _compare(kind, str(ocr_val), str(mrz_val))
        entry = {
            "field": key, "label": label,
            "ocr": ocr_val, "mrz": mrz_val, "result": result,
        }
        if result == MISMATCH:
            entry["severity"] = severity
            mismatches.append(entry)
        comparisons.append(entry)

    if compared == 0:
        overall = "INSUFFICIENT_DATA"
    elif mismatches:
        overall = "MISMATCH"
    else:
        overall = "CONSISTENT"

    return {
        "comparisons": comparisons,
        "mismatches": mismatches,
        "compared_count": compared,
        "overall": overall,
    }
