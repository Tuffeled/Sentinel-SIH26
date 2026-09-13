"""Deterministic, explainable risk engine.

* No randomness.
* Per-type de-duplication: related evidence of the same type is counted once at
  its strongest contribution, preventing double-counting.
* Score normalised to 0–100 with fixed level thresholds.
* Stores the individual contributors for full explainability.
"""
from __future__ import annotations

from ..core.constants import (
    EvidenceType,
    RiskLevel,
    recommended_action_for,
    risk_level_for_score,
)

DISCLAIMER = (
    "Risk assessment is an analytical aid produced by combining multiple "
    "independent signals. It does not constitute a final determination. The "
    "authorised officer remains responsible for the decision."
)

# Human labels for contributors.
_LABELS = {
    EvidenceType.MRZ_CHECKSUM_FAILURE: "MRZ checksum failure",
    EvidenceType.FIELD_MISMATCH: "Field mismatch",
    EvidenceType.FORENSIC_ANOMALY: "Forensic anomaly",
    EvidenceType.METADATA_ANOMALY: "Metadata anomaly",
    EvidenceType.FACE_LOW_SIMILARITY: "Face mismatch",
    EvidenceType.WATCHLIST_MATCH: "Watchlist match",
    EvidenceType.CROSS_DOCUMENT_CONFLICT: "Cross-document conflict",
    EvidenceType.OCR_LOW_CONFIDENCE: "OCR uncertainty",
    EvidenceType.CLASSIFICATION_UNCERTAIN: "Classification uncertainty",
}


class RiskEngine:
    """Swappable risk engine (weights come from configuration)."""

    def calculate(self, evidence: list[dict]) -> dict:
        # Group by type, keep the strongest (max risk_contribution) per type.
        per_type: dict[str, dict] = {}
        for ev in evidence:
            etype = ev.get("type")
            contrib = int(ev.get("risk_contribution", 0) or 0)
            if contrib <= 0:
                continue
            if etype not in per_type or contrib > per_type[etype]["points"]:
                per_type[etype] = {
                    "type": etype,
                    "label": _LABELS.get(etype, etype),
                    "points": contrib,
                    "confidence": ev.get("confidence", 0),
                    "severity": ev.get("severity"),
                }

        contributors = sorted(per_type.values(), key=lambda c: c["points"], reverse=True)
        raw = sum(c["points"] for c in contributors)
        score = float(min(100, max(0, raw)))
        level = risk_level_for_score(score)
        watchlist_hit = EvidenceType.WATCHLIST_MATCH in per_type
        action = recommended_action_for(level, watchlist_hit)

        return {
            "score": round(score, 1),
            "level": level,
            "recommended_action": action,
            "contributors": contributors,
            "raw_total": raw,
            "disclaimer": DISCLAIMER,
            "watchlist_hit": watchlist_hit,
        }


risk_engine = RiskEngine()


def calculate(evidence: list[dict]) -> dict:
    return risk_engine.calculate(evidence)
