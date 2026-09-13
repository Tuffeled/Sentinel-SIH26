"""Shared enums / constants used across services, models and API layers.

These are plain string constants (not Enum classes) so they serialise cleanly to
JSON, store cleanly in SQLite, and compare cleanly in Python.
"""
from __future__ import annotations


class DocumentType:
    PASSPORT = "PASSPORT"
    VISA = "VISA"
    NATIONAL_ID = "NATIONAL_ID"
    UNKNOWN = "UNKNOWN"
    ALL = (PASSPORT, VISA, NATIONAL_ID, UNKNOWN)


class RiskLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    ALL = (LOW, MEDIUM, HIGH, CRITICAL)


class Severity:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class StageStatus:
    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AnalysisStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScreeningStatus:
    """High level status shown in dashboards / history."""
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    VERIFIED = "VERIFIED"       # low risk, no review needed
    REVIEW = "REVIEW"          # needs officer review
    FLAGGED = "FLAGGED"        # high/critical
    FAILED = "FAILED"
    REVIEWED = "REVIEWED"      # officer completed a decision


class EvidenceType:
    MRZ_CHECKSUM_FAILURE = "MRZ_CHECKSUM_FAILURE"
    FIELD_MISMATCH = "FIELD_MISMATCH"
    OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
    FORENSIC_ANOMALY = "FORENSIC_ANOMALY"
    METADATA_ANOMALY = "METADATA_ANOMALY"
    FACE_LOW_SIMILARITY = "FACE_LOW_SIMILARITY"
    WATCHLIST_MATCH = "WATCHLIST_MATCH"
    CROSS_DOCUMENT_CONFLICT = "CROSS_DOCUMENT_CONFLICT"
    CLASSIFICATION_UNCERTAIN = "CLASSIFICATION_UNCERTAIN"
    MRZ_NOT_DETECTED = "MRZ_NOT_DETECTED"
    FACE_NOT_DETECTED = "FACE_NOT_DETECTED"


# Which evidence types map to which risk weight key (see settings.risk_weights).
EVIDENCE_WEIGHT_KEY = {
    EvidenceType.MRZ_CHECKSUM_FAILURE: "MRZ_CHECKSUM_FAILURE",
    EvidenceType.FIELD_MISMATCH: "FIELD_MISMATCH",
    EvidenceType.OCR_LOW_CONFIDENCE: "OCR_LOW_CONFIDENCE",
    EvidenceType.FORENSIC_ANOMALY: "FORENSIC_ANOMALY",
    EvidenceType.METADATA_ANOMALY: "METADATA_ANOMALY",
    EvidenceType.FACE_LOW_SIMILARITY: "FACE_LOW_SIMILARITY",
    EvidenceType.WATCHLIST_MATCH: "WATCHLIST_MATCH",
    EvidenceType.CROSS_DOCUMENT_CONFLICT: "CROSS_DOCUMENT_CONFLICT",
    EvidenceType.CLASSIFICATION_UNCERTAIN: "CLASSIFICATION_UNCERTAIN",
}


class WatchlistStatus:
    FLAGGED = "FLAGGED"
    STOLEN = "STOLEN"
    LOST = "LOST"
    SUSPICIOUS = "SUSPICIOUS"
    DUPLICATE = "DUPLICATE"
    REVOKED = "REVOKED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ALL = (FLAGGED, STOLEN, LOST, SUSPICIOUS, DUPLICATE, REVOKED, UNDER_REVIEW)


# Severity a watchlist status contributes when matched.
WATCHLIST_STATUS_SEVERITY = {
    WatchlistStatus.STOLEN: Severity.CRITICAL,
    WatchlistStatus.REVOKED: Severity.CRITICAL,
    WatchlistStatus.FLAGGED: Severity.HIGH,
    WatchlistStatus.LOST: Severity.HIGH,
    WatchlistStatus.DUPLICATE: Severity.HIGH,
    WatchlistStatus.SUSPICIOUS: Severity.MEDIUM,
    WatchlistStatus.UNDER_REVIEW: Severity.MEDIUM,
}


class CaseStatus:
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    ALL = (OPEN, UNDER_REVIEW, ESCALATED, RESOLVED)


class ReviewDecision:
    CLEAR = "CLEAR"
    SECONDARY_INSPECTION = "SECONDARY_INSPECTION"
    SUSPICIOUS = "SUSPICIOUS"
    INCONCLUSIVE = "INCONCLUSIVE"
    ALL = (CLEAR, SECONDARY_INSPECTION, SUSPICIOUS, INCONCLUSIVE)


class RecommendedAction:
    CLEAR = "CLEAR"
    ROUTINE_VERIFICATION = "ROUTINE_VERIFICATION"
    SECONDARY_INSPECTION = "SECONDARY_INSPECTION"
    ESCALATE = "ESCALATE"


class NotificationType:
    SCREENING_COMPLETE = "SCREENING_COMPLETE"
    HIGH_RISK = "HIGH_RISK"
    WATCHLIST_MATCH = "WATCHLIST_MATCH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    FACE_UNAVAILABLE = "FACE_UNAVAILABLE"


class GroundTruth:
    GENUINE = "GENUINE"
    ALTERED = "ALTERED"


# Ordered pipeline stages (key, human label). Drives the live analysis UI.
PIPELINE_STAGES = [
    ("received", "Document Received"),
    ("classification", "Classification"),
    ("ocr", "OCR"),
    ("mrz", "MRZ Validation"),
    ("field_consistency", "Field Consistency"),
    ("forensic", "Forensic Analysis"),
    ("face", "Face Verification"),
    ("watchlist", "Watchlist Lookup"),
    ("identity", "Identity Consistency"),
    ("risk", "Risk Assessment"),
]


def risk_level_for_score(score: float) -> str:
    if score >= 75:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def recommended_action_for(level: str, watchlist_hit: bool = False) -> str:
    if level == RiskLevel.CRITICAL:
        return RecommendedAction.ESCALATE
    if level == RiskLevel.HIGH:
        return RecommendedAction.SECONDARY_INSPECTION
    if level == RiskLevel.MEDIUM:
        return RecommendedAction.ROUTINE_VERIFICATION
    return RecommendedAction.CLEAR


def screening_status_for(level: str) -> str:
    if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return ScreeningStatus.FLAGGED
    if level == RiskLevel.MEDIUM:
        return ScreeningStatus.REVIEW
    return ScreeningStatus.VERIFIED
