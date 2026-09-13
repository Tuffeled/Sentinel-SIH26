"""All ORM tables for the screening system.

Timestamps are stored as naive UTC (``utcnow``) and serialised with a trailing
``Z`` by the schema layer.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from ..database.session import Base


def utcnow() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# People / identity
# ---------------------------------------------------------------------------
class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True)
    external_ref = Column(String(64), index=True, nullable=True)
    full_name = Column(String(255), nullable=True)
    surname = Column(String(128), nullable=True)
    given_names = Column(String(255), nullable=True)
    dob = Column(String(32), nullable=True)
    nationality = Column(String(8), nullable=True)
    sex = Column(String(4), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    documents = relationship("Document", back_populates="person")


# ---------------------------------------------------------------------------
# Investigation (the screening / analysis unit)
# ---------------------------------------------------------------------------
class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(Integer, primary_key=True)
    screening_id = Column(String(32), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=True)

    status = Column(String(16), default="QUEUED", index=True)          # AnalysisStatus
    screening_status = Column(String(16), default="QUEUED", index=True)  # ScreeningStatus
    current_stage = Column(String(32), nullable=True)
    stages = Column(JSON, default=list)      # [{key,label,status,detail,duration_ms}]
    progress = Column(Integer, default=0)

    risk_score = Column(Float, nullable=True)
    risk_level = Column(String(16), nullable=True, index=True)
    recommended_action = Column(String(32), nullable=True)

    watchlist_hit = Column(Boolean, default=False)
    screening_time_ms = Column(Integer, nullable=True)

    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    assigned_officer = Column(String(128), nullable=True)

    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)

    documents = relationship("Document", back_populates="investigation",
                             cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="investigation",
                            cascade="all, delete-orphan")
    risk_assessments = relationship("RiskAssessment", back_populates="investigation",
                                    cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="investigation",
                           cascade="all, delete-orphan")
    identity_links = relationship("IdentityLink", back_populates="investigation",
                                  cascade="all, delete-orphan")
    case = relationship("Case", back_populates="investigations")


# ---------------------------------------------------------------------------
# Documents & per-document analysis results
# ---------------------------------------------------------------------------
class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    investigation_id = Column(Integer, ForeignKey("investigations.id"), index=True, nullable=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)

    role = Column(String(16), default="primary")  # primary | secondary | reference
    original_filename = Column(String(255), nullable=True)
    stored_filename = Column(String(255), nullable=False)
    file_kind = Column(String(8), nullable=True)
    file_size = Column(Integer, nullable=True)
    sha256 = Column(String(64), index=True, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    document_type = Column(String(24), default="UNKNOWN", index=True)
    classification_confidence = Column(Float, nullable=True)
    classification_evidence = Column(JSON, default=list)

    document_number = Column(String(64), index=True, nullable=True)
    normalized_document_number = Column(String(64), index=True, nullable=True)

    ground_truth = Column(String(16), nullable=True)  # GENUINE | ALTERED (eval only)
    created_at = Column(DateTime, default=utcnow, index=True)

    investigation = relationship("Investigation", back_populates="documents")
    person = relationship("Person", back_populates="documents")
    ocr_result = relationship("OcrResult", back_populates="document",
                              uselist=False, cascade="all, delete-orphan")
    mrz_result = relationship("MrzResult", back_populates="document",
                              uselist=False, cascade="all, delete-orphan")
    forensic_result = relationship("ForensicResult", back_populates="document",
                                   uselist=False, cascade="all, delete-orphan")
    face_result = relationship("FaceResult", back_populates="document",
                               uselist=False, cascade="all, delete-orphan")


class OcrResult(Base):
    __tablename__ = "ocr_results"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    engine = Column(String(32), nullable=True)
    raw_text = Column(Text, nullable=True)
    fields = Column(JSON, default=dict)     # {full_name, dob, nationality, ...}
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="ocr_result")


class MrzResult(Base):
    __tablename__ = "mrz_results"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    detected = Column(Boolean, default=False)
    mrz_type = Column(String(8), nullable=True)   # TD1 | TD2 | TD3
    raw_lines = Column(JSON, default=list)
    fields = Column(JSON, default=dict)
    checks = Column(JSON, default=dict)           # {document_number: PASS/FAIL, ...}
    valid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="mrz_result")


class ForensicResult(Base):
    __tablename__ = "forensic_results"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    signals = Column(JSON, default=list)          # [{signal,score,confidence,regions,description}]
    overall_score = Column(Float, nullable=True)  # 0..1
    suspicious = Column(Boolean, default=False)
    visualization_path = Column(String(255), nullable=True)  # ELA/overlay image (relative)
    ela_path = Column(String(255), nullable=True)
    metadata_findings = Column(JSON, default=list)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="forensic_result")


class FaceResult(Base):
    __tablename__ = "face_results"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    engine = Column(String(32), nullable=True)
    face_detected = Column(Boolean, default=False)
    num_faces = Column(Integer, default=0)
    face_crop_path = Column(String(255), nullable=True)
    reference_document_id = Column(Integer, nullable=True)
    similarity = Column(Float, nullable=True)   # 0..1
    match = Column(Boolean, nullable=True)
    confidence = Column(Float, nullable=True)
    status = Column(String(24), default="UNAVAILABLE")  # MATCH|NO_MATCH|UNAVAILABLE|NOT_DETECTED|NO_REFERENCE
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="face_result")


# ---------------------------------------------------------------------------
# Identity graph / cross-document links
# ---------------------------------------------------------------------------
class IdentityLink(Base):
    __tablename__ = "identity_links"

    id = Column(Integer, primary_key=True)
    investigation_id = Column(Integer, ForeignKey("investigations.id"), index=True)
    source_document_id = Column(Integer, nullable=True)
    target_document_id = Column(Integer, nullable=True)
    relation = Column(String(24), default="COMPARE")  # OWNS|CONTAINS|HAS_FACE|RELATED_TO|COMPARE
    attribute = Column(String(32), nullable=True)     # name|dob|nationality|face|...
    result = Column(String(16), nullable=True)        # MATCH|CONFLICT|WARNING|N/A
    detail = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)

    investigation = relationship("Investigation", back_populates="identity_links")


# ---------------------------------------------------------------------------
# Evidence & risk
# ---------------------------------------------------------------------------
class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True)
    investigation_id = Column(Integer, ForeignKey("investigations.id"), index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    type = Column(String(48), index=True)
    severity = Column(String(16))
    confidence = Column(Float, default=0.0)
    risk_contribution = Column(Integer, default=0)
    title = Column(String(255))
    description = Column(Text)
    source = Column(String(48))
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)

    investigation = relationship("Investigation", back_populates="evidence")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id = Column(Integer, primary_key=True)
    investigation_id = Column(Integer, ForeignKey("investigations.id"), index=True)
    score = Column(Float, default=0.0)
    level = Column(String(16), index=True)
    recommended_action = Column(String(32))
    contributors = Column(JSON, default=list)  # [{type,label,points,confidence}]
    disclaimer = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    investigation = relationship("Investigation", back_populates="risk_assessments")


# ---------------------------------------------------------------------------
# Human review
# ---------------------------------------------------------------------------
class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    investigation_id = Column(Integer, ForeignKey("investigations.id"), index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    reviewer = Column(String(128))
    decision = Column(String(32))
    notes = Column(Text, nullable=True)
    ai_recommendation = Column(String(32), nullable=True)
    ai_risk_level = Column(String(16), nullable=True)
    overridden = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow, index=True)

    investigation = relationship("Investigation", back_populates="reviews")


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------
class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    case_id = Column(String(32), unique=True, index=True)
    title = Column(String(255))
    status = Column(String(16), default="OPEN", index=True)
    risk_level = Column(String(16), nullable=True)
    risk_score = Column(Float, nullable=True)
    assigned_officer = Column(String(128), nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    resolved_at = Column(DateTime, nullable=True)

    investigations = relationship("Investigation", back_populates="case")


# ---------------------------------------------------------------------------
# Watchlist (synthetic demo only)
# ---------------------------------------------------------------------------
class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    document_number = Column(String(64))
    normalized_document_number = Column(String(64), index=True)
    document_type = Column(String(24), default="PASSPORT")
    status = Column(String(24), default="FLAGGED", index=True)
    reason = Column(Text, nullable=True)
    source = Column(String(64), default="SYNTHETIC_DEMO")
    notes = Column(Text, nullable=True)
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


Index("ix_watchlist_norm_active", Watchlist.normalized_document_number, Watchlist.active)


# ---------------------------------------------------------------------------
# Face reference gallery (enrolment: known-good embeddings by document number)
# ---------------------------------------------------------------------------
class FaceReference(Base):
    __tablename__ = "face_references"

    id = Column(Integer, primary_key=True)
    normalized_document_number = Column(String(64), index=True)
    embedding = Column(JSON)              # list[float] SFace descriptor
    source_document_id = Column(Integer, nullable=True)
    label = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    type = Column(String(32), index=True)
    title = Column(String(255))
    message = Column(Text)
    severity = Column(String(16), default="INFO")
    investigation_id = Column(Integer, nullable=True)
    read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=utcnow, index=True)
    event = Column(String(64), index=True)
    actor = Column(String(128), default="system")
    document_id = Column(Integer, nullable=True)
    investigation_id = Column(Integer, nullable=True, index=True)
    case_id = Column(Integer, nullable=True)
    details = Column(JSON, default=dict)
