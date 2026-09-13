"""Global search across screenings, documents, cases."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Case, Document, Investigation
from ..schemas import serializers as S
from ..utils.text import normalize_doc_number

router = APIRouter(tags=["search"])


@router.get("/search")
def search(q: str, limit: int = 20, db: Session = Depends(get_db)) -> dict:
    q = (q or "").strip()
    if not q:
        return {"query": q, "investigations": [], "cases": []}
    like = f"%{q}%"
    norm = normalize_doc_number(q)

    inv_ids = db.execute(
        select(Investigation.id)
        .join(Document, Document.investigation_id == Investigation.id, isouter=True)
        .where(or_(
            Investigation.screening_id.ilike(like),
            Document.original_filename.ilike(like),
            Document.normalized_document_number.ilike(f"%{norm}%"),
            Document.document_number.ilike(like),
        ))
        .distinct().limit(limit)
    ).scalars().all()
    invs = [db.get(Investigation, i) for i in inv_ids]

    cases = db.execute(
        select(Case).where(or_(Case.case_id.ilike(like), Case.title.ilike(like))).limit(limit)
    ).scalars().all()

    return {
        "query": q,
        "investigations": [S.investigation_summary(i) for i in invs if i],
        "cases": [S.case_dict(c) for c in cases],
    }
