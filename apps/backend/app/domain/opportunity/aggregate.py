"""Opportunity aggregate (Intelligence context): the judgment about a company.

The central value aggregate of the product (ADR-0015/0016). Invariants:
- Score 0–100, confidence 0–1 (enforced by value objects).
- Every assessment carries a scoring version.
- The score changes only via apply_assessment — each change appends to an
  append-only history. No history entry, no score change.
- Qualification requires evidence and reasons; disqualification requires a
  reason; closed opportunities change only through an explicit reopen.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.events import (
    DomainEvent,
    OpportunityAssessmentApplied,
    OpportunityDisqualified,
    OpportunityQualified,
)
from app.domain.exceptions import (
    DomainError,
    InvalidStateTransition,
    MissingEvidence,
)
from app.domain.values import Confidence, OpportunityAssessment, OpportunityScore, Priority


class OpportunityStage(StrEnum):
    IDENTIFIED = "identified"
    ASSESSED = "assessed"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    WON = "won"
    LOST = "lost"


CLOSED_STAGES = frozenset(
    {OpportunityStage.DISQUALIFIED, OpportunityStage.WON, OpportunityStage.LOST}
)


class Opportunity:
    """Aggregate root. The score is untouchable except through behaviors."""

    def __init__(
        self,
        *,
        id: UUID,
        company_id: UUID,
        user_id: UUID,
        created_at: datetime,
    ) -> None:
        self._id = id
        self._company_id = company_id
        self._user_id = user_id
        self._created_at = created_at
        self._stage = OpportunityStage.IDENTIFIED
        self._stage_reason: str | None = None
        self._score: OpportunityScore | None = None
        self._confidence: Confidence | None = None
        self._priority: Priority | None = None
        self._history: list[OpportunityAssessment] = []
        self._events: list[DomainEvent] = []

    # -- construction -------------------------------------------------

    @classmethod
    def create_for_company(cls, company_id: UUID, user_id: UUID) -> "Opportunity":
        return cls(id=uuid4(), company_id=company_id, user_id=user_id, created_at=utcnow())

    # -- behaviors ----------------------------------------------------

    def apply_assessment(self, assessment: OpportunityAssessment) -> None:
        """The only way the score ever changes."""
        if self._stage in CLOSED_STAGES:
            raise InvalidStateTransition(
                f"cannot assess a {self._stage.value} opportunity — reopen it first"
            )
        self._history.append(assessment)
        old_score = self._score
        self._score = assessment.new_score
        self._confidence = assessment.confidence
        self._priority = Priority.from_score(assessment.new_score)
        if self._stage is OpportunityStage.IDENTIFIED:
            self._stage = OpportunityStage.ASSESSED
        self._events.append(
            OpportunityAssessmentApplied(
                opportunity_id=self._id,
                company_id=self._company_id,
                old_score=old_score,
                new_score=assessment.new_score,
                scoring_version=assessment.scoring_version,
            )
        )

    def qualify(self) -> None:
        if self._stage is not OpportunityStage.ASSESSED:
            raise InvalidStateTransition(
                f"cannot qualify from {self._stage.value} — an assessment is required first"
            )
        latest = self._history[-1]
        if not latest.evidence:
            raise MissingEvidence("qualification requires evidence on the latest assessment")
        assert self._score is not None and self._priority is not None
        self._stage = OpportunityStage.QUALIFIED
        self._events.append(
            OpportunityQualified(
                opportunity_id=self._id,
                company_id=self._company_id,
                score=self._score,
                priority=self._priority,
            )
        )

    def disqualify(self, reason: str) -> None:
        if not reason.strip():
            raise DomainError("disqualification requires a reason")
        if self._stage in CLOSED_STAGES:
            raise InvalidStateTransition(f"opportunity is already {self._stage.value}")
        self._stage = OpportunityStage.DISQUALIFIED
        self._stage_reason = reason.strip()
        self._events.append(OpportunityDisqualified(opportunity_id=self._id, reason=reason.strip()))

    def reopen(self, trigger: str) -> None:
        """Closed opportunities come back only through this explicit operation."""
        if not trigger.strip():
            raise DomainError("reopening requires a trigger")
        if self._stage not in CLOSED_STAGES:
            raise InvalidStateTransition(f"cannot reopen an open ({self._stage.value}) opportunity")
        self._stage = OpportunityStage.ASSESSED if self._history else OpportunityStage.IDENTIFIED
        self._stage_reason = None

    # -- events -------------------------------------------------------

    def drain_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    # -- read-only state ----------------------------------------------

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def company_id(self) -> UUID:
        return self._company_id

    @property
    def user_id(self) -> UUID:
        return self._user_id

    @property
    def stage(self) -> OpportunityStage:
        return self._stage

    @property
    def stage_reason(self) -> str | None:
        return self._stage_reason

    @property
    def score(self) -> OpportunityScore | None:
        return self._score

    @property
    def confidence(self) -> Confidence | None:
        return self._confidence

    @property
    def priority(self) -> Priority | None:
        return self._priority

    @property
    def history(self) -> tuple[OpportunityAssessment, ...]:
        """Append-only: exposed as an immutable snapshot."""
        return tuple(self._history)

    @property
    def created_at(self) -> datetime:
        return self._created_at
