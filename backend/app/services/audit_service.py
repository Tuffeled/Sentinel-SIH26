"""Audit trail writer + reader."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog


def log(
    db: Session,
    event: str,
    *,
    actor: str = "system",
    document_id: int | None = None,
    investigation_id: int | None = None,
    case_id: int | None = None,
    details: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        event=event,
        actor=actor,
        document_id=document_id,
        investigation_id=investigation_id,
        case_id=case_id,
        details=details or {},
    )
    db.add(entry)
    if commit:
        db.commit()
    else:
        db.flush()
    return entry


def timeline(db: Session, investigation_id: int) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.investigation_id == investigation_id)
        .order_by(AuditLog.ts.asc(), AuditLog.id.asc())
    )
    return list(db.execute(stmt).scalars())


def recent(db: Session, limit: int = 100) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars())
