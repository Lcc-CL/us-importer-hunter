"""HTTP contracts for D1 importer discovery tasks."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.domain.discovery import DiscoveryCandidate, DiscoveryTask

NonBlankPrompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DiscoveryTaskCreateRequest(BaseModel):
    prompt: NonBlankPrompt


class DiscoveryTaskResponse(BaseModel):
    task_id: UUID
    original_prompt: str
    requested_count: int
    effective_count: int
    parsed_region: str
    parsed_category: str
    parsed_keywords: list[str]
    provider: str
    status: str
    discovered_count: int
    ingested_count: int
    duplicate_count: int
    failed_count: int
    error_code: str | None
    error_summary: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_domain(cls, task: DiscoveryTask) -> Self:
        return cls(
            task_id=task.id,
            original_prompt=task.original_prompt,
            requested_count=task.requested_count,
            effective_count=task.effective_count,
            parsed_region=task.parsed_region,
            parsed_category=task.parsed_category,
            parsed_keywords=list(task.parsed_keywords),
            provider=task.provider,
            status=task.status.value,
            discovered_count=task.discovered_count,
            ingested_count=task.ingested_count,
            duplicate_count=task.duplicate_count,
            failed_count=task.failed_count,
            error_code=task.error_code,
            error_summary=task.error_summary,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
        )


class DiscoveryCompanyResponse(BaseModel):
    candidate_id: UUID
    position: int
    company_id: UUID | None
    company_name: str
    website: str | None
    domain: str | None
    address: str | None
    region: str | None
    product_description: str | None
    import_evidence: str | None
    source: str
    source_url: str | None
    external_id: str | None
    status: str
    is_duplicate: bool
    failure_reason: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, candidate: DiscoveryCandidate) -> Self:
        return cls(
            candidate_id=candidate.id,
            position=candidate.position,
            company_id=candidate.company_id,
            company_name=candidate.company_name,
            website=candidate.website,
            domain=candidate.normalized_domain,
            address=candidate.address,
            region=candidate.region,
            product_description=candidate.product_description,
            import_evidence=candidate.import_evidence,
            source=candidate.source,
            source_url=candidate.source_url,
            external_id=candidate.external_id,
            status=candidate.status.value,
            is_duplicate=candidate.status.value == "duplicate",
            failure_reason=candidate.failure_reason,
            created_at=candidate.created_at,
        )


class DiscoveryCompanyListResponse(BaseModel):
    task_id: UUID
    companies: list[DiscoveryCompanyResponse] = Field(default_factory=list)
