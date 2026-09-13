"""Notifications generated from real system events."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Notification


def create(
    db: Session,
    ntype: str,
    title: str,
    message: str,
    *,
    severity: str = "INFO",
    investigation_id: int | None = None,
    commit: bool = True,
) -> Notification:
    note = Notification(
        type=ntype,
        title=title,
        message=message,
        severity=severity,
        investigation_id=investigation_id,
    )
    db.add(note)
    if commit:
        db.commit()
    else:
        db.flush()
    return note


def list_notifications(db: Session, limit: int = 50, unread_only: bool = False) -> list[Notification]:
    stmt = select(Notification).order_by(Notification.created_at.desc(), Notification.id.desc())
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
    return list(db.execute(stmt.limit(limit)).scalars())


def unread_count(db: Session) -> int:
    return int(db.execute(
        select(func.count()).select_from(Notification).where(Notification.read.is_(False))
    ).scalar_one())


def mark_read(db: Session, note_id: int) -> bool:
    note = db.get(Notification, note_id)
    if not note:
        return False
    note.read = True
    db.commit()
    return True


def mark_all_read(db: Session) -> int:
    notes = db.execute(select(Notification).where(Notification.read.is_(False))).scalars().all()
    for n in notes:
        n.read = True
    db.commit()
    return len(notes)
