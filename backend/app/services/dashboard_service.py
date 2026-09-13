"""Dashboard aggregations — every value is computed from the database."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.constants import AnalysisStatus, RiskLevel, ScreeningStatus
from ..models import Document, Investigation, Review


def _completed_filter():
    return Investigation.status == AnalysisStatus.COMPLETED


def stats(db: Session) -> dict:
    documents_screened = int(db.execute(
        select(func.count(Document.id))
        .join(Investigation, Document.investigation_id == Investigation.id)
        .where(_completed_filter())
    ).scalar_one())

    reviewed_ids = select(Review.investigation_id)
    flagged_for_review = int(db.execute(
        select(func.count(Investigation.id)).where(
            _completed_filter(),
            Investigation.screening_status.in_([ScreeningStatus.FLAGGED, ScreeningStatus.REVIEW]),
            Investigation.id.notin_(reviewed_ids),
        )
    ).scalar_one())

    high_risk = int(db.execute(
        select(func.count(Investigation.id)).where(
            _completed_filter(),
            Investigation.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
        )
    ).scalar_one())

    avg_ms = db.execute(
        select(func.avg(Investigation.screening_time_ms)).where(
            _completed_filter(), Investigation.screening_time_ms.isnot(None))
    ).scalar()
    avg_sec = round((avg_ms or 0) / 1000.0, 1)

    total_screenings = int(db.execute(
        select(func.count(Investigation.id)).where(_completed_filter())
    ).scalar_one())

    return {
        "documents_screened": documents_screened,
        "total_screenings": total_screenings,
        "flagged_for_review": flagged_for_review,
        "high_risk_cases": high_risk,
        "avg_screening_time_sec": avg_sec,
    }


def risk_distribution(db: Session) -> dict:
    rows = db.execute(
        select(Investigation.risk_level, func.count(Investigation.id))
        .where(_completed_filter(), Investigation.risk_level.isnot(None))
        .group_by(Investigation.risk_level)
    ).all()
    dist = {lvl: 0 for lvl in RiskLevel.ALL}
    for level, count in rows:
        if level in dist:
            dist[level] = int(count)
    return dist


def trends(db: Session, days: int = 7) -> list[dict]:
    today = datetime.utcnow().date()
    start = today - timedelta(days=days - 1)
    rows = db.execute(
        select(Investigation.created_at, Investigation.risk_level)
        .where(_completed_filter(), Investigation.created_at >= datetime(start.year, start.month, start.day))
    ).all()
    buckets = {(start + timedelta(days=i)).isoformat(): {"screened": 0, "flagged": 0}
               for i in range(days)}
    for created_at, level in rows:
        key = created_at.date().isoformat()
        if key in buckets:
            buckets[key]["screened"] += 1
            if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                buckets[key]["flagged"] += 1
    return [{"date": d, **v} for d, v in sorted(buckets.items())]


def activity(db: Session, limit: int = 15) -> list[dict]:
    invs = db.execute(
        select(Investigation).order_by(Investigation.created_at.desc()).limit(limit)
    ).scalars().all()
    out = []
    for inv in invs:
        docs = list(inv.documents)
        primary = docs[0] if docs else None
        out.append({
            "investigation_id": inv.id,
            "screening_id": inv.screening_id,
            "time": inv.created_at.isoformat() + "Z",
            "document": primary.original_filename if primary else "—",
            "type": primary.document_type if primary else "UNKNOWN",
            "status": inv.screening_status,
            "risk": inv.risk_level or "—",
            "risk_score": inv.risk_score,
            "watchlist_hit": inv.watchlist_hit,
        })
    return out
