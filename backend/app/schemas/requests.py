"""Pydantic request models (validate all API inputs)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.constants import (
    CaseStatus,
    DocumentType,
    ReviewDecision,
    WatchlistStatus,
)


class InvestigationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    assigned_officer: str | None = Field(default=None, max_length=128)


class WatchlistCreate(BaseModel):
    document_number: str = Field(min_length=1, max_length=64)
    document_type: str = Field(default=DocumentType.PASSPORT, max_length=24)
    status: str = Field(default=WatchlistStatus.FLAGGED, max_length=24)
    reason: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    source: str = Field(default="SYNTHETIC_DEMO", max_length=64)
    active: bool = True


class WatchlistUpdate(BaseModel):
    document_number: str | None = Field(default=None, max_length=64)
    document_type: str | None = Field(default=None, max_length=24)
    status: str | None = Field(default=None, max_length=24)
    reason: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    active: bool | None = None


class ReviewCreate(BaseModel):
    investigation_id: int
    decision: str = Field(description="One of CLEAR, SECONDARY_INSPECTION, SUSPICIOUS, INCONCLUSIVE")
    reviewer: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=4000)
    create_case: bool = False

    def valid_decision(self) -> bool:
        return self.decision in ReviewDecision.ALL


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    investigation_id: int | None = None
    assigned_officer: str | None = Field(default=None, max_length=128)
    status: str = Field(default=CaseStatus.OPEN, max_length=16)
    summary: str | None = Field(default=None, max_length=4000)


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=16)
    assigned_officer: str | None = Field(default=None, max_length=128)
    summary: str | None = Field(default=None, max_length=4000)
