"""Domain events: immutable facts that already happened.

Aggregates collect these internally (`drain_events()`); publishing them
is the application layer's job — no event bus lives in the domain.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.values import OpportunityScore, Priority


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Common envelope. Events are facts — past tense, never commands."""

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, kw_only=True)
class CompanyVerified(DomainEvent):
    company_id: UUID


@dataclass(frozen=True, kw_only=True)
class OpportunityAssessmentApplied(DomainEvent):
    opportunity_id: UUID
    company_id: UUID
    old_score: OpportunityScore | None
    new_score: OpportunityScore
    scoring_version: str


@dataclass(frozen=True, kw_only=True)
class OpportunityQualified(DomainEvent):
    opportunity_id: UUID
    company_id: UUID
    score: OpportunityScore
    priority: Priority


@dataclass(frozen=True, kw_only=True)
class OpportunityDisqualified(DomainEvent):
    opportunity_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class OutreachApproved(DomainEvent):
    outreach_id: UUID
    draft_version: int


@dataclass(frozen=True, kw_only=True)
class OutreachSent(DomainEvent):
    outreach_id: UUID
    draft_version: int


@dataclass(frozen=True, kw_only=True)
class OutreachReplied(DomainEvent):
    outreach_id: UUID
    sentiment: str


@dataclass(frozen=True, kw_only=True)
class OpportunityWon(DomainEvent):
    opportunity_id: UUID
    outreach_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class OpportunityLost(DomainEvent):
    opportunity_id: UUID
    outreach_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class TaskStarted(DomainEvent):
    task_id: UUID
    attempt: int


@dataclass(frozen=True, kw_only=True)
class TaskCompleted(DomainEvent):
    task_id: UUID


@dataclass(frozen=True, kw_only=True)
class TaskFailed(DomainEvent):
    task_id: UUID
    error: str
    attempts: int
