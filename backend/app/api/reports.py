"""Investigation report generation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/{investigation_id}")
def generate_report(investigation_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        result = report_service.generate_pdf(db, investigation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "ok": True,
        "filename": result["filename"],
        "url": f"/api/media/{result['relative']}",
    }
