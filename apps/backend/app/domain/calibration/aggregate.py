"""Persistent quality calibration metadata and human evaluation.

Calibration never reimplements prospect processing. It points at one existing
manual-CSV Discovery Task and its existing Prospect Batch, records the provider
modes used for that run, and owns only the human quality evaluation.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import ensure_utc, utcnow
from app.domain.exceptions import DomainError


class WebsiteFetchMode(StrEnum):
    REAL_HTTP = "real_http"
    FIXTURE = "fixture"


class ResearchProviderMode(StrEnum):
    REAL = "real"
    DETERMINISTIC_FAKE = "deterministic_fake"


class DraftProviderMode(StrEnum):
    REAL = "real"
    DETERMINISTIC_FAKE = "deterministic_fake"


class ContactSourceMode(StrEnum):
    OFFICIAL_WEBSITE = "official_website"


@dataclass(frozen=True, kw_only=True)
class CalibrationEvaluation:
    company_id: UUID
    research_accuracy: int
    opportunity_reasonableness: int
    contact_usability: int
    draft_personalization: int
    draft_professionalism: int
    ready_for_real_outreach: bool
    reviewer_name: str
    notes: str | None
    reviewed_at: datetime

    def __post_init__(self) -> None:
        for label, value in (
            ("research_accuracy", self.research_accuracy),
            ("opportunity_reasonableness", self.opportunity_reasonableness),
            ("contact_usability", self.contact_usability),
            ("draft_personalization", self.draft_personalization),
            ("draft_professionalism", self.draft_professionalism),
        ):
            if not 1 <= value <= 5:
                raise DomainError(f"{label} must be between 1 and 5")
        reviewer_name = self.reviewer_name.strip()
        if not reviewer_name:
            raise DomainError("calibration evaluation requires reviewer_name")
        if len(reviewer_name) > 200:
            raise DomainError("reviewer_name exceeds 200 characters")
        notes = self.notes.strip() if self.notes else None
        if notes is not None and len(notes) > 4000:
            raise DomainError("calibration notes exceed 4000 characters")
        object.__setattr__(self, "reviewer_name", reviewer_name)
        object.__setattr__(self, "notes", notes)
        object.__setattr__(
            self,
            "reviewed_at",
            ensure_utc(self.reviewed_at, field="reviewed_at"),
        )


class CalibrationRun:
    def __init__(
        self,
        *,
        id: UUID,
        discovery_task_id: UUID,
        prospect_batch_id: UUID,
        sample_count: int,
        website_fetch_mode: WebsiteFetchMode,
        research_provider_mode: ResearchProviderMode,
        draft_provider_mode: DraftProviderMode,
        contact_source_mode: ContactSourceMode,
        created_at: datetime,
        updated_at: datetime,
        evaluations: list[CalibrationEvaluation],
    ) -> None:
        if not 3 <= sample_count <= 5:
            raise DomainError("calibration sample_count must be between 3 and 5")
        self._id = id
        self._discovery_task_id = discovery_task_id
        self._prospect_batch_id = prospect_batch_id
        self._sample_count = sample_count
        self._website_fetch_mode = website_fetch_mode
        self._research_provider_mode = research_provider_mode
        self._draft_provider_mode = draft_provider_mode
        self._contact_source_mode = contact_source_mode
        self._created_at = ensure_utc(created_at, field="created_at")
        self._updated_at = ensure_utc(updated_at, field="updated_at")
        self._evaluations = evaluations

    @classmethod
    def create(
        cls,
        *,
        discovery_task_id: UUID,
        prospect_batch_id: UUID,
        sample_count: int,
        website_fetch_mode: WebsiteFetchMode,
        research_provider_mode: ResearchProviderMode,
        draft_provider_mode: DraftProviderMode,
        contact_source_mode: ContactSourceMode = ContactSourceMode.OFFICIAL_WEBSITE,
    ) -> "CalibrationRun":
        now = utcnow()
        return cls(
            id=uuid4(),
            discovery_task_id=discovery_task_id,
            prospect_batch_id=prospect_batch_id,
            sample_count=sample_count,
            website_fetch_mode=website_fetch_mode,
            research_provider_mode=research_provider_mode,
            draft_provider_mode=draft_provider_mode,
            contact_source_mode=contact_source_mode,
            created_at=now,
            updated_at=now,
            evaluations=[],
        )

    def record_evaluation(self, evaluation: CalibrationEvaluation) -> None:
        self._evaluations = [
            item for item in self._evaluations if item.company_id != evaluation.company_id
        ]
        self._evaluations.append(evaluation)
        self._updated_at = evaluation.reviewed_at

    def evaluation_for(self, company_id: UUID) -> CalibrationEvaluation | None:
        return next(
            (item for item in self._evaluations if item.company_id == company_id),
            None,
        )

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def discovery_task_id(self) -> UUID:
        return self._discovery_task_id

    @property
    def prospect_batch_id(self) -> UUID:
        return self._prospect_batch_id

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def website_fetch_mode(self) -> WebsiteFetchMode:
        return self._website_fetch_mode

    @property
    def research_provider_mode(self) -> ResearchProviderMode:
        return self._research_provider_mode

    @property
    def draft_provider_mode(self) -> DraftProviderMode:
        return self._draft_provider_mode

    @property
    def contact_source_mode(self) -> ContactSourceMode:
        return self._contact_source_mode

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def evaluations(self) -> tuple[CalibrationEvaluation, ...]:
        return tuple(sorted(self._evaluations, key=lambda item: str(item.company_id)))
