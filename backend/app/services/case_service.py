"""Case management + human review handling."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.constants import (
    CaseStatus,
    RecommendedAction,
    ReviewDecision,
    ScreeningStatus,
)
from ..models import Case, Investigation, Review
from . import audit_service, notification_service


def generate_case_id(db: Session) -> str:
    year = datetime.utcnow().year
    prefix = f"CASE-{year}-"
    count = db.execute(
        select(func.count()).select_from(Case).where(Case.case_id.like(prefix + "%"))
    ).scalar_one()
    return f"{prefix}{count + 1:04d}"


def create_case(db: Session, *, title: str, investigation_id: int | None = None,
                assigned_officer: str | None = None, status: str = CaseStatus.OPEN,
                summary: str | None = None) -> Case:
    case = Case(
        case_id=generate_case_id(db), title=title, status=status,
        assigned_officer=assigned_officer or settings.officer_name, summary=summary)
    db.add(case)
    db.commit()
    db.refresh(case)
    if investigation_id:
        inv = db.get(Investigation, investigation_id)
        if inv:
            inv.case_id = case.id
            case.risk_level = inv.risk_level
            case.risk_score = inv.risk_score
            db.add_all([inv, case])
            db.commit()
    audit_service.log(db, "CASE_CREATED", case_id=case.id,
                      investigation_id=investigation_id, actor=case.assigned_officer,
                      details={"case_id": case.case_id, "title": title})
    return case


def attach_investigation(db: Session, case_id: int, investigation_id: int) -> bool:
    case = db.get(Case, case_id)
    inv = db.get(Investigation, investigation_id)
    if not case or not inv:
        return False
    inv.case_id = case.id
    db.add(inv)
    db.commit()
    audit_service.log(db, "INVESTIGATION_ATTACHED_TO_CASE", case_id=case.id,
                      investigation_id=investigation_id)
    return True


def update_case(db: Session, case_id: int, data: dict) -> Case | None:
    case = db.get(Case, case_id)
    if not case:
        return None
    for key in ("title", "status", "assigned_officer", "summary"):
        if key in data and data[key] is not None:
            setattr(case, key, data[key])
    if data.get("status") == CaseStatus.RESOLVED and not case.resolved_at:
        case.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(case)
    audit_service.log(db, "CASE_UPDATED", case_id=case.id, details=data)
    return case


def stats(db: Session) -> dict:
    def count(*conds) -> int:
        stmt = select(func.count()).select_from(Case)
        for c in conds:
            stmt = stmt.where(c)
        return int(db.execute(stmt).scalar_one())

    return {
        "total": count(),
        "open": count(Case.status == CaseStatus.OPEN),
        "under_review": count(Case.status == CaseStatus.UNDER_REVIEW),
        "escalated": count(Case.status == CaseStatus.ESCALATED),
        "resolved": count(Case.status == CaseStatus.RESOLVED),
    }


def open_case_count(db: Session) -> int:
    return int(db.execute(
        select(func.count()).select_from(Case)
        .where(Case.status != CaseStatus.RESOLVED)
    ).scalar_one())


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
_DECISION_TO_ACTION = {
    ReviewDecision.CLEAR: RecommendedAction.CLEAR,
    ReviewDecision.SECONDARY_INSPECTION: RecommendedAction.SECONDARY_INSPECTION,
    ReviewDecision.SUSPICIOUS: RecommendedAction.ESCALATE,
    ReviewDecision.INCONCLUSIVE: RecommendedAction.ROUTINE_VERIFICATION,
}


def submit_review(db: Session, *, investigation_id: int, reviewer: str,
                  decision: str, notes: str | None = None,
                  create_case_flag: bool = False) -> Review | None:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        return None

    ai_action = inv.recommended_action
    ai_level = inv.risk_level
    officer_action = _DECISION_TO_ACTION.get(decision)
    overridden = bool(ai_action and officer_action and officer_action != ai_action)

    review = Review(
        investigation_id=inv.id, case_id=inv.case_id, reviewer=reviewer or settings.officer_name,
        decision=decision, notes=notes, ai_recommendation=ai_action,
        ai_risk_level=ai_level, overridden=overridden)
    db.add(review)
    inv.screening_status = ScreeningStatus.REVIEWED
    db.add(inv)
    db.commit()
    db.refresh(review)

    audit_service.log(db, "OFFICER_REVIEWED", investigation_id=inv.id,
                      actor=review.reviewer,
                      details={"decision": decision, "overridden": overridden})
    if overridden:
        audit_service.log(db, "DECISION_OVERRIDDEN", investigation_id=inv.id,
                          actor=review.reviewer,
                          details={"ai": ai_action, "officer": decision})

    if create_case_flag and not inv.case_id:
        create_case(db, title=f"Review case for {inv.screening_id}",
                    investigation_id=inv.id, assigned_officer=review.reviewer,
                    status=CaseStatus.UNDER_REVIEW,
                    summary=f"Opened from officer review ({decision}).")
    return review
