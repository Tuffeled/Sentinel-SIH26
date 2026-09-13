"""Local SYNTHETIC watchlist (SQLite).

This is NOT connected to any real stolen-document database. It only checks
whether an extracted (synthetic) identifier appears in the local demonstration
table. A "no match" result does NOT mean a document is genuine.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.constants import WatchlistStatus
from ..models import Watchlist
from ..utils.text import normalize_doc_number


def lookup(db: Session, document_number: str | None) -> Watchlist | None:
    """Return an active watchlist record matching the normalised number, or None."""
    norm = normalize_doc_number(document_number)
    if not norm:
        return None
    stmt = (
        select(Watchlist)
        .where(Watchlist.normalized_document_number == norm)
        .where(Watchlist.active.is_(True))
        .order_by(Watchlist.updated_at.desc())
    )
    return db.execute(stmt).scalars().first()


def list_records(
    db: Session,
    *,
    status: str | None = None,
    active: bool | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[Watchlist], int]:
    stmt = select(Watchlist)
    count_stmt = select(func.count()).select_from(Watchlist)
    conds = []
    if status:
        conds.append(Watchlist.status == status)
    if active is not None:
        conds.append(Watchlist.active.is_(active))
    if search:
        like = f"%{search.strip()}%"
        norm = normalize_doc_number(search)
        conds.append(or_(
            Watchlist.document_number.ilike(like),
            Watchlist.normalized_document_number.ilike(f"%{norm}%"),
            Watchlist.reason.ilike(like),
        ))
    for c in conds:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)
    total = int(db.execute(count_stmt).scalar_one())
    stmt = stmt.order_by(Watchlist.updated_at.desc(), Watchlist.id.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars()), total


def get(db: Session, record_id: int) -> Watchlist | None:
    return db.get(Watchlist, record_id)


def create(db: Session, data: dict) -> Watchlist:
    number = data.get("document_number", "")
    rec = Watchlist(
        document_number=number,
        normalized_document_number=normalize_doc_number(number),
        document_type=data.get("document_type", "PASSPORT"),
        status=data.get("status", WatchlistStatus.FLAGGED),
        reason=data.get("reason"),
        source=data.get("source", "SYNTHETIC_DEMO"),
        notes=data.get("notes"),
        active=data.get("active", True),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def upsert(db: Session, data: dict) -> Watchlist:
    """Create or update by normalised number (used by demo seeding)."""
    norm = normalize_doc_number(data.get("document_number", ""))
    existing = db.execute(
        select(Watchlist).where(Watchlist.normalized_document_number == norm)
    ).scalars().first()
    if existing:
        for key in ("document_type", "status", "reason", "source", "notes", "active"):
            if key in data and data[key] is not None:
                setattr(existing, key, data[key])
        db.commit()
        db.refresh(existing)
        return existing
    return create(db, data)


def update(db: Session, record_id: int, data: dict) -> Watchlist | None:
    rec = db.get(Watchlist, record_id)
    if not rec:
        return None
    if "document_number" in data and data["document_number"]:
        rec.document_number = data["document_number"]
        rec.normalized_document_number = normalize_doc_number(data["document_number"])
    for key in ("document_type", "status", "reason", "source", "notes", "active"):
        if key in data and data[key] is not None:
            setattr(rec, key, data[key])
    db.commit()
    db.refresh(rec)
    return rec


def deactivate(db: Session, record_id: int) -> bool:
    rec = db.get(Watchlist, record_id)
    if not rec:
        return False
    rec.active = False
    db.commit()
    return True


def stats(db: Session) -> dict:
    def count(*conds) -> int:
        stmt = select(func.count()).select_from(Watchlist)
        for c in conds:
            stmt = stmt.where(c)
        return int(db.execute(stmt).scalar_one())

    return {
        "total": count(),
        "active": count(Watchlist.active.is_(True)),
        "flagged": count(Watchlist.status == WatchlistStatus.FLAGGED),
        "stolen_lost": count(Watchlist.status.in_([WatchlistStatus.STOLEN, WatchlistStatus.LOST])),
        "under_review": count(Watchlist.status == WatchlistStatus.UNDER_REVIEW),
    }


# --- Demo seeding ------------------------------------------------------------
_DEMO_RECORDS = [
    {"document_number": "SYN-PAS-00001", "document_type": "PASSPORT",
     "status": WatchlistStatus.STOLEN, "reason": "Reported stolen (synthetic demo record)."},
    {"document_number": "SYN-PAS-00002", "document_type": "PASSPORT",
     "status": WatchlistStatus.LOST, "reason": "Reported lost (synthetic demo record)."},
    {"document_number": "SYN-ID-00003", "document_type": "NATIONAL_ID",
     "status": WatchlistStatus.SUSPICIOUS, "reason": "Flagged during prior screening (synthetic)."},
    {"document_number": "SYN-PAS-00017", "document_type": "PASSPORT",
     "status": WatchlistStatus.FLAGGED, "reason": "Associated with a flagged synthetic identity."},
    {"document_number": "SYN-VIS-00021", "document_type": "VISA",
     "status": WatchlistStatus.REVOKED, "reason": "Visa revoked (synthetic demo record)."},
    {"document_number": "SYN-PAS-00042", "document_type": "PASSPORT",
     "status": WatchlistStatus.DUPLICATE, "reason": "Duplicate identifier detected (synthetic)."},
    {"document_number": "SYN-ID-00055", "document_type": "NATIONAL_ID",
     "status": WatchlistStatus.UNDER_REVIEW, "reason": "Pending manual review (synthetic)."},
    # Matches the synthetic "watchlist demo" passport (passport_099_watchlist_demo).
    {"document_number": "SP0000099", "document_type": "PASSPORT",
     "status": WatchlistStatus.STOLEN,
     "reason": "Reported stolen — matches synthetic demonstration passport SP0000099."},
]


def seed_demo(db: Session, extra: list[dict] | None = None) -> int:
    """Insert synthetic demo watchlist records (idempotent by number)."""
    records = list(_DEMO_RECORDS) + list(extra or [])
    count = 0
    for rec in records:
        rec = {**rec, "source": "SYNTHETIC_DEMO", "active": rec.get("active", True)}
        upsert(db, rec)
        count += 1
    return count
