"""Case management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Case
from ..schemas import serializers as S
from ..schemas.requests import CaseCreate, CaseUpdate
from ..services import case_service

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
def list_cases(status: str | None = None, limit: int = 100,
               db: Session = Depends(get_db)) -> dict:
    stmt = select(Case).order_by(Case.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Case.status == status.upper())
    cases = db.execute(stmt).scalars().all()
    return {
        "stats": case_service.stats(db),
        "cases": [S.case_dict(c, list(c.investigations)) for c in cases],
    }


@router.get("/stats")
def case_stats(db: Session = Depends(get_db)) -> dict:
    return case_service.stats(db)


@router.post("")
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> dict:
    case = case_service.create_case(
        db, title=payload.title, investigation_id=payload.investigation_id,
        assigned_officer=payload.assigned_officer, status=payload.status,
        summary=payload.summary)
    return S.case_dict(case, list(case.investigations))


@router.get("/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return S.case_dict(case, list(case.investigations))


@router.put("/{case_id}")
def update_case(case_id: int, payload: CaseUpdate, db: Session = Depends(get_db)) -> dict:
    case = case_service.update_case(db, case_id, payload.model_dump(exclude_none=True))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return S.case_dict(case, list(case.investigations))


@router.post("/{case_id}/attach/{investigation_id}")
def attach(case_id: int, investigation_id: int, db: Session = Depends(get_db)) -> dict:
    ok = case_service.attach_investigation(db, case_id, investigation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Case or investigation not found")
    return {"ok": True}
