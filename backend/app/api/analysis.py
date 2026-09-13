"""Analysis status + result endpoints (analysis id == investigation id)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Investigation
from ..schemas import serializers as S
from ..services import analysis_service

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/{investigation_id}/status")
def analysis_status(investigation_id: int, db: Session = Depends(get_db)) -> dict:
    status = analysis_service.get_status(db, investigation_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return status


@router.get("/{investigation_id}")
def analysis_result(investigation_id: int, db: Session = Depends(get_db)) -> dict:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return S.investigation_full(inv, db)
