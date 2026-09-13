"""Text normalisation & comparison helpers used by extraction / consistency."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    # Drop control characters, normalise unicode & whitespace.
    value = unicodedata.normalize("NFKC", value)
    value = "".join(ch for ch in value if ch == "\n" or ch >= " ")
    return value.strip()


def normalize_doc_number(value: str | None) -> str:
    """Uppercase, keep only [A-Z0-9]. e.g. 'P123 456 789' -> 'P123456789'."""
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^A-Za-z ]", " ", value.upper())
    return re.sub(r"\s+", " ", value).strip()


_DATE_PATTERNS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
    "%m/%d/%Y", "%Y/%m/%d", "%y%m%d", "%d%m%y",
]


def normalize_date(value: str | None) -> str:
    """Return ISO YYYY-MM-DD if parseable, else the cleaned original string."""
    if not value:
        return ""
    raw = clean_text(value)
    candidate = raw.replace(",", " ").strip()
    candidate = re.sub(r"\s+", " ", candidate)
    for fmt in _DATE_PATTERNS:
        try:
            dt = datetime.strptime(candidate, fmt)
            if dt.year > datetime.now().year + 20 and fmt in ("%y%m%d", "%d%m%y"):
                dt = dt.replace(year=dt.year - 100)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return candidate.upper()


def similarity(a: str | None, b: str | None) -> float:
    a_n, b_n = normalize_name(a), normalize_name(b)
    if not a_n or not b_n:
        return 0.0
    return SequenceMatcher(None, a_n, b_n).ratio()


def dates_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return normalize_date(a) == normalize_date(b)


def truncate(value: str, length: int = 120) -> str:
    value = clean_text(value)
    return value if len(value) <= length else value[: length - 1] + "…"
