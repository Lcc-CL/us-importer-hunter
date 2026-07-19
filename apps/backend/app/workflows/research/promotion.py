"""Claim review and promotion: a human's decisions become company facts.

This is the only place where research output is allowed to touch a Company,
and it does so under strict rules (ADR-0025):

- one transaction for the whole batch — all decisions land or none do;
- a rejected claim never produces a Source or a Signal;
- a decision that already wrote company rows is frozen; changing it would
  orphan a signal whose provenance no longer matches, so callers get a
  conflict instead;
- qualification, decision-maker selection and draft generation are never
  called from here. Promotion records facts; scoring is a separate act.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.company import Company
from app.domain.repositories import UnitOfWork
from app.domain.research import (
    ALLOWED_CLAIM_KINDS,
    PromotionDecision,
    ResearchClaim,
    ResearchPromotion,
    ResearchRun,
)
from app.domain.values import SourceReference


class PromotionError(Exception):
    """Base class for review failures that callers must distinguish."""


class ResearchRunNotFound(PromotionError):
    pass


class CompanyNotFound(PromotionError):
    pass


class InvalidDecision(PromotionError):
    """The request is malformed: unknown claim, bad kind, empty detail."""


class PromotionConflict(PromotionError):
    """The request contradicts a decision that has already been applied."""


class ReviewAction(StrEnum):
    APPLIED = "applied"       # decisions written, company rows created
    RECORDED = "recorded"     # decisions written, no company to apply them to
    UNCHANGED = "unchanged"   # identical request replayed — nothing to do


@dataclass(frozen=True)
class ClaimDecision:
    """One reviewer verdict. `edited_kind` defaults to the claim's own kind."""

    claim_position: int
    decision: PromotionDecision
    edited_detail: str | None = None
    edited_kind: str | None = None


@dataclass(frozen=True)
class ReviewRequest:
    research_run_id: UUID
    reviewer_name: str
    decisions: tuple[ClaimDecision, ...]
    target_company_id: UUID | None = None


@dataclass(frozen=True)
class PromotionResult:
    claim_position: int
    decision: PromotionDecision
    kind: str
    detail: str
    company_source_position: int | None = None
    company_signal_position: int | None = None
    source_reused: bool = False
    idempotent: bool = False


@dataclass(frozen=True)
class ProspectFormPayload:
    """What phase 4 will drop into the existing prospect form when there is no
    company to write to yet."""

    company_name: str
    website: str
    sources: tuple[dict[str, str], ...]
    signals: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ReviewOutcome:
    action: ReviewAction
    research_id: UUID
    company_id: UUID | None
    accepted: int
    edited: int
    rejected: int
    results: tuple[PromotionResult, ...]
    application_payload: ProspectFormPayload | None = None
    warnings: tuple[str, ...] = ()


@dataclass
class ClaimPromotionWorkflow:
    uow_factory: Callable[[], UnitOfWork]

    async def handle(self, request: ReviewRequest) -> ReviewOutcome:
        """One transaction: read the run, validate everything, then write."""
        async with self.uow_factory() as uow:
            run = await uow.research_runs.get_by_id(request.research_run_id)
            if run is None:
                raise ResearchRunNotFound(f"research run not found: {request.research_run_id}")

            company_id = self._target_company(run, request)
            company: Company | None = None
            if company_id is not None:
                company = await uow.companies.get_by_id(company_id)
                if company is None:
                    raise CompanyNotFound(f"company not found: {company_id}")

            # --- validate the whole batch before writing anything ---
            planned = [self._plan(run, decision) for decision in request.decisions]
            replay = self._classify_replays(run, planned)
            if replay is not None:
                return replay

            warnings: list[str] = []
            results: list[PromotionResult] = []
            for claim, decision in planned:
                promotion, result = self._apply_one(
                    run=run,
                    claim=claim,
                    decision=decision,
                    reviewer_name=request.reviewer_name,
                    company=company,
                    company_id=company_id,
                    warnings=warnings,
                )
                if run.promotion_for(decision.claim_position) is None:
                    run.record_promotion(promotion)
                else:
                    run.revise_promotion(promotion)
                results.append(result)

            await uow.research_runs.save(run)
            if company is not None:
                await uow.companies.save(company)
            await uow.commit()

        return ReviewOutcome(
            action=ReviewAction.APPLIED if company_id else ReviewAction.RECORDED,
            research_id=run.id,
            company_id=company_id,
            accepted=sum(1 for _, d in planned if d.decision is PromotionDecision.ACCEPTED),
            edited=sum(1 for _, d in planned if d.decision is PromotionDecision.EDITED),
            rejected=sum(1 for _, d in planned if d.decision is PromotionDecision.REJECTED),
            results=tuple(results),
            application_payload=(
                None if company_id else self._payload(run, planned)
            ),
            warnings=tuple(warnings),
        )

    # -- validation ------------------------------------------------------

    def _target_company(self, run: ResearchRun, request: ReviewRequest) -> UUID | None:
        """A run bound to a company wins; a mismatch is a conflict, not a
        silent redirect of someone's evidence onto the wrong company."""
        if run.company_id is not None:
            if (
                request.target_company_id is not None
                and request.target_company_id != run.company_id
            ):
                raise PromotionConflict(
                    f"run is bound to company {run.company_id}, "
                    f"but target_company_id is {request.target_company_id}"
                )
            return run.company_id
        return request.target_company_id

    def _plan(
        self, run: ResearchRun, decision: ClaimDecision
    ) -> tuple[ResearchClaim, ClaimDecision]:
        claim = run.claim_at(decision.claim_position)
        if claim is None:
            raise InvalidDecision(
                f"claim {decision.claim_position} does not belong to run {run.id}"
            )
        if decision.decision is PromotionDecision.EDITED:
            if not (decision.edited_detail or "").strip():
                raise InvalidDecision(
                    f"claim {decision.claim_position}: an edited decision requires a detail"
                )
            kind = decision.edited_kind or claim.kind
            if kind not in ALLOWED_CLAIM_KINDS:
                raise InvalidDecision(
                    f"claim {decision.claim_position}: kind {kind!r} is not allowed"
                )
        elif decision.edited_detail is not None or decision.edited_kind is not None:
            raise InvalidDecision(
                f"claim {decision.claim_position}: only an edited decision may carry edits"
            )
        return claim, decision

    def _classify_replays(
        self, run: ResearchRun, planned: list[tuple[ResearchClaim, ClaimDecision]]
    ) -> ReviewOutcome | None:
        """Replaying the same request is a no-op; contradicting an applied
        decision is a conflict. Both are decided before anything is written."""
        existing_matches = 0
        for _claim, decision in planned:
            existing = run.promotion_for(decision.claim_position)
            if existing is None:
                continue
            same = existing.decision is decision.decision and (
                existing.edited_detail or ""
            ) == (decision.edited_detail or "")
            if same:
                existing_matches += 1
                continue
            if existing.applied_to_company:
                raise PromotionConflict(
                    f"claim {decision.claim_position} was already applied to company "
                    f"{existing.company_id} as {existing.decision.value}"
                )

        if existing_matches == len(planned) and planned:
            return ReviewOutcome(
                action=ReviewAction.UNCHANGED,
                research_id=run.id,
                company_id=run.company_id,
                accepted=sum(
                    1 for _, d in planned if d.decision is PromotionDecision.ACCEPTED
                ),
                edited=sum(1 for _, d in planned if d.decision is PromotionDecision.EDITED),
                rejected=sum(
                    1 for _, d in planned if d.decision is PromotionDecision.REJECTED
                ),
                results=tuple(
                    self._result_from_existing(run, claim, decision)
                    for claim, decision in planned
                ),
                warnings=("identical review already recorded — nothing changed",),
            )
        return None

    @staticmethod
    def _result_from_existing(
        run: ResearchRun, claim: ResearchClaim, decision: ClaimDecision
    ) -> PromotionResult:
        existing = run.promotion_for(decision.claim_position)
        assert existing is not None
        return PromotionResult(
            claim_position=claim.position,
            decision=existing.decision,
            kind=existing.edited_kind or claim.kind,
            detail=existing.edited_detail or claim.detail,
            company_source_position=existing.company_source_position,
            company_signal_position=existing.company_signal_position,
            idempotent=True,
        )

    # -- writing ---------------------------------------------------------

    def _apply_one(
        self,
        *,
        run: ResearchRun,
        claim: ResearchClaim,
        decision: ClaimDecision,
        reviewer_name: str,
        company: Company | None,
        company_id: UUID | None,
        warnings: list[str],
    ) -> tuple[ResearchPromotion, PromotionResult]:
        kind = (
            decision.edited_kind or claim.kind
            if decision.decision is PromotionDecision.EDITED
            else claim.kind
        )
        detail = (
            str(decision.edited_detail).strip()
            if decision.decision is PromotionDecision.EDITED
            else claim.detail
        )

        # A rejected claim never reaches company data (rule 5).
        if decision.decision is PromotionDecision.REJECTED or company is None:
            promotion = ResearchPromotion(
                claim_position=claim.position,
                decision=decision.decision,
                reviewer_name=reviewer_name,
                edited_detail=(
                    detail if decision.decision is PromotionDecision.EDITED else None
                ),
                edited_kind=(
                    kind if decision.decision is PromotionDecision.EDITED else None
                ),
                company_id=None if decision.decision is PromotionDecision.REJECTED else company_id,
            )
            return promotion, PromotionResult(
                claim_position=claim.position,
                decision=decision.decision,
                kind=kind,
                detail=detail,
            )

        source_position, reused = self._ensure_source(company, run, claim, warnings)
        signal_position = _add_signal(company, f"{kind}: {detail}")

        promotion = ResearchPromotion(
            claim_position=claim.position,
            decision=decision.decision,
            reviewer_name=reviewer_name,
            edited_detail=detail if decision.decision is PromotionDecision.EDITED else None,
            edited_kind=kind if decision.decision is PromotionDecision.EDITED else None,
            company_id=company_id,
            company_source_position=source_position,
            company_signal_position=signal_position,
        )
        return promotion, PromotionResult(
            claim_position=claim.position,
            decision=decision.decision,
            kind=kind,
            detail=detail,
            company_source_position=source_position,
            company_signal_position=signal_position,
            source_reused=reused,
        )

    @staticmethod
    def _ensure_source(
        company: Company, run: ResearchRun, claim: ResearchClaim, warnings: list[str]
    ) -> tuple[int, bool]:
        """One Source per URL: two claims citing the same page share it."""
        page = run.page_at(claim.source_page_position)
        assert page is not None  # the claim invariant guarantees this
        sources = list(company.sources)
        for index, existing in enumerate(sources):
            if existing.reference == page.url:
                return index, True
        reference = SourceReference(
            source="company_website", reference=page.url, retrieved_at=page.fetched_at
        )
        company.add_source(reference)
        return len(sources), False

    @staticmethod
    def _payload(
        run: ResearchRun, planned: list[tuple[ResearchClaim, ClaimDecision]]
    ) -> ProspectFormPayload:
        """Everything the existing prospect form needs, for a run with no
        company: the caller submits it through the unchanged analyze endpoint."""
        sources: list[dict[str, str]] = []
        seen: set[str] = set()
        signals: list[dict[str, str]] = []
        for claim, decision in planned:
            if decision.decision is PromotionDecision.REJECTED:
                continue
            page = run.page_at(claim.source_page_position)
            if page is not None and page.url not in seen:
                seen.add(page.url)
                sources.append({"source": "company_website", "reference": page.url})
            kind = (
                decision.edited_kind or claim.kind
                if decision.decision is PromotionDecision.EDITED
                else claim.kind
            )
            detail = (
                str(decision.edited_detail).strip()
                if decision.decision is PromotionDecision.EDITED
                else claim.detail
            )
            signals.append({"kind": kind, "detail": detail})
        return ProspectFormPayload(
            company_name=run.company_name,
            website=run.website,
            sources=tuple(sources),
            signals=tuple(signals),
        )


def _add_signal(company: Company, rendered: str) -> int:
    """Append a signal and return its position. Duplicate text is shared, so a
    re-review does not grow the signal list."""
    signals = list(company.signals)
    for index, existing in enumerate(signals):
        if existing == rendered:
            return index
    company.add_signal(rendered)
    return len(signals)
