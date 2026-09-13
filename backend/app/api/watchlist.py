"""Synthetic watchlist endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import serializers as S
from ..schemas.requests import WatchlistCreate, WatchlistUpdate
from ..services import audit_service, watchlist_service

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def list_watchlist(status: str | None = None, active: bool | None = None,
                   search: str | None = None, limit: int = 200, offset: int = 0,
                   db: Session = Depends(get_db)) -> dict:
    records, total = watchlist_service.list_records(
        db, status=status, active=active, search=search, limit=limit, offset=offset)
    return {
        "total": total,
        "stats": watchlist_service.stats(db),
        "records": [S.watchlist_dict(r) for r in records],
        "notice": "SYNTHETIC DEMO WATCHLIST — not connected to any real database.",
    }


@router.get("/search")
def search_watchlist(document_number: str, db: Session = Depends(get_db)) -> dict:
    rec = watchlist_service.lookup(db, document_number)
    return {
        "query": document_number,
        "match": bool(rec),
        "record": S.watchlist_dict(rec) if rec else None,
        "note": ("No match in the local synthetic watchlist. This does NOT mean the "
                 "document is genuine." if not rec else "Matched a synthetic watchlist record."),
    }


@router.get("/{record_id}")
def get_record(record_id: int, db: Session = Depends(get_db)) -> dict:
    rec = watchlist_service.get(db, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return S.watchlist_dict(rec)


@router.post("")
def create_record(payload: WatchlistCreate, db: Session = Depends(get_db)) -> dict:
    rec = watchlist_service.create(db, payload.model_dump())
    audit_service.log(db, "WATCHLIST_RECORD_CREATED",
                      details={"id": rec.id, "number": rec.document_number})
    return S.watchlist_dict(rec)


@router.put("/{record_id}")
def update_record(record_id: int, payload: WatchlistUpdate,
                  db: Session = Depends(get_db)) -> dict:
    rec = watchlist_service.update(db, record_id, payload.model_dump(exclude_none=True))
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return S.watchlist_dict(rec)


@router.delete("/{record_id}")
def deactivate_record(record_id: int, db: Session = Depends(get_db)) -> dict:
    """Soft-deactivate (records are preserved for audit; nothing is hard-deleted)."""
    if not watchlist_service.deactivate(db, record_id):
        raise HTTPException(status_code=404, detail="Record not found")
    audit_service.log(db, "WATCHLIST_RECORD_DEACTIVATED", details={"id": record_id})
    return {"ok": True, "deactivated": record_id}


@router.post("/seed-demo")
def seed_demo(db: Session = Depends(get_db)) -> dict:
    count = watchlist_service.seed_demo(db)
    audit_service.log(db, "WATCHLIST_SEEDED", details={"count": count})
    return {"ok": True, "seeded": count}
