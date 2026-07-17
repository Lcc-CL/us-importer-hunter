"""Domain events: immutable facts that already happened.

Aggregates collect these internally (`drain_events()`); publishing them
is the application layer's job — no event bus lives in the domain.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.values import OpportunityScore, Priority

if TYPE_CHECKING:
    # imported lazily to avoid package-init cycles (events ↔ discovery/contact);
    # dataclasses never resolve annotations at runtime
    from app.domain.contact.values import RawContactSnapshot
    from app.domain.discovery.values import DiscoveryResult, DiscoveryStats


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Common envelope. Events are facts — past tense, never commands."""

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, kw_only=True)
class CompanyVerified(DomainEvent):
    company_id: UUID


@dataclass(frozen=True, kw_only=True)
class CompanyDiscovered(DomainEvent):
    """A source claimed a company exists. The Company context consumes
    this (dedup + fact-merge); Discovery never creates companies."""

    run_id: UUID
    result: "DiscoveryResult"


@dataclass(frozen=True, kw_only=True)
class DiscoveryCompleted(DomainEvent):
    run_id: UUID
    stats: "DiscoveryStats"


@dataclass(frozen=True, kw_only=True)
class DiscoveryFailed(DomainEvent):
    run_id: UUID
    error: str
    stats: "DiscoveryStats"


@dataclass(frozen=True, kw_only=True)
class CompanyIngested(DomainEvent):
    """The ingestion workflow finished creating or merging a company.
    Application-layer fact consumed by the opportunity workflow."""

    company_id: UUID
    ingestion_result: Literal["created", "merged"]
    source: str


@dataclass(frozen=True, kw_only=True)
class CompanyFactsChanged(DomainEvent):
    """Facts relevant to opportunity judgment changed on a company.
    (Supersedes the earlier catalog name CompanyProfileUpdated.)"""

    company_id: UUID
    changed_fields: tuple[str, ...]
    reason: str


@dataclass(frozen=True, kw_only=True)
class ContactCandidateDiscovered(DomainEvent):
    """A source claimed a person exists — not yet a trusted contact."""

    candidate: "RawContactSnapshot"


@dataclass(frozen=True, kw_only=True)
class ContactCreated(DomainEvent):
    contact_id: UUID
    company_id: UUID


@dataclass(frozen=True, kw_only=True)
class ContactUpdated(DomainEvent):
    contact_id: UUID
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ContactChannelAdded(DomainEvent):
    contact_id: UUID
    channel_type: str
    normalized_value: str


@dataclass(frozen=True, kw_only=True)
class ContactChannelVerified(DomainEvent):
    contact_id: UUID
    channel_type: str
    normalized_value: str
    verification_status: str


@dataclass(frozen=True, kw_only=True)
class ContactInvalidated(DomainEvent):
    contact_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class ContactabilityChanged(DomainEvent):
    """Reachability of a company's people changed — feeds a later
    CompanyFactsChanged / reassessment of the CONTACTABILITY dimension."""

    company_id: UUID
    contact_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class DecisionMakerSelected(DomainEvent):
    """A best contact was chosen for an opportunity — consumed by the
    email draft workflow (next lesson)."""

    opportunity_id: UUID
    company_id: UUID
    contact_id: UUID
    recommended_channel: str | None
    policy_version: str


@dataclass(frozen=True, kw_only=True)
class OpportunityCreated(DomainEvent):
    opportunity_id: UUID
    company_id: UUID
    user_id: UUID


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
class EmailDraftGenerated(DomainEvent):
    """A draft is ready for human review — never auto-sent."""

    outreach_id: UUID
    draft_version: int
    prompt_version: str
    provider: str
    model: str


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
