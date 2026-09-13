"""Health & system status."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..core.constants import AnalysisStatus
from ..database import get_db
from ..models import Investigation
from ..services import face_service, ocr_service

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    running = db.execute(
        select(Investigation.id).where(Investigation.status == AnalysisStatus.RUNNING).limit(1)
    ).first()

    status = "operational" if db_ok else "degraded"
    if running:
        status = "busy"

    return {
        "status": status,
        "state": "ANALYSIS_BUSY" if running else ("SYSTEM_OPERATIONAL" if db_ok else "DEGRADED"),
        "demo_mode": settings.demo_mode,
        "time": datetime.utcnow().isoformat() + "Z",
        "database": "connected" if db_ok else "error",
        "ocr": ocr_service.engine_status(),
        "face": face_service.engine_status(),
        "app_name": settings.app_name,
    }
