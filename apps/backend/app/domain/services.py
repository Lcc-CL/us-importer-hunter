"""Domain service protocols: business capabilities the domain needs but
cannot compute inside one aggregate.

Interfaces only — implementations live in app/services and are injected.
No provider-, LLM- or storage-specific detail belongs here.
"""

import hashlib
import json
from collections.abc import Sequence  # noqa: TC003 — used in protocol signatures
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError
from app.domain.import_evidence.models import ImportEvidenceScoringProjection
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
    signal_selection_reasons: tuple[str, ...] = ()
    assessed_at: datetime = field(default_factory=utcnow)


class ImportEvidenceProjectionReader(Protocol):
    async def read_for_company(self, company_id: UUID) -> ImportEvidenceScoringProjection: ...


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


@dataclass(frozen=True, kw_only=True)
class SenderProfile:
    """Who the email is from — the forwarder's selling identity (MVP slice)."""

    name: str
    company: str
    value_proposition: str

    def __post_init__(self) -> None:
        for label, value in (
            ("name", self.name),
            ("company", self.company),
            ("value_proposition", self.value_proposition),
        ):
            if not value.strip():
                raise DomainError(f"sender profile requires a non-empty {label}")


@dataclass(frozen=True, kw_only=True)
class EmailGenerationContext:
    """Everything the email generator may look at — nothing else.

    Deliberately minimal (L11): no ORM objects, no full aggregates, no
    page HTML. Only facts that exist; the prompt forbids inventing more.
    """

    company_name: str
    website: str | None
    contact_name: str
    contact_title: str | None
    opportunity_score: float
    qualification_decision: str
    opportunity_reasons: tuple[str, ...]
    available_evidence: tuple[str, ...]
    sender_name: str
    sender_company: str
    sender_value_proposition: str

    def fingerprint(self) -> str:
        """SHA-256 over canonical content: same context → same fingerprint."""
        canonical = json.dumps(
            {
                "company_name": self.company_name,
                "website": self.website,
                "contact_name": self.contact_name,
                "contact_title": self.contact_title,
                "opportunity_score": self.opportunity_score,
                "qualification_decision": self.qualification_decision,
                "opportunity_reasons": list(self.opportunity_reasons),
                "available_evidence": list(self.available_evidence),
                "sender_name": self.sender_name,
                "sender_company": self.sender_company,
                "sender_value_proposition": self.sender_value_proposition,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GeneratedEmail:
    """The generator's output: subject + body, nothing provider-specific."""

    subject: str
    body: str

    def __post_init__(self) -> None:
        if not self.subject.strip() or not self.body.strip():
            raise DomainError("generated email requires a subject and a body")


class EmailDraftGenerator(Protocol):
    """Turns an EmailGenerationContext into one draft. Implementations
    (fake, OpenAI) live in app/services/email; SDK types never leak."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def generate(self, context: EmailGenerationContext) -> GeneratedEmail: ...


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

    async def rank(
        self, contacts: "Sequence[Contact]", **kwargs: Any
    ) -> "tuple[DecisionMakerFitAssessment, ...]":
        """Assessments sorted best-first; ties broken deterministically."""

    def score_all(self, contacts: "Sequence[Contact]") -> "tuple[Any, ...]":
        """Score every contact without ranking. Returns CandidateScore-equivalent objects."""
        ...
