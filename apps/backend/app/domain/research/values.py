"""Research value objects: what a website said, before it becomes a fact.

A research run produces *claims* (ADR-0025). Claims are not Company signals
and never become them without a human decision. Everything here is immutable
and validates at construction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.clock import ensure_utc, utcnow
from app.domain.exceptions import DomainError

#: The only signal kinds a claim may carry. Identical to the scorer's
#: dimensions plus pain_point, which is stored but never scored (ADR-0025).
ALLOWED_CLAIM_KINDS = frozenset(
    {
        "import_activity",
        "china_dependency",
        "shipping_fit",
        "cargo_value_potential",
        "company_scale",
        "growth_signal",
        "logistics_complexity",
        "pain_point",
    }
)


class ResearchRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


TERMINAL_RUN_STATUSES = frozenset(
    {ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL, ResearchRunStatus.FAILED}
)


class ResearchFailureCode(StrEnum):
    UNREACHABLE = "unreachable"
    ROBOTS_DENIED = "robots_denied"
    NEEDS_BROWSER = "needs_browser"
    BUDGET_EXCEEDED = "budget_exceeded"
    EXTRACTION_FAILED = "extraction_failed"
    INVALID_URL = "invalid_url"


class ClaimRejectionReason(StrEnum):
    """Why a proposed claim was refused. Rejection discards the claim; it is
    never downgraded into a low-confidence signal (ADR-0025 §5)."""

    UNKNOWN_KIND = "unknown_kind"
    UNFETCHED_SOURCE = "unfetched_source"
    SNIPPET_NOT_FOUND = "snippet_not_found"
    CONFIDENCE_OUT_OF_RANGE = "confidence_out_of_range"
    PAGE_NOT_IN_RUN = "page_not_in_run"
    EMPTY_FIELD = "empty_field"


class PromotionDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"


@dataclass(frozen=True)
class ResearchPage:
    """One page we actually fetched. `position` is its identity inside a run."""

    position: int
    url: str
    final_url: str
    http_status: int
    content_type: str
    fetched_at: datetime
    content_chars: int
    bytes_read: int = 0
    truncated: bool = False
    discovery_reason: str = "homepage"

    def __post_init__(self) -> None:
        if self.position < 0:
            raise DomainError("page position must be non-negative")
        if not self.url.strip():
            raise DomainError("page requires a url")
        if self.content_chars < 0 or self.bytes_read < 0:
            raise DomainError("page counters must be non-negative")
        object.__setattr__(self, "fetched_at", ensure_utc(self.fetched_at, field="fetched_at"))


@dataclass(frozen=True)
class ResearchClaim:
    """A validated claim: kind, the sentence supporting it, and where from.

    Construction enforces the invariants that do not need run context (kind,
    non-empty fields, confidence range). The two context-dependent rules —
    the source page belongs to this run, and the snippet really occurs in that
    page's cleaned text — are enforced by the validator, which has the run.
    """

    position: int
    kind: str
    detail: str
    evidence_snippet: str
    source_page_position: int
    confidence: float

    def __post_init__(self) -> None:
        if self.position < 0:
            raise DomainError("claim position must be non-negative")
        if self.kind not in ALLOWED_CLAIM_KINDS:
            raise DomainError(f"claim kind is not allowed: {self.kind!r}")
        for name, value in (
            ("detail", self.detail),
            ("evidence_snippet", self.evidence_snippet),
        ):
            if not value.strip():
                raise DomainError(f"claim requires a non-empty {name}")
        if not 0.0 <= self.confidence <= 1.0:
            raise DomainError(f"claim confidence must be within 0–1, got {self.confidence}")
        if self.source_page_position < 0:
            raise DomainError("claim must reference a page position")


@dataclass(frozen=True)
class RejectedClaim:
    """A proposal that failed validation, kept so extractor quality is
    measurable rather than invisible."""

    reason: ClaimRejectionReason
    kind: str
    detail: str
    warning: str

    def __post_init__(self) -> None:
        if not self.warning.strip():
            raise DomainError("a rejected claim requires a warning")


@dataclass(frozen=True)
class ResearchProfile:
    """Non-signal facts about the company, as stated by its own site."""

    summary: str | None = None
    industry: str | None = None
    products: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    size_hint: str | None = None
    year_founded: str | None = None
    mentions_importing: bool | None = None


@dataclass(frozen=True)
class ExtractorIdentity:
    """Which extractor produced a result — recorded on every run."""

    provider: str
    model: str
    prompt_version: str

    def __post_init__(self) -> None:
        for name, value in (
            ("provider", self.provider),
            ("model", self.model),
            ("prompt_version", self.prompt_version),
        ):
            if not value.strip():
                raise DomainError(f"extractor identity requires a {name}")


@dataclass(frozen=True)
class ProposedClaim:
    """What an extractor returned, before validation. Deliberately permissive:
    an extractor may propose nonsense, and the validator's job is to say no."""

    kind: str
    detail: str
    evidence_snippet: str
    source_url: str
    confidence: float


@dataclass(frozen=True)
class ExtractionResult:
    """One extractor call: a profile, some proposals, and what it could not
    determine. Unknown dimensions are named, never guessed."""

    profile: ResearchProfile
    claims: tuple[ProposedClaim, ...] = ()
    unknown_dimensions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchPromotion:
    """A human's decision about one claim, and where it landed.

    `company_id` / `company_signal_position` stay None until the confirmed
    payload is actually submitted and a company exists — that back-fill closes
    the trace from company signal to the page and sentence behind it.
    """

    claim_position: int
    decision: PromotionDecision
    reviewed_at: datetime = field(default_factory=utcnow)
    reviewer_name: str | None = None
    edited_detail: str | None = None
    company_id: object | None = None
    company_signal_position: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reviewed_at", ensure_utc(self.reviewed_at, field="reviewed_at"))
        if self.decision is PromotionDecision.EDITED and not (self.edited_detail or "").strip():
            raise DomainError("an edited promotion requires edited_detail")
        if self.decision is not PromotionDecision.EDITED and self.edited_detail is not None:
            raise DomainError("edited_detail is only valid for an edited promotion")
