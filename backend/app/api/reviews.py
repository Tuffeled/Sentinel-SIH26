"""Human-in-the-loop review endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.constants import ReviewDecision
from ..database import get_db
from ..models import Review
from ..schemas import serializers as S
from ..schemas.requests import ReviewCreate
from ..services import case_service

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("")
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)) -> dict:
    if not payload.valid_decision():
        raise HTTPException(status_code=422,
                            detail=f"decision must be one of {ReviewDecision.ALL}")
    review = case_service.submit_review(
        db, investigation_id=payload.investigation_id,
        reviewer=payload.reviewer, decision=payload.decision,
        notes=payload.notes, create_case_flag=payload.create_case)
    if review is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return S.review_dict(review)


@router.get("")
def list_reviews(investigation_id: int | None = None, limit: int = 100,
                 db: Session = Depends(get_db)) -> dict:
    stmt = select(Review).order_by(Review.created_at.desc()).limit(limit)
    if investigation_id:
        stmt = stmt.where(Review.investigation_id == investigation_id)
    rows = db.execute(stmt).scalars().all()
    return {"reviews": [S.review_dict(r) for r in rows]}
