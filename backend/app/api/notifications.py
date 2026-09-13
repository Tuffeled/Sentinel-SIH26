"""Notification endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import serializers as S
from ..services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(limit: int = 50, unread_only: bool = False,
                       db: Session = Depends(get_db)) -> dict:
    rows = notification_service.list_notifications(db, limit=limit, unread_only=unread_only)
    return {
        "unread_count": notification_service.unread_count(db),
        "notifications": [S.notification_dict(n) for n in rows],
    }


@router.post("/{note_id}/read")
def mark_read(note_id: int, db: Session = Depends(get_db)) -> dict:
    if not notification_service.mark_read(db, note_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db)) -> dict:
    count = notification_service.mark_all_read(db)
    return {"ok": True, "updated": count}
