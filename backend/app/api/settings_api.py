"""Settings + demo-data controls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Document, Investigation, Watchlist
from ..services import demo_service, evaluation_service, face_service, ocr_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)) -> dict:
    counts = {
        "investigations": int(db.execute(select(func.count(Investigation.id))).scalar_one()),
        "documents": int(db.execute(select(func.count(Document.id))).scalar_one()),
        "watchlist": int(db.execute(select(func.count(Watchlist.id))).scalar_one()),
    }
    dataset = evaluation_service.load_dataset()
    return {
        "config": settings.as_public_dict(),
        "ocr": ocr_service.engine_status(),
        "face": face_service.engine_status(),
        "database": {"url": "sqlite (local)", "counts": counts},
        "dataset": {"count": len(dataset),
                    "genuine": sum(1 for i in dataset if i["ground_truth"] == "GENUINE"),
                    "altered": sum(1 for i in dataset if i["ground_truth"] == "ALTERED")},
    }


@router.post("/seed-demo")
def seed_demo(db: Session = Depends(get_db)) -> dict:
    return demo_service.seed_demo(db)


@router.post("/clear-demo")
def clear_demo(confirm: bool = Query(default=False), db: Session = Depends(get_db)) -> dict:
    if not confirm:
        raise HTTPException(status_code=400,
                            detail="Destructive action requires ?confirm=true")
    return demo_service.clear_demo(db)


@router.post("/reset")
def reset_demo(confirm: bool = Query(default=False), db: Session = Depends(get_db)) -> dict:
    if not confirm:
        raise HTTPException(status_code=400,
                            detail="Destructive action requires ?confirm=true")
    return demo_service.reset_demo(db)
