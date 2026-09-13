"""Investigations: create, list/history (filters + search), detail, re-analyze."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document, Investigation
from ..schemas import serializers as S
from ..schemas.requests import InvestigationCreate
from ..services import analysis_service
from ..utils.text import normalize_doc_number

router = APIRouter(prefix="/investigations", tags=["investigations"])


@router.post("")
def create_investigation(payload: InvestigationCreate, db: Session = Depends(get_db)) -> dict:
    inv = analysis_service.create_investigation(
        db, title=payload.title, assigned_officer=payload.assigned_officer)
    return S.investigation_summary(inv)


@router.get("")
def list_investigations(
    risk: str | None = None,
    status: str | None = None,
    document_type: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Investigation)
    count_stmt = select(func.count(func.distinct(Investigation.id))).select_from(Investigation)
    conds = []

    if risk:
        conds.append(Investigation.risk_level == risk.upper())
    if status:
        conds.append(Investigation.screening_status == status.upper())
    if date_from:
        try:
            conds.append(Investigation.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            conds.append(Investigation.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    needs_doc_join = bool(document_type or search)
    if needs_doc_join:
        stmt = stmt.join(Document, Document.investigation_id == Investigation.id)
        count_stmt = count_stmt.join(Document, Document.investigation_id == Investigation.id)
    if document_type:
        conds.append(Document.document_type == document_type.upper())
    if search:
        like = f"%{search.strip()}%"
        norm = normalize_doc_number(search)
        conds.append(or_(
            Investigation.screening_id.ilike(like),
            Document.original_filename.ilike(like),
            Document.normalized_document_number.ilike(f"%{norm}%"),
        ))

    for c in conds:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = int(db.execute(count_stmt).scalar_one())
    stmt = (stmt.distinct().order_by(Investigation.created_at.desc())
            .limit(limit).offset(offset))
    invs = db.execute(stmt).scalars().unique().all()
    return {"total": total, "investigations": [S.investigation_summary(i) for i in invs]}


@router.get("/{investigation_id}")
def get_investigation(investigation_id: int, db: Session = Depends(get_db)) -> dict:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return S.investigation_full(inv, db)


@router.post("/{investigation_id}/analyze")
def reanalyze(investigation_id: int, db: Session = Depends(get_db)) -> dict:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if not list(inv.documents):
        raise HTTPException(status_code=400, detail="No documents to analyze")
    inv.stages = analysis_service._init_stages()
    inv.status = "QUEUED"
    inv.screening_status = "QUEUED"
    db.add(inv)
    db.commit()
    analysis_service.start_analysis(inv.id)
    return analysis_service.get_status(db, inv.id)
