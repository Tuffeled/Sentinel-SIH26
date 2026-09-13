"""Analysis orchestrator.

Runs the full screening pipeline for an investigation, persisting each module's
structured result, updating live stage progress (polled by the frontend), then
building evidence, computing risk, and emitting notifications + audit events.

Pipeline order (per the spec):
    received → classification → ocr → mrz → field_consistency → forensic →
    face → watchlist → identity → risk

Note: raw OCR + MRZ *reading* happens during the classification stage (you must
read a document to identify it); the OCR/MRZ stages persist and validate those
reads. Nothing is faked — a module that cannot run reports SKIPPED/WARNING.
"""
from __future__ import annotations

import copy
import threading
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..config import settings
from ..core.constants import (
    AnalysisStatus,
    NotificationType,
    PIPELINE_STAGES,
    RiskLevel,
    ScreeningStatus,
    StageStatus,
    recommended_action_for,
    screening_status_for,
)
from ..core.security import new_uuid, safe_stored_name, validate_upload
from ..database import session_scope
from ..models import (
    Document,
    Evidence,
    FaceReference,
    FaceResult,
    ForensicResult,
    Investigation,
    MrzResult,
    OcrResult,
    Person,
    RiskAssessment,
)
from ..utils import images as imgutil
from ..utils.text import normalize_doc_number
from . import (
    audit_service,
    document_classifier as classifier_mod,
    evidence_service,
    face_service,
    forensic_service,
    identity_service,
    mrz_service,
    notification_service,
    ocr_service,
    risk_service,
    watchlist_service,
)

_classifier = classifier_mod.document_classifier


# ---------------------------------------------------------------------------
# Investigation / document creation
# ---------------------------------------------------------------------------
def generate_screening_id(db: Session) -> str:
    year = datetime.utcnow().year
    prefix = f"SCR-{year}-"
    count = db.execute(
        select(func.count()).select_from(Investigation)
        .where(Investigation.screening_id.like(prefix + "%"))
    ).scalar_one()
    return f"{prefix}{count + 1:06d}"


def create_investigation(db: Session, *, title: str | None = None,
                         assigned_officer: str | None = None) -> Investigation:
    inv = Investigation(
        screening_id=generate_screening_id(db),
        title=title,
        status=AnalysisStatus.QUEUED,
        screening_status=ScreeningStatus.QUEUED,
        assigned_officer=assigned_officer or settings.officer_name,
        stages=_init_stages(),
        progress=0,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    audit_service.log(db, "INVESTIGATION_CREATED", investigation_id=inv.id,
                      actor=inv.assigned_officer, details={"screening_id": inv.screening_id})
    return inv


def add_document(db: Session, investigation: Investigation, *, data: bytes,
                 filename: str, role: str = "primary",
                 ground_truth: str | None = None) -> Document:
    kind = validate_upload(filename, data)  # raises FileValidationError
    stored = safe_stored_name(kind)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / stored
    dest.write_bytes(data)

    w, h = imgutil.image_size(dest)
    doc = Document(
        investigation_id=investigation.id,
        role=role,
        original_filename=Path(filename).name,
        stored_filename=stored,
        file_kind=kind,
        file_size=len(data),
        sha256=imgutil.sha256_bytes(data),
        width=w,
        height=h,
        ground_truth=ground_truth,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    audit_service.log(db, "DOCUMENT_UPLOADED", document_id=doc.id,
                      investigation_id=investigation.id, actor=investigation.assigned_officer,
                      details={"filename": doc.original_filename, "kind": kind,
                               "size": len(data)})
    return doc


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------
def _init_stages() -> list[dict]:
    return [{"key": k, "label": lbl, "status": StageStatus.WAITING,
             "detail": None, "duration_ms": None} for k, lbl in PIPELINE_STAGES]


def _set_stage(db: Session, inv: Investigation, key: str, status: str,
               detail: str | None = None, duration_ms: int | None = None) -> None:
    # Deep-copy so the reassigned list holds NEW dict objects; without this,
    # in-place edits share refs with the loaded value and SQLAlchemy's JSON
    # change-detection misses the update (stages would appear stuck on WAITING).
    stages = copy.deepcopy(inv.stages or _init_stages())
    completed = 0
    for s in stages:
        if s["key"] == key:
            s["status"] = status
            if detail is not None:
                s["detail"] = detail
            if duration_ms is not None:
                s["duration_ms"] = duration_ms
        if s["status"] in (StageStatus.COMPLETED, StageStatus.WARNING,
                           StageStatus.SKIPPED, StageStatus.FAILED):
            completed += 1
    inv.stages = stages
    flag_modified(inv, "stages")  # force the JSON column to be written
    inv.current_stage = key
    inv.progress = int(completed / len(stages) * 100)
    inv.updated_at = datetime.utcnow()
    db.add(inv)
    db.commit()


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def start_analysis(investigation_id: int) -> None:
    """Run the pipeline in a background thread."""
    thread = threading.Thread(target=run_sync, args=(investigation_id,), daemon=True)
    thread.start()


def run_sync(investigation_id: int) -> None:
    """Run the pipeline synchronously (used by background thread, eval, tests)."""
    with session_scope() as db:
        inv = db.get(Investigation, investigation_id)
        if inv is None:
            return
        try:
            _run_pipeline(db, inv)
        except Exception as exc:  # never leave an investigation stuck
            inv.status = AnalysisStatus.FAILED
            inv.screening_status = ScreeningStatus.FAILED
            inv.error = str(exc)
            db.add(inv)
            db.commit()
            audit_service.log(db, "ANALYSIS_FAILED", investigation_id=inv.id,
                              details={"error": str(exc)})
            notification_service.create(
                db, NotificationType.ANALYSIS_FAILED, "Analysis failed",
                f"{inv.screening_id}: {exc}", severity="ERROR", investigation_id=inv.id)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def _run_pipeline(db: Session, inv: Investigation) -> None:
    start = time.time()
    inv.status = AnalysisStatus.RUNNING
    inv.screening_status = ScreeningStatus.PROCESSING
    if not inv.stages:
        inv.stages = _init_stages()
    db.add(inv)
    db.commit()
    audit_service.log(db, "ANALYSIS_STARTED", investigation_id=inv.id,
                      actor=inv.assigned_officer)

    documents = list(inv.documents)
    if not documents:
        raise RuntimeError("No documents attached to investigation.")

    _set_stage(db, inv, "received", StageStatus.COMPLETED,
               detail=f"{len(documents)} document(s) received")

    contexts: dict[int, dict] = {}
    reference_encoding = None
    reference_doc_id = None
    for d in documents:
        if d.role == "reference":
            det = face_service.face_verifier.detect(settings.uploads_dir / d.stored_filename, d.id)
            reference_encoding = det.get("encoding")
            reference_doc_id = d.id

    # ---- Stage: classification (reads OCR + MRZ) ----
    _set_stage(db, inv, "classification", StageStatus.PROCESSING)
    t0 = time.time()
    for doc in documents:
        path = settings.uploads_dir / doc.stored_filename
        ocr = ocr_service.run_ocr(path)
        mrz = mrz_service.detect_and_parse(path, ocr.get("raw_text"))
        classification = _classifier.classify(ocr.get("raw_text", ""), mrz)
        contexts[doc.id] = {"ocr": ocr, "mrz": mrz, "classification": classification}
        doc.document_type = classification["document_type"]
        doc.classification_confidence = classification["confidence"]
        doc.classification_evidence = classification["evidence"]
        db.add(doc)
    db.commit()
    primary = documents[0]
    ctype = contexts[primary.id]["classification"]
    _set_stage(db, inv, "classification", StageStatus.COMPLETED,
               detail=f"{ctype['document_type']} ({ctype['confidence']*100:.0f}%)",
               duration_ms=int((time.time() - t0) * 1000))
    audit_service.log(db, "CLASSIFICATION_COMPLETED", investigation_id=inv.id,
                      document_id=primary.id, details=ctype)

    # ---- Stage: OCR (persist structured fields) ----
    _set_stage(db, inv, "ocr", StageStatus.PROCESSING)
    t0 = time.time()
    ocr_ok = True
    for doc in documents:
        ocr = contexts[doc.id]["ocr"]
        doc_path = settings.uploads_dir / doc.stored_filename
        fields = (ocr_service.extract_fields(ocr.get("raw_text", ""), image_path=doc_path)
                  if ocr.get("available") else {})
        contexts[doc.id]["ocr_fields"] = fields
        db.add(OcrResult(document_id=doc.id, engine=ocr.get("engine"),
                         raw_text=ocr.get("raw_text"), fields=fields,
                         confidence=ocr.get("confidence")))
        if not ocr.get("available"):
            ocr_ok = False
    db.commit()
    _set_stage(db, inv, "ocr", StageStatus.COMPLETED if ocr_ok else StageStatus.WARNING,
               detail=(f"{contexts[primary.id]['ocr'].get('engine','?')} · "
                       f"{(contexts[primary.id]['ocr'].get('confidence') or 0)*100:.0f}%")
               if ocr_ok else "OCR engine unavailable",
               duration_ms=int((time.time() - t0) * 1000))
    audit_service.log(db, "OCR_COMPLETED", investigation_id=inv.id, document_id=primary.id,
                      details={"engine": contexts[primary.id]["ocr"].get("engine")})

    # ---- Stage: MRZ ----
    _set_stage(db, inv, "mrz", StageStatus.PROCESSING)
    t0 = time.time()
    any_mrz = False
    mrz_fail = False
    for doc in documents:
        mrz = contexts[doc.id]["mrz"]
        db.add(MrzResult(document_id=doc.id, detected=mrz.get("detected", False),
                         mrz_type=mrz.get("mrz_type"), raw_lines=mrz.get("raw_lines", []),
                         fields=mrz.get("fields", {}), checks=mrz.get("checks", {}),
                         valid=mrz.get("valid", False)))
        # Record document number (prefer MRZ, fall back OCR).
        num = (mrz.get("fields", {}) or {}).get("document_number") \
            or contexts[doc.id].get("ocr_fields", {}).get("document_number")
        if num:
            doc.document_number = num
            doc.normalized_document_number = normalize_doc_number(num)
            db.add(doc)
        if mrz.get("detected"):
            any_mrz = True
            if not mrz.get("valid"):
                mrz_fail = True
    db.commit()
    p_mrz = contexts[primary.id]["mrz"]
    if not p_mrz.get("detected"):
        mrz_status, mrz_detail = StageStatus.SKIPPED, "MRZ not detected"
    elif p_mrz.get("valid"):
        mrz_status, mrz_detail = StageStatus.COMPLETED, f"{p_mrz.get('mrz_type')} · all checks passed"
    else:
        failed = [k for k, v in (p_mrz.get("checks") or {}).items() if v == "FAIL"]
        mrz_status = StageStatus.WARNING
        mrz_detail = f"{p_mrz.get('mrz_type')} · failed: {', '.join(failed)}"
    _set_stage(db, inv, "mrz", mrz_status, detail=mrz_detail,
               duration_ms=int((time.time() - t0) * 1000))
    audit_service.log(db, "MRZ_VALIDATION_COMPLETED", investigation_id=inv.id,
                      document_id=primary.id, details=p_mrz.get("checks", {}))

    # ---- Stage: field consistency ----
    _set_stage(db, inv, "field_consistency", StageStatus.PROCESSING)
    t0 = time.time()
    from . import validation_service
    consistency_overall = "CONSISTENT"
    for doc in documents:
        cons = validation_service.check_consistency(
            contexts[doc.id].get("ocr_fields", {}),
            contexts[doc.id]["mrz"].get("fields", {}))
        contexts[doc.id]["consistency"] = cons
        if cons["overall"] == "MISMATCH":
            consistency_overall = "MISMATCH"
    p_cons = contexts[primary.id]["consistency"]
    fc_status = (StageStatus.WARNING if p_cons["overall"] == "MISMATCH"
                 else StageStatus.SKIPPED if p_cons["overall"] == "INSUFFICIENT_DATA"
                 else StageStatus.COMPLETED)
    _set_stage(db, inv, "field_consistency", fc_status,
               detail=f"{p_cons['overall']} ({p_cons['compared_count']} fields)",
               duration_ms=int((time.time() - t0) * 1000))

    # ---- Stage: forensic ----
    _set_stage(db, inv, "forensic", StageStatus.PROCESSING)
    t0 = time.time()
    for doc in documents:
        path = settings.uploads_dir / doc.stored_filename
        # Reference = earliest previously-screened document with the same number
        # ("photo on file"), enabling reliable difference analysis.
        ref_path = None
        if doc.normalized_document_number:
            prev = db.execute(
                select(Document)
                .where(Document.normalized_document_number == doc.normalized_document_number,
                       Document.id != doc.id)
                .order_by(Document.created_at.asc())
            ).scalars().first()
            if prev:
                ref_path = settings.uploads_dir / prev.stored_filename
        forensic = forensic_service.analyze(path, doc.id, reference_image_path=ref_path)
        contexts[doc.id]["forensic"] = forensic
        db.add(ForensicResult(
            document_id=doc.id, signals=forensic.get("signals", []),
            overall_score=forensic.get("overall_score"), suspicious=forensic.get("suspicious", False),
            visualization_path=forensic.get("visualization_path"),
            ela_path=forensic.get("ela_path"),
            metadata_findings=forensic.get("metadata_findings", [])))
    db.commit()
    p_for = contexts[primary.id]["forensic"]
    _set_stage(db, inv, "forensic",
               StageStatus.WARNING if p_for.get("suspicious") else StageStatus.COMPLETED,
               detail=f"anomaly score {p_for.get('overall_score', 0):.2f}",
               duration_ms=int((time.time() - t0) * 1000))
    audit_service.log(db, "FORENSIC_ANALYSIS_COMPLETED", investigation_id=inv.id,
                      document_id=primary.id, details={"score": p_for.get("overall_score")})

    # ---- Stage: face ----
    _set_stage(db, inv, "face", StageStatus.PROCESSING)
    t0 = time.time()
    face_engine_off = not face_service.available()
    face_unavailable_notified = False
    for doc in documents:
        if doc.role == "reference":
            continue
        path = settings.uploads_dir / doc.stored_filename

        # Resolve a reference face: an explicit reference doc, else the enrolled
        # gallery entry for this document number ("photo on file").
        ref_enc = reference_encoding
        ref_doc_id = reference_doc_id
        if ref_enc is None and doc.normalized_document_number:
            fr = db.execute(
                select(FaceReference)
                .where(FaceReference.normalized_document_number == doc.normalized_document_number)
                .order_by(FaceReference.created_at.asc())
            ).scalars().first()
            if fr:
                ref_enc = fr.embedding
                ref_doc_id = fr.source_document_id

        face = face_service.face_verifier.analyze(
            path, doc.id, reference_encoding=ref_enc, reference_document_id=ref_doc_id)
        contexts[doc.id]["face"] = face
        db.add(FaceResult(
            document_id=doc.id, engine=face.get("engine"),
            face_detected=face.get("face_detected", False), num_faces=face.get("num_faces", 0),
            face_crop_path=face.get("face_crop_path"),
            reference_document_id=face.get("reference_document_id"),
            similarity=face.get("similarity"), match=face.get("match"),
            confidence=face.get("confidence"), status=face.get("status"),
            detail=face.get("detail")))
        contexts[doc.id]["face_encoding"] = face.get("encoding")

        # Enrol a new reference the first time we see this identifier.
        if (ref_enc is None and face.get("face_detected") and face.get("encoding")
                and doc.normalized_document_number):
            db.add(FaceReference(
                normalized_document_number=doc.normalized_document_number,
                embedding=face["encoding"], source_document_id=doc.id,
                label=(doc.mrz_result.fields.get("full_name") if doc.mrz_result else None)))
    db.commit()
    p_face = contexts[primary.id].get("face", {})
    face_status_map = {
        "MATCH": StageStatus.COMPLETED, "NO_MATCH": StageStatus.WARNING,
        "NOT_DETECTED": StageStatus.WARNING, "NO_REFERENCE": StageStatus.SKIPPED,
        "UNAVAILABLE": StageStatus.SKIPPED,
    }
    _set_stage(db, inv, "face", face_status_map.get(p_face.get("status"), StageStatus.SKIPPED),
               detail=p_face.get("detail", "Face verification"),
               duration_ms=int((time.time() - t0) * 1000))
    if p_face.get("status") in ("UNAVAILABLE", "NOT_DETECTED"):
        notification_service.create(
            db, NotificationType.FACE_UNAVAILABLE, "Face verification limited",
            f"{inv.screening_id}: {p_face.get('detail')}", severity="WARNING",
            investigation_id=inv.id)
    audit_service.log(db, "FACE_VERIFICATION_COMPLETED", investigation_id=inv.id,
                      document_id=primary.id, details={"status": p_face.get("status")})

    # ---- Stage: watchlist ----
    _set_stage(db, inv, "watchlist", StageStatus.PROCESSING)
    t0 = time.time()
    watchlist_hit = False
    for doc in documents:
        rec = watchlist_service.lookup(db, doc.normalized_document_number or doc.document_number)
        if rec:
            watchlist_hit = True
            contexts[doc.id]["watchlist"] = {"match": True, "record": {
                "id": rec.id, "document_number": rec.document_number,
                "status": rec.status, "reason": rec.reason,
                "source": rec.source, "updated_at": rec.updated_at.isoformat() + "Z"}}
        else:
            contexts[doc.id]["watchlist"] = {"match": False, "record": None}
    audit_service.log(db, "WATCHLIST_SEARCHED", investigation_id=inv.id,
                      details={"hit": watchlist_hit})
    _set_stage(db, inv, "watchlist",
               StageStatus.WARNING if watchlist_hit else StageStatus.COMPLETED,
               detail="MATCH found" if watchlist_hit else "No match in synthetic watchlist",
               duration_ms=int((time.time() - t0) * 1000))
    if watchlist_hit:
        notification_service.create(
            db, NotificationType.WATCHLIST_MATCH, "Watchlist match detected",
            f"{inv.screening_id}: identifier matched a synthetic watchlist record.",
            severity="HIGH", investigation_id=inv.id)

    # ---- Stage: identity (cross-document) ----
    _set_stage(db, inv, "identity", StageStatus.PROCESSING)
    t0 = time.time()
    cross = _run_cross_document(db, inv, documents, contexts)
    real_docs = [d for d in documents if d.role != "reference"]
    if len(real_docs) < 2:
        _set_stage(db, inv, "identity", StageStatus.SKIPPED,
                   detail="Single document — cross-check not applicable",
                   duration_ms=int((time.time() - t0) * 1000))
    else:
        _set_stage(db, inv, "identity",
                   StageStatus.WARNING if cross.get("conflicts") else StageStatus.COMPLETED,
                   detail=(f"{len(cross.get('conflicts', []))} conflict(s)"
                           if cross.get("conflicts") else "Consistent across documents"),
                   duration_ms=int((time.time() - t0) * 1000))

    # ---- Stage: risk ----
    _set_stage(db, inv, "risk", StageStatus.PROCESSING)
    t0 = time.time()
    all_evidence: list[dict] = []
    for doc in documents:
        ctx = contexts[doc.id]
        ctx_for_ev = {**ctx, "cross_document": {} }  # cross-doc added once below
        items = evidence_service.build_all(ctx_for_ev)
        for it in items:
            it["_document_id"] = doc.id
        all_evidence += items
    # cross-document evidence once at investigation level
    all_evidence += evidence_service.from_cross_document(cross)

    # Persist evidence
    for it in all_evidence:
        db.add(Evidence(
            investigation_id=inv.id, document_id=it.get("_document_id"),
            type=it["type"], severity=it["severity"], confidence=it["confidence"],
            risk_contribution=it["risk_contribution"], title=it["title"],
            description=it["description"], source=it["source"], details=it.get("details", {})))
    db.commit()

    risk = risk_service.calculate(all_evidence)
    db.add(RiskAssessment(
        investigation_id=inv.id, score=risk["score"], level=risk["level"],
        recommended_action=risk["recommended_action"], contributors=risk["contributors"],
        disclaimer=risk["disclaimer"]))
    inv.risk_score = risk["score"]
    inv.risk_level = risk["level"]
    inv.recommended_action = risk["recommended_action"]
    inv.watchlist_hit = watchlist_hit
    _set_stage(db, inv, "risk", StageStatus.COMPLETED,
               detail=f"{risk['score']:.0f}/100 · {risk['level']}",
               duration_ms=int((time.time() - t0) * 1000))
    audit_service.log(db, "RISK_CALCULATED", investigation_id=inv.id,
                      details={"score": risk["score"], "level": risk["level"]})

    # ---- Finalise ----
    inv.status = AnalysisStatus.COMPLETED
    inv.screening_status = screening_status_for(risk["level"])
    inv.screening_time_ms = int((time.time() - start) * 1000)
    inv.completed_at = datetime.utcnow()
    inv.progress = 100
    db.add(inv)
    db.commit()

    notification_service.create(
        db, NotificationType.SCREENING_COMPLETE, "Screening complete",
        f"{inv.screening_id}: {risk['level']} risk ({risk['score']:.0f}/100).",
        severity="INFO", investigation_id=inv.id)
    if risk["level"] in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        notification_service.create(
            db, NotificationType.HIGH_RISK, "High-risk document detected",
            f"{inv.screening_id} flagged as {risk['level']} — officer review required.",
            severity="HIGH", investigation_id=inv.id)
        notification_service.create(
            db, NotificationType.REVIEW_REQUIRED, "Officer review required",
            f"{inv.screening_id} awaits human review.", severity="HIGH",
            investigation_id=inv.id)
    audit_service.log(db, "ANALYSIS_COMPLETED", investigation_id=inv.id,
                      details={"screening_time_ms": inv.screening_time_ms})


def _run_cross_document(db: Session, inv: Investigation, documents, contexts) -> dict:
    from ..models import IdentityLink
    doc_inputs = []
    for doc in documents:
        if doc.role == "reference":
            continue
        ctx = contexts.get(doc.id, {})
        doc_inputs.append({
            "id": doc.id, "document_type": doc.document_type,
            "label": f"{doc.document_type} ({doc.original_filename})",
            "ocr_fields": ctx.get("ocr_fields", {}),
            "mrz_fields": ctx.get("mrz", {}).get("fields", {}),
            "face_encoding": ctx.get("face_encoding"),
            "document_number": doc.document_number,
        })
    cross = identity_service.analyze(doc_inputs)
    # Persist matrix rows as identity links.
    for row in cross.get("matrix", []):
        db.add(IdentityLink(
            investigation_id=inv.id, relation="COMPARE",
            attribute=row["attribute"], result=row["result"], detail=row))
    db.commit()
    inv._cross_document = cross  # transient, not persisted
    return cross


# ---------------------------------------------------------------------------
# Status for polling
# ---------------------------------------------------------------------------
def get_status(db: Session, investigation_id: int) -> dict | None:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        return None
    return {
        "investigation_id": inv.id,
        "screening_id": inv.screening_id,
        "status": inv.status,
        "screening_status": inv.screening_status,
        "current_stage": inv.current_stage,
        "progress": inv.progress,
        "stages": inv.stages,
        "risk_score": inv.risk_score,
        "risk_level": inv.risk_level,
        "recommended_action": inv.recommended_action,
        "error": inv.error,
    }
