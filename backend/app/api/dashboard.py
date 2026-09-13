"""Dashboard data endpoints (all values from the database)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import case_service, dashboard_service, notification_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    data = dashboard_service.stats(db)
    data["open_cases"] = case_service.open_case_count(db)
    data["unread_notifications"] = notification_service.unread_count(db)
    return data


@router.get("/risk-distribution")
def risk_distribution(db: Session = Depends(get_db)) -> dict:
    return dashboard_service.risk_distribution(db)


@router.get("/trends")
def trends(days: int = 7, db: Session = Depends(get_db)) -> dict:
    return {"days": days, "series": dashboard_service.trends(db, days)}


@router.get("/activity")
def activity(limit: int = 15, db: Session = Depends(get_db)) -> dict:
    return {"activity": dashboard_service.activity(db, limit)}


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    """Everything the dashboard needs in a single request."""
    stats_data = dashboard_service.stats(db)
    stats_data["open_cases"] = case_service.open_case_count(db)
    stats_data["unread_notifications"] = notification_service.unread_count(db)
    return {
        "stats": stats_data,
        "risk_distribution": dashboard_service.risk_distribution(db),
        "trends": dashboard_service.trends(db, 7),
        "activity": dashboard_service.activity(db, 12),
    }
