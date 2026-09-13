"""Genuine vs altered document comparison (for the SIH demo)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document, Investigation
from ..schemas import serializers as S

router = APIRouter(prefix="/compare", tags=["compare"])

_COMPARE_FIELDS = ["full_name", "surname", "given_names", "document_number",
                   "nationality", "dob", "sex", "expiry_date"]


def _fields_of(doc: Document) -> dict:
    mrz = (doc.mrz_result.fields if doc.mrz_result else {}) or {}
    ocr = (doc.ocr_result.fields if doc.ocr_result else {}) or {}
    merged = {}
    for k in _COMPARE_FIELDS:
        merged[k] = mrz.get(k) or ocr.get(k) or ""
    return merged


def _risk_of(db: Session, doc: Document) -> dict:
    inv = db.get(Investigation, doc.investigation_id) if doc.investigation_id else None
    if not inv:
        return {}
    return {"screening_id": inv.screening_id, "risk_score": inv.risk_score,
            "risk_level": inv.risk_level, "recommended_action": inv.recommended_action,
            "watchlist_hit": inv.watchlist_hit, "investigation_id": inv.id}


@router.get("")
def compare(a: int = Query(...), b: int = Query(...), db: Session = Depends(get_db)) -> dict:
    doc_a = db.get(Document, a)
    doc_b = db.get(Document, b)
    if not doc_a or not doc_b:
        raise HTTPException(status_code=404, detail="One or both documents not found")

    fa, fb = _fields_of(doc_a), _fields_of(doc_b)
    field_diffs = []
    for k in _COMPARE_FIELDS:
        va, vb = fa.get(k, ""), fb.get(k, "")
        field_diffs.append({"field": k, "label": k.replace("_", " ").title(),
                            "a": va or None, "b": vb or None,
                            "same": (va or "").upper() == (vb or "").upper()})

    def mrz_summary(doc):
        m = doc.mrz_result
        return {"detected": m.detected if m else False,
                "valid": m.valid if m else False,
                "checks": (m.checks if m else {}) or {}} if m else {"detected": False}

    def forensic_summary(doc):
        f = doc.forensic_result
        return {"overall_score": f.overall_score if f else None,
                "suspicious": f.suspicious if f else False,
                "visualization_url": (S._media(f.visualization_path) if f else None)}

    return {
        "a": {"document": S.document_summary(doc_a), "fields": fa,
              "mrz": mrz_summary(doc_a), "forensic": forensic_summary(doc_a),
              "risk": _risk_of(db, doc_a)},
        "b": {"document": S.document_summary(doc_b), "fields": fb,
              "mrz": mrz_summary(doc_b), "forensic": forensic_summary(doc_b),
              "risk": _risk_of(db, doc_b)},
        "field_diffs": field_diffs,
        "differences": [d for d in field_diffs if not d["same"]],
    }
