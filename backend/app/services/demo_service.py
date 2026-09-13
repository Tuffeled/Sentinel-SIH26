"""Demo data seeding / clearing.

Seeding runs the REAL analysis pipeline over the synthetic dataset so every
dashboard number originates from genuine analysis — nothing is fabricated. Only
the created_at timestamps of demo screenings are spread across the last few days
so the trend chart has history (these are clearly-synthetic demo records).
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import settings
from ..core.constants import CaseStatus, ReviewDecision, RiskLevel
from ..database import session_scope
from ..models import (
    AuditLog,
    Case,
    Document,
    Evidence,
    FaceReference,
    FaceResult,
    ForensicResult,
    IdentityLink,
    Investigation,
    MrzResult,
    Notification,
    OcrResult,
    Person,
    Review,
    RiskAssessment,
    Watchlist,
)
from . import analysis_service, case_service, watchlist_service

# Delete order respects foreign keys (children first).
_OPERATIONAL_MODELS = [
    AuditLog, Notification, Review, RiskAssessment, Evidence, IdentityLink,
    FaceResult, ForensicResult, MrzResult, OcrResult, FaceReference, Document,
    Investigation, Case, Person,
]


def clear_demo(db: Session) -> dict:
    """Delete all operational data (keeps the watchlist)."""
    for model in _OPERATIONAL_MODELS:
        db.execute(delete(model))
    db.commit()
    return {"cleared": True, "kept": "watchlist"}


def reset_demo(db: Session) -> dict:
    """Delete everything including the watchlist, then re-seed the watchlist."""
    for model in _OPERATIONAL_MODELS + [Watchlist]:
        db.execute(delete(model))
    db.commit()
    watchlist_service.seed_demo(db)
    return {"reset": True}


def _dataset() -> list[dict]:
    from .evaluation_service import load_dataset
    return load_dataset()


def seed_demo(db: Session, spread_days: int = 7) -> dict:
    """Seed watchlist + run the real pipeline over the synthetic dataset."""
    watchlist_service.seed_demo(db)
    dataset = _dataset()
    if not dataset:
        return {"seeded_watchlist": True, "screenings": 0,
                "message": "No synthetic dataset found — generate it first "
                           "(python backend/generate_synthetic_docs.py)."}

    created_ids: list[int] = []
    rng = random.Random(42)
    for idx, item in enumerate(dataset):
        data = item["path"].read_bytes()
        inv = analysis_service.create_investigation(
            db, title=f"Demo screening — {item['file']}")
        analysis_service.add_document(
            db, inv, data=data, filename=item["file"], role="primary",
            ground_truth=item["ground_truth"])
        analysis_service.run_sync(inv.id)
        created_ids.append(inv.id)

        # Spread timestamps across the last `spread_days` days for the trend chart.
        day_offset = rng.randint(0, max(spread_days - 1, 0))
        when = datetime.utcnow() - timedelta(days=day_offset,
                                             hours=rng.randint(0, 20),
                                             minutes=rng.randint(0, 59))
        fresh = db.get(Investigation, inv.id)
        if fresh:
            fresh.created_at = when
            fresh.completed_at = when + timedelta(seconds=(fresh.screening_time_ms or 3000) / 1000)
            db.add(fresh)
    db.commit()

    # Create a case + a review for the first high-risk screening (populates Cases page).
    high = db.query(Investigation).filter(
        Investigation.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL])
    ).first()
    if high:
        case_service.create_case(
            db, title=f"Escalated: {high.screening_id}", investigation_id=high.id,
            status=CaseStatus.UNDER_REVIEW,
            summary="Auto-opened demo case for a high-risk synthetic screening.")
        case_service.submit_review(
            db, investigation_id=high.id, reviewer=settings.officer_name,
            decision=ReviewDecision.SECONDARY_INSPECTION,
            notes="Demo review: anomalies confirmed on the synthetic document.")

    return {"seeded_watchlist": True, "screenings": len(created_ids),
            "investigation_ids": created_ids}


# Convenience wrappers using their own session (for the CLI script).
def seed_demo_standalone(spread_days: int = 7) -> dict:
    with session_scope() as db:
        return seed_demo(db, spread_days)


def reset_standalone() -> dict:
    with session_scope() as db:
        return reset_demo(db)
