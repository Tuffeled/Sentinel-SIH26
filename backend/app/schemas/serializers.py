"""ORM -> JSON serialisers. OCR text is sanitised/truncated before exposure."""
from __future__ import annotations

from ..models import (
    Case,
    Document,
    Evidence,
    Investigation,
    Notification,
    Review,
    Watchlist,
)
from ..utils.text import clean_text, truncate


def iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _media(rel: str | None) -> str | None:
    return f"/api/media/{rel}" if rel else None


# ---------------------------------------------------------------------------
def document_summary(d: Document) -> dict:
    return {
        "id": d.id,
        "role": d.role,
        "original_filename": d.original_filename,
        "document_type": d.document_type,
        "classification_confidence": d.classification_confidence,
        "document_number": d.document_number,
        "file_kind": d.file_kind,
        "width": d.width,
        "height": d.height,
        "ground_truth": d.ground_truth,
        "image_url": f"/api/documents/{d.id}/image",
        "created_at": iso(d.created_at),
    }


def document_full(d: Document) -> dict:
    base = document_summary(d)
    base["classification_evidence"] = d.classification_evidence or []
    ocr = d.ocr_result
    mrz = d.mrz_result
    forensic = d.forensic_result
    face = d.face_result
    base["ocr"] = {
        "engine": ocr.engine,
        "confidence": ocr.confidence,
        "fields": ocr.fields or {},
        "raw_text": truncate(clean_text(ocr.raw_text or ""), 4000),
    } if ocr else None
    base["mrz"] = {
        "detected": mrz.detected, "mrz_type": mrz.mrz_type,
        "raw_lines": mrz.raw_lines or [], "fields": mrz.fields or {},
        "checks": mrz.checks or {}, "valid": mrz.valid,
    } if mrz else None
    base["forensic"] = {
        "overall_score": forensic.overall_score, "suspicious": forensic.suspicious,
        "signals": forensic.signals or [],
        "metadata_findings": forensic.metadata_findings or [],
        "visualization_url": _media(forensic.visualization_path),
        "ela_url": _media(forensic.ela_path),
    } if forensic else None
    base["face"] = {
        "engine": face.engine, "status": face.status,
        "face_detected": face.face_detected, "num_faces": face.num_faces,
        "similarity": face.similarity, "match": face.match,
        "confidence": face.confidence, "detail": face.detail,
        "crop_url": _media(face.face_crop_path),
    } if face else None
    return base


def evidence_dict(e: Evidence) -> dict:
    return {
        "id": e.id, "type": e.type, "severity": e.severity,
        "confidence": e.confidence, "risk_contribution": e.risk_contribution,
        "title": e.title, "description": e.description, "source": e.source,
        "document_id": e.document_id, "details": e.details or {},
        "created_at": iso(e.created_at),
    }


def review_dict(r: Review) -> dict:
    return {
        "id": r.id, "investigation_id": r.investigation_id, "reviewer": r.reviewer,
        "decision": r.decision, "notes": r.notes,
        "ai_recommendation": r.ai_recommendation, "ai_risk_level": r.ai_risk_level,
        "overridden": r.overridden, "created_at": iso(r.created_at),
    }


def risk_dict(inv: Investigation) -> dict | None:
    if not inv.risk_assessments:
        return None
    r = inv.risk_assessments[-1]
    return {
        "score": r.score, "level": r.level,
        "recommended_action": r.recommended_action,
        "contributors": r.contributors or [], "disclaimer": r.disclaimer,
    }


def investigation_summary(inv: Investigation) -> dict:
    docs = list(inv.documents)
    primary = docs[0] if docs else None
    return {
        "id": inv.id, "screening_id": inv.screening_id, "title": inv.title,
        "status": inv.status, "screening_status": inv.screening_status,
        "progress": inv.progress, "current_stage": inv.current_stage,
        "risk_score": inv.risk_score, "risk_level": inv.risk_level,
        "recommended_action": inv.recommended_action, "watchlist_hit": inv.watchlist_hit,
        "document_type": primary.document_type if primary else None,
        "document_number": primary.document_number if primary else None,
        "document_count": len(docs),
        "assigned_officer": inv.assigned_officer,
        "case_id": inv.case_id,
        "screening_time_ms": inv.screening_time_ms,
        "reviewed": bool(inv.reviews),
        "created_at": iso(inv.created_at),
        "completed_at": iso(inv.completed_at),
    }


def investigation_full(inv: Investigation, db=None) -> dict:
    from ..services import audit_service
    from ..models import IdentityLink
    base = investigation_summary(inv)
    base["stages"] = inv.stages or []
    base["error"] = inv.error
    base["documents"] = [document_full(d) for d in inv.documents]
    base["evidence"] = [evidence_dict(e) for e in
                        sorted(inv.evidence, key=lambda e: e.risk_contribution, reverse=True)]
    base["risk"] = risk_dict(inv)
    base["reviews"] = [review_dict(r) for r in inv.reviews]

    # Cross-document matrix (from persisted identity links)
    links = inv.identity_links
    base["cross_document"] = {
        "applicable": len([d for d in inv.documents if d.role != "reference"]) >= 2,
        "matrix": [l.detail for l in links if l.detail],
    }
    # Audit timeline
    if db is not None:
        base["audit"] = [{
            "ts": iso(a.ts), "event": a.event, "actor": a.actor,
            "document_id": a.document_id, "details": a.details or {},
        } for a in audit_service.timeline(db, inv.id)]
    return base


def case_dict(c: Case, investigations: list | None = None) -> dict:
    d = {
        "id": c.id, "case_id": c.case_id, "title": c.title, "status": c.status,
        "risk_level": c.risk_level, "risk_score": c.risk_score,
        "assigned_officer": c.assigned_officer, "summary": c.summary,
        "created_at": iso(c.created_at), "updated_at": iso(c.updated_at),
        "resolved_at": iso(c.resolved_at),
    }
    if investigations is not None:
        d["investigations"] = [investigation_summary(i) for i in investigations]
        d["document_count"] = sum(len(list(i.documents)) for i in investigations)
    return d


def watchlist_dict(w: Watchlist) -> dict:
    return {
        "id": w.id, "document_number": w.document_number,
        "normalized_document_number": w.normalized_document_number,
        "document_type": w.document_type, "status": w.status, "reason": w.reason,
        "source": w.source, "notes": w.notes, "active": w.active,
        "created_at": iso(w.created_at), "updated_at": iso(w.updated_at),
    }


def notification_dict(n: Notification) -> dict:
    return {
        "id": n.id, "type": n.type, "title": n.title, "message": n.message,
        "severity": n.severity, "investigation_id": n.investigation_id,
        "read": n.read, "created_at": iso(n.created_at),
    }
