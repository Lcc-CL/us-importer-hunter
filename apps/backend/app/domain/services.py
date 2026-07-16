"""Domain service protocols: business capabilities the domain needs but
cannot compute inside one aggregate.

Interfaces only — implementations live in app/services and are injected.
No provider-, LLM- or storage-specific detail belongs here.
"""

from collections.abc import Sequence  # noqa: TC003 — used in protocol signatures
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.values import (
    CompanyName,
    OpportunityAssessment,
    SourceReference,
    WebsiteUrl,
)

if TYPE_CHECKING:
    from app.domain.contact import (
        Contact,
        ContactMatch,
        DecisionMakerFitAssessment,
        JobTitle,
        PersonName,
    )


@dataclass(frozen=True)
class ContactChoice:
    """Result of contact selection: who, and why them."""

    contact_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class OpportunityScoringInput:
    """Everything a scorer may look at — an explicit facts snapshot.

    Scorers must not fetch anything else (no repository, no network):
    same input, same assessment.
    """

    company_id: UUID
    company_name: str
    website_host: str | None
    verified: bool
    signals: tuple[str, ...]
    sources: tuple[SourceReference, ...]
    scoring_version: str
    user_lens_version: str | None = None
    assessed_at: datetime = field(default_factory=utcnow)


class OpportunityScoringService(Protocol):
    """Computes an assessment from an explicit input snapshot.

    Deterministic and explainable by contract: the returned
    OpportunityAssessment is complete (score, confidence, priority,
    reasons, evidence, recommended action) and immutable; the scoring
    version identifies the algorithm.
    """

    @property
    def scoring_version(self) -> str: ...

    async def assess(self, scoring_input: OpportunityScoringInput) -> OpportunityAssessment: ...


class ContactSelectionService(Protocol):
    """Chooses the best recipient at a company for an outreach purpose."""

    async def select(self, company_id: UUID, purpose: str) -> ContactChoice | None:
        """Return the chosen contact and the selection reason, or None if nobody qualifies."""
        ...


class CompanyDeduplicationService(Protocol):
    """Finds whether a candidate company already exists canonically."""

    async def find_canonical(self, name: CompanyName, website: WebsiteUrl | None) -> UUID | None:
        """Return the canonical company id the candidate duplicates, or None."""
        ...


class ContactDeduplicationService(Protocol):
    """Is this candidate a person we already know at this company?

    Never matches on name alone across companies; conflicting channels
    demand a human (POSSIBLE_MATCH), not an automatic merge (ADR-0022).
    """

    async def classify(
        self,
        company_id: UUID,
        name: "PersonName",
        title: "JobTitle | None",
        email_normalized: str | None,
        linkedin_normalized: str | None,
    ) -> "ContactMatch": ...


class DecisionMakerSelectionService(Protocol):
    """Ranks a company's contacts as logistics decision makers.

    Deterministic and explainable: complete immutable fit assessments,
    weights owned by the versioned policy. No database, no network.
    """

    @property
    def policy_version(self) -> str: ...

    async def rank(self, contacts: "Sequence[Contact]") -> "tuple[DecisionMakerFitAssessment, ...]":
        """Assessments sorted best-first; ties broken deterministically."""
        ...
