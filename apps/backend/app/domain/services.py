"""Domain service protocols: business capabilities the domain needs but
cannot compute inside one aggregate.

Interfaces only — implementations live in app/services and are injected.
No provider-, LLM- or storage-specific detail belongs here.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from app.domain.values import CompanyName, OpportunityAssessment, WebsiteUrl

if TYPE_CHECKING:
    from app.domain.company.aggregate import Company


@dataclass(frozen=True)
class ContactChoice:
    """Result of contact selection: who, and why them."""

    contact_id: UUID
    reason: str


class OpportunityScoringService(Protocol):
    """Computes an assessment for a company through a user's lens.

    Deterministic and explainable by contract: same inputs, same
    assessment — the scoring version identifies the algorithm.
    """

    async def assess(self, company: "Company", user_lens_version: str) -> OpportunityAssessment:
        """Produce one immutable assessment (score, confidence, reasons, evidence)."""
        ...


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
