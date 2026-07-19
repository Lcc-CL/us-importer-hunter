"""ResearchRun aggregate: one attempt to research one website.

Owns its pages, claims, rejections and promotions. It never creates a Company
and never scores anything — a run is a proposal (ADR-0025).
"""

from datetime import datetime
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition
from app.domain.research.values import (
    ALLOWED_CLAIM_KINDS,
    TERMINAL_RUN_STATUSES,
    ClaimRejectionReason,
    ExtractorIdentity,
    OutputLanguage,
    PromotionDecision,
    RejectedClaim,
    ResearchClaim,
    ResearchFailureCode,
    ResearchPage,
    ResearchProfile,
    ResearchPromotion,
    ResearchRunStatus,
)


class ResearchRun:
    """Aggregate root. Status moves forward only."""

    def __init__(
        self,
        *,
        id: UUID,
        company_name: str,
        website: str,
        started_at: datetime,
        company_id: UUID | None = None,
        output_language: OutputLanguage = OutputLanguage.EN_US,
    ) -> None:
        self._id = id
        self._company_id = company_id
        self._output_language = output_language
        self._company_name = company_name
        self._website = website
        self._started_at = started_at
        self._completed_at: datetime | None = None
        self._status = ResearchRunStatus.CREATED
        self._failure_code: ResearchFailureCode | None = None
        self._pages: list[ResearchPage] = []
        self._claims: list[ResearchClaim] = []
        self._rejected: list[RejectedClaim] = []
        self._promotions: list[ResearchPromotion] = []
        self._profile = ResearchProfile()
        self._extractor: ExtractorIdentity | None = None
        self._warnings: list[str] = []
        self._unknown_dimensions: list[str] = []
        self._pages_failed = 0
        self._claims_extracted = 0

    # -- construction ---------------------------------------------------

    @classmethod
    def start(
        cls,
        company_name: str,
        website: str,
        *,
        company_id: UUID | None = None,
        output_language: OutputLanguage = OutputLanguage.EN_US,
    ) -> "ResearchRun":
        """`company_id` is optional: research also runs on prospects that are
        not in the database yet. company_name and website are always recorded
        as a snapshot of what was researched."""
        if not company_name.strip():
            raise DomainError("research run requires a company name")
        if not website.strip():
            raise DomainError("research run requires a website")
        return cls(
            id=uuid4(),
            company_id=company_id,
            company_name=company_name.strip(),
            website=website.strip(),
            started_at=utcnow(),
            output_language=output_language,
        )

    # -- behaviors ------------------------------------------------------

    def mark_running(self) -> None:
        if self._status is not ResearchRunStatus.CREATED:
            raise InvalidStateTransition(f"cannot start a {self._status.value} run")
        self._status = ResearchRunStatus.RUNNING

    def record_page(self, page: ResearchPage) -> None:
        if self._status in TERMINAL_RUN_STATUSES:
            raise InvalidStateTransition("cannot add pages to a finished run")
        if any(existing.position == page.position for existing in self._pages):
            raise DomainError(f"page position already recorded: {page.position}")
        self._pages.append(page)

    def record_page_failure(self, warning: str) -> None:
        self._pages_failed += 1
        self.add_warning(warning)

    def record_extraction(
        self,
        *,
        profile: ResearchProfile,
        extractor: ExtractorIdentity,
        proposed_count: int,
        unknown_dimensions: tuple[str, ...] = (),
    ) -> None:
        """Record what the extractor produced, including what it could *not*
        determine.

        Unknown dimensions are a first-class result, not an absence: naming
        them is how the run says "no evidence was found", as opposed to "this
        company is weak here". They never influence scoring (ADR-0025).

        A name outside the whitelist is dropped with a warning rather than
        stored — an unknown dimension nobody can map to a scoring dimension is
        noise, and silently keeping it would let a model invent categories.
        """
        self._profile = profile
        self._extractor = extractor
        self._claims_extracted = proposed_count

        kept: list[str] = []
        for name in unknown_dimensions:
            cleaned = name.strip()
            if not cleaned:
                continue
            if cleaned not in ALLOWED_CLAIM_KINDS:
                self.add_warning(f"unknown dimension {cleaned!r} dropped: not an allowed kind")
                continue
            if cleaned not in kept:
                kept.append(cleaned)
        self._unknown_dimensions = kept

    def record_claim(self, claim: ResearchClaim) -> None:
        """Add a claim that has already passed validation."""
        if self._status in TERMINAL_RUN_STATUSES:
            raise InvalidStateTransition("cannot add claims to a finished run")
        if not any(page.position == claim.source_page_position for page in self._pages):
            raise DomainError(
                f"claim cites page {claim.source_page_position}, which is not in this run"
            )
        if any(existing.position == claim.position for existing in self._claims):
            raise DomainError(f"claim position already recorded: {claim.position}")
        self._claims.append(claim)

    def record_rejection(self, rejection: RejectedClaim) -> None:
        self._rejected.append(rejection)
        self.add_warning(rejection.warning)

    def add_warning(self, warning: str) -> None:
        if warning.strip():
            self._warnings.append(warning.strip())

    def complete(
        self, *, partial: bool = False, failure_code: ResearchFailureCode | None = None
    ) -> None:
        if self._status in TERMINAL_RUN_STATUSES:
            raise InvalidStateTransition(f"run is already {self._status.value}")
        self._status = ResearchRunStatus.PARTIAL if partial else ResearchRunStatus.COMPLETED
        self._failure_code = failure_code
        self._completed_at = utcnow()

    def fail(self, code: ResearchFailureCode, reason: str) -> None:
        if self._status in TERMINAL_RUN_STATUSES:
            raise InvalidStateTransition(f"run is already {self._status.value}")
        self._status = ResearchRunStatus.FAILED
        self._failure_code = code
        self._completed_at = utcnow()
        self.add_warning(reason)

    def record_promotion(self, promotion: ResearchPromotion) -> None:
        """Persist a human decision about one claim. Rejections are recorded
        too — they are the only evidence of extractor precision."""
        if not any(claim.position == promotion.claim_position for claim in self._claims):
            raise DomainError(
                f"promotion references unknown claim position {promotion.claim_position}"
            )
        if any(p.claim_position == promotion.claim_position for p in self._promotions):
            raise DomainError(
                f"claim {promotion.claim_position} has already been reviewed"
            )
        self._promotions.append(promotion)

    def revise_promotion(self, promotion: ResearchPromotion) -> None:
        """Replace a decision that has not yet written into a Company.

        Once a promotion has produced company rows it is frozen: changing it
        would orphan a signal whose provenance no longer matches. Callers get
        a conflict instead (rule 7).
        """
        existing = self.promotion_for(promotion.claim_position)
        if existing is None:
            raise DomainError(
                f"no promotion to revise for claim {promotion.claim_position}"
            )
        if existing.applied_to_company:
            raise InvalidStateTransition(
                f"claim {promotion.claim_position} was already applied to a company"
            )
        self._promotions = [
            promotion if p.claim_position == promotion.claim_position else p
            for p in self._promotions
        ]

    def promotion_for(self, claim_position: int) -> ResearchPromotion | None:
        return next(
            (p for p in self._promotions if p.claim_position == claim_position), None
        )

    def claim_at(self, position: int) -> ResearchClaim | None:
        return next((claim for claim in self._claims if claim.position == position), None)

    # -- read-only state ------------------------------------------------

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def company_id(self) -> UUID | None:
        return self._company_id

    @property
    def company_name(self) -> str:
        return self._company_name

    @property
    def website(self) -> str:
        return self._website

    @property
    def output_language(self) -> OutputLanguage:
        """Language of the conclusions, persisted so a reloaded run reads the
        same way it did when it was produced."""
        return self._output_language

    @property
    def status(self) -> ResearchRunStatus:
        return self._status

    @property
    def failure_code(self) -> ResearchFailureCode | None:
        return self._failure_code

    @property
    def started_at(self) -> datetime:
        return self._started_at

    @property
    def completed_at(self) -> datetime | None:
        return self._completed_at

    @property
    def pages(self) -> tuple[ResearchPage, ...]:
        return tuple(self._pages)

    @property
    def claims(self) -> tuple[ResearchClaim, ...]:
        return tuple(self._claims)

    @property
    def rejected_claims(self) -> tuple[RejectedClaim, ...]:
        return tuple(self._rejected)

    @property
    def promotions(self) -> tuple[ResearchPromotion, ...]:
        return tuple(self._promotions)

    @property
    def profile(self) -> ResearchProfile:
        return self._profile

    @property
    def extractor(self) -> ExtractorIdentity | None:
        return self._extractor

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    @property
    def unknown_dimensions(self) -> tuple[str, ...]:
        """Dimensions the extractor found no reliable evidence for. Never a
        negative signal and never an input to scoring."""
        return tuple(self._unknown_dimensions)

    @property
    def pages_fetched(self) -> int:
        return len(self._pages)

    @property
    def pages_failed(self) -> int:
        return self._pages_failed

    @property
    def claims_extracted(self) -> int:
        return self._claims_extracted

    @property
    def claims_validated(self) -> int:
        return len(self._claims)

    def page_at(self, position: int) -> ResearchPage | None:
        return next((page for page in self._pages if page.position == position), None)

    def accepted_promotions(self) -> tuple[ResearchPromotion, ...]:
        return tuple(
            promotion
            for promotion in self._promotions
            if promotion.decision in (PromotionDecision.ACCEPTED, PromotionDecision.EDITED)
        )

    def rejection_reasons(self) -> tuple[ClaimRejectionReason, ...]:
        return tuple(rejection.reason for rejection in self._rejected)
