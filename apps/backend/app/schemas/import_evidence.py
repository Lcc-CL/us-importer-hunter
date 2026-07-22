"""HTTP contracts for the single-company Import Evidence MVP flow."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from app.workflows.import_evidence import EvidenceFlowStatus, EvidenceUploadOutcome


class EvidenceUploadResponse(BaseModel):
    status: EvidenceFlowStatus
    company_id: UUID
    import_job_id: UUID | None = None
    aggregate_id: UUID | None = None
    records_received: int = 0
    records_normalized: int = 0
    shipments_matched: int = 0
    quality_status: str | None = None
    quality_score: float | None = None
    promoted_signals: list[str] = Field(default_factory=list)
    previous_qualification_score: float | None = None
    qualification_score: float | None = None
    qualification_status: str | None = None
    qualification_reasons: list[str] = Field(default_factory=list)
    draft_status: str = "skipped"
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_outcome(cls, outcome: EvidenceUploadOutcome) -> Self:
        return cls(
            status=outcome.status,
            company_id=outcome.company_id,
            import_job_id=outcome.import_job_id,
            aggregate_id=outcome.aggregate_id,
            records_received=outcome.records_received,
            records_normalized=outcome.records_normalized,
            shipments_matched=outcome.shipments_matched,
            quality_status=outcome.quality_status,
            quality_score=outcome.quality_score,
            promoted_signals=list(outcome.promoted_signals),
            previous_qualification_score=outcome.previous_qualification_score,
            qualification_score=outcome.qualification_score,
            qualification_status=outcome.qualification_status,
            qualification_reasons=list(outcome.qualification_reasons),
            draft_status=outcome.draft_status,
            warnings=list(outcome.warnings),
        )
