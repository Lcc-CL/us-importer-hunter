"""Real PostgreSQL: claim review and promotion into a Company.

The whole point of this phase is that a human decision becomes company data
exactly once, traceably, and never by accident — so these tests assert against
the database, not just the returned objects.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain.company import Company
from app.domain.research import (
    ExtractorIdentity,
    PromotionDecision,
    ResearchClaim,
    ResearchPage,
    ResearchProfile,
    ResearchRun,
)
from app.domain.values import CompanyName, WebsiteUrl
from app.workflows.research import (
    ClaimDecision,
    ClaimPromotionWorkflow,
    CompanyNotFound,
    InvalidDecision,
    PromotionConflict,
    ResearchRunNotFound,
    ReviewAction,
    ReviewRequest,
)
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_research_db import session_of

FIXED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
WEBSITE = "https://acme.example"
HOME = f"{WEBSITE}/"
ABOUT = f"{WEBSITE}/about"


def build_run(company_id: object | None = None) -> ResearchRun:
    """Two pages, three claims — two citing the same page, so source
    deduplication is exercised."""
    run = ResearchRun.start("Acme Hardware", WEBSITE, company_id=company_id)  # type: ignore[arg-type]
    run.mark_running()
    for position, url in ((0, HOME), (1, ABOUT)):
        run.record_page(
            ResearchPage(
                position=position,
                url=url,
                final_url=url,
                http_status=200,
                content_type="text/html",
                fetched_at=FIXED_AT,
                content_chars=500,
                discovery_reason="homepage" if position == 0 else "ranked:about",
            )
        )
    run.record_extraction(
        profile=ResearchProfile(summary="Hardware importer"),
        extractor=ExtractorIdentity(provider="fake", model="fake-research-v1", prompt_version="v1"),
        proposed_count=3,
    )
    specs = [
        (0, "company_scale", "operates a large warehouse", 0),
        (1, "import_activity", "imports fasteners from Asia", 0),  # same page as claim 0
        (2, "growth_signal", "import volume rising", 1),
    ]
    for position, kind, detail, page_position in specs:
        run.record_claim(
            ResearchClaim(
                position=position,
                kind=kind,
                detail=detail,
                evidence_snippet=f"evidence sentence for {kind}",
                source_page_position=page_position,
                confidence=0.8,
            )
        )
    run.complete()
    return run


async def seed(
    uow_factory: UowFactory, *, bind_company: bool = True
) -> tuple[ResearchRun, Company | None]:
    company: Company | None = None
    if bind_company:
        company = Company.create(CompanyName("Acme Hardware"), WebsiteUrl(WEBSITE))
    run = build_run(company.id if company else None)
    async with uow_factory() as uow:
        if company is not None:
            await uow.companies.add(company)
        await uow.research_runs.add(run)
        await uow.commit()
    return run, company


def workflow(uow_factory: UowFactory) -> ClaimPromotionWorkflow:
    return ClaimPromotionWorkflow(uow_factory=uow_factory)


def decisions(*specs: tuple[int, str, str | None]) -> tuple[ClaimDecision, ...]:
    return tuple(
        ClaimDecision(
            claim_position=position,
            decision=PromotionDecision(decision),
            edited_detail=detail,
        )
        for position, decision, detail in specs
    )


class TestAcceptedEditedRejected:
    async def test_accepted_uses_the_original_kind_and_detail(
        self, uow_factory: UowFactory
    ) -> None:
        run, company = await seed(uow_factory)
        outcome = await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "accepted", None)),
            )
        )
        assert outcome.action is ReviewAction.APPLIED
        result = outcome.results[0]
        assert result.kind == "company_scale"
        assert result.detail == "operates a large warehouse"

        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
        assert reloaded is not None
        assert reloaded.signals == ("company_scale: operates a large warehouse",)

    async def test_edited_uses_the_reviewers_text_and_kind(
        self, uow_factory: UowFactory
    ) -> None:
        run, company = await seed(uow_factory)
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=(
                    ClaimDecision(
                        claim_position=0,
                        decision=PromotionDecision.EDITED,
                        edited_detail="reviewer reworded this",
                        edited_kind="shipping_fit",
                    ),
                ),
            )
        )
        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
            saved_run = await uow.research_runs.get_by_id(run.id)
        assert reloaded is not None
        assert reloaded.signals == ("shipping_fit: reviewer reworded this",)
        assert saved_run is not None
        promotion = saved_run.promotion_for(0)
        assert promotion is not None
        assert promotion.edited_detail == "reviewer reworded this"
        assert promotion.edited_kind == "shipping_fit"

    async def test_rejected_writes_no_company_data(self, uow_factory: UowFactory) -> None:
        run, company = await seed(uow_factory)
        outcome = await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "rejected", None)),
            )
        )
        assert outcome.results[0].company_signal_position is None

        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
            saved_run = await uow.research_runs.get_by_id(run.id)
        assert reloaded is not None
        assert reloaded.signals == ()
        assert reloaded.sources == ()
        # The decision itself is still recorded — it measures extractor precision.
        assert saved_run is not None
        promotion = saved_run.promotion_for(0)
        assert promotion is not None and promotion.decision is PromotionDecision.REJECTED

    async def test_mixed_batch_applies_atomically(self, uow_factory: UowFactory) -> None:
        run, company = await seed(uow_factory)
        outcome = await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=(
                    ClaimDecision(claim_position=0, decision=PromotionDecision.ACCEPTED),
                    ClaimDecision(
                        claim_position=1,
                        decision=PromotionDecision.EDITED,
                        edited_detail="edited import detail",
                    ),
                    ClaimDecision(claim_position=2, decision=PromotionDecision.REJECTED),
                ),
            )
        )
        assert (outcome.accepted, outcome.edited, outcome.rejected) == (1, 1, 1)

        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
        assert reloaded is not None
        assert len(reloaded.signals) == 2  # the rejected one is absent
        assert "import_activity: edited import detail" in reloaded.signals


class TestAtomicity:
    async def test_one_invalid_decision_rolls_back_the_whole_batch(
        self, uow_factory: UowFactory
    ) -> None:
        """All or nothing: a bad decision late in the list must not leave the
        earlier ones applied."""
        run, company = await seed(uow_factory)
        with pytest.raises(InvalidDecision):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run.id,
                    reviewer_name="Lcc",
                    decisions=(
                        ClaimDecision(claim_position=0, decision=PromotionDecision.ACCEPTED),
                        ClaimDecision(claim_position=99, decision=PromotionDecision.ACCEPTED),
                    ),
                )
            )

        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
            saved_run = await uow.research_runs.get_by_id(run.id)
        assert reloaded is not None and reloaded.signals == ()
        assert saved_run is not None and saved_run.promotions == ()

    async def test_invalid_edited_kind_rolls_back(self, uow_factory: UowFactory) -> None:
        run, company = await seed(uow_factory)
        with pytest.raises(InvalidDecision, match="not allowed"):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run.id,
                    reviewer_name="Lcc",
                    decisions=(
                        ClaimDecision(claim_position=0, decision=PromotionDecision.ACCEPTED),
                        ClaimDecision(
                            claim_position=1,
                            decision=PromotionDecision.EDITED,
                            edited_detail="ok",
                            edited_kind="revenue_estimate",
                        ),
                    ),
                )
            )
        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
        assert reloaded is not None and reloaded.signals == ()

    async def test_empty_edited_detail_is_refused(self, uow_factory: UowFactory) -> None:
        run, _ = await seed(uow_factory)
        with pytest.raises(InvalidDecision, match="requires a detail"):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run.id,
                    reviewer_name="Lcc",
                    decisions=(
                        ClaimDecision(
                            claim_position=0,
                            decision=PromotionDecision.EDITED,
                            edited_detail="   ",
                        ),
                    ),
                )
            )


class TestClaimOwnership:
    async def test_unknown_claim_position_is_refused(self, uow_factory: UowFactory) -> None:
        run, _ = await seed(uow_factory)
        with pytest.raises(InvalidDecision, match="does not belong"):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run.id,
                    reviewer_name="Lcc",
                    decisions=decisions((42, "accepted", None)),
                )
            )

    async def test_claim_from_another_run_is_refused(self, uow_factory: UowFactory) -> None:
        """Positions are per-run; a position that exists elsewhere must not be
        borrowed across runs."""
        run_a, _ = await seed(uow_factory)
        run_b = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run_b)
            await uow.commit()

        # Position 2 exists in both runs; confirm against run_b must review
        # run_b's claim, and a position beyond its range must be refused.
        with pytest.raises(InvalidDecision, match="does not belong"):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run_b.id,
                    reviewer_name="Lcc",
                    decisions=decisions((7, "accepted", None)),
                )
            )

    async def test_unknown_run_is_refused(self, uow_factory: UowFactory) -> None:
        with pytest.raises(ResearchRunNotFound):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=uuid4(),
                    reviewer_name="Lcc",
                    decisions=decisions((0, "accepted", None)),
                )
            )


class TestTargetCompanyRules:
    async def test_bound_run_uses_its_own_company(self, uow_factory: UowFactory) -> None:
        run, company = await seed(uow_factory)
        outcome = await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "accepted", None)),
            )
        )
        assert outcome.company_id == company.id  # type: ignore[union-attr]

    async def test_mismatched_target_company_is_a_conflict(
        self, uow_factory: UowFactory
    ) -> None:
        run, _ = await seed(uow_factory)
        with pytest.raises(PromotionConflict, match="bound to company"):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run.id,
                    reviewer_name="Lcc",
                    target_company_id=uuid4(),
                    decisions=decisions((0, "accepted", None)),
                )
            )

    async def test_unbound_run_with_target_company_applies_to_it(
        self, uow_factory: UowFactory
    ) -> None:
        run, _ = await seed(uow_factory, bind_company=False)
        target = Company.create(CompanyName("Target Co"), WebsiteUrl("https://target.example"))
        async with uow_factory() as uow:
            await uow.companies.add(target)
            await uow.commit()

        outcome = await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                target_company_id=target.id,
                decisions=decisions((0, "accepted", None)),
            )
        )
        assert outcome.action is ReviewAction.APPLIED
        assert outcome.company_id == target.id

        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(target.id)
        assert reloaded is not None
        assert reloaded.signals == ("company_scale: operates a large warehouse",)

    async def test_unknown_target_company_is_refused(self, uow_factory: UowFactory) -> None:
        run, _ = await seed(uow_factory, bind_company=False)
        with pytest.raises(CompanyNotFound):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run.id,
                    reviewer_name="Lcc",
                    target_company_id=uuid4(),
                    decisions=decisions((0, "accepted", None)),
                )
            )

    async def test_unbound_run_without_target_records_only(
        self, uow_factory: UowFactory
    ) -> None:
        """No company is created; the decisions are kept and a form payload is
        returned for phase 4."""
        run, _ = await seed(uow_factory, bind_company=False)
        outcome = await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=(
                    ClaimDecision(claim_position=0, decision=PromotionDecision.ACCEPTED),
                    ClaimDecision(claim_position=2, decision=PromotionDecision.REJECTED),
                ),
            )
        )
        assert outcome.action is ReviewAction.RECORDED
        assert outcome.company_id is None
        payload = outcome.application_payload
        assert payload is not None
        assert payload.company_name == "Acme Hardware"
        assert payload.website == WEBSITE
        assert payload.signals == (
            {"kind": "company_scale", "detail": "operates a large warehouse"},
        )
        assert len(payload.sources) == 1  # rejected claim contributed nothing

        async with uow_factory() as uow:
            count = await session_of(uow).execute(
                text("SELECT count(*) FROM companies WHERE name = 'Acme Hardware'")
            )
        assert count.scalar_one() == 0  # no Company was created


class TestSourceDeduplication:
    async def test_two_claims_on_one_page_share_a_single_source(
        self, uow_factory: UowFactory
    ) -> None:
        run, company = await seed(uow_factory)
        outcome = await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=(
                    ClaimDecision(claim_position=0, decision=PromotionDecision.ACCEPTED),
                    ClaimDecision(claim_position=1, decision=PromotionDecision.ACCEPTED),
                ),
            )
        )
        assert outcome.results[0].source_reused is False
        assert outcome.results[1].source_reused is True
        assert outcome.results[0].company_source_position == 0
        assert outcome.results[1].company_source_position == 0

        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
        assert reloaded is not None
        assert len(reloaded.sources) == 1
        assert reloaded.sources[0].reference == HOME
        assert len(reloaded.signals) == 2  # two signals, one source

    async def test_claims_on_different_pages_create_separate_sources(
        self, uow_factory: UowFactory
    ) -> None:
        run, company = await seed(uow_factory)
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=(
                    ClaimDecision(claim_position=0, decision=PromotionDecision.ACCEPTED),
                    ClaimDecision(claim_position=2, decision=PromotionDecision.ACCEPTED),
                ),
            )
        )
        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
        assert reloaded is not None
        assert {source.reference for source in reloaded.sources} == {HOME, ABOUT}


class TestIdempotencyAndConflict:
    async def test_identical_replay_changes_nothing(self, uow_factory: UowFactory) -> None:
        run, company = await seed(uow_factory)
        request = ReviewRequest(
            research_run_id=run.id,
            reviewer_name="Lcc",
            decisions=decisions((0, "accepted", None)),
        )
        first = await workflow(uow_factory).handle(request)
        second = await workflow(uow_factory).handle(request)

        assert first.action is ReviewAction.APPLIED
        assert second.action is ReviewAction.UNCHANGED
        assert all(result.idempotent for result in second.results)

        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
        assert reloaded is not None
        assert len(reloaded.signals) == 1  # not duplicated
        assert len(reloaded.sources) == 1

    async def test_contradicting_an_applied_decision_is_a_conflict(
        self, uow_factory: UowFactory
    ) -> None:
        run, _ = await seed(uow_factory)
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "accepted", None)),
            )
        )
        with pytest.raises(PromotionConflict, match="already applied"):
            await workflow(uow_factory).handle(
                ReviewRequest(
                    research_run_id=run.id,
                    reviewer_name="Lcc",
                    decisions=decisions((0, "rejected", None)),
                )
            )

    async def test_revising_a_decision_that_never_touched_a_company_is_allowed(
        self, uow_factory: UowFactory
    ) -> None:
        """A rejected decision wrote nothing, so the reviewer may change it."""
        run, company = await seed(uow_factory)
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "rejected", None)),
            )
        )
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "accepted", None)),
            )
        )
        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)  # type: ignore[union-attr]
        assert reloaded is not None and len(reloaded.signals) == 1


class TestDatabaseGuarantees:
    async def test_one_promotion_per_claim_is_enforced_by_the_database(
        self, uow_factory: UowFactory
    ) -> None:
        run, _ = await seed(uow_factory)
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "accepted", None)),
            )
        )
        async with uow_factory() as uow:
            with pytest.raises(IntegrityError):
                await session_of(uow).execute(
                    text(
                        "INSERT INTO research_promotions (research_id, claim_position,"
                        " decision, reviewed_at) VALUES (:rid, 0, 'rejected', now())"
                    ),
                    {"rid": run.id},
                )

    async def test_rejected_promotion_cannot_carry_company_positions(
        self, uow_factory: UowFactory
    ) -> None:
        run, _ = await seed(uow_factory)
        async with uow_factory() as uow:
            with pytest.raises(IntegrityError):
                await session_of(uow).execute(
                    text(
                        "INSERT INTO research_promotions (research_id, claim_position,"
                        " decision, reviewed_at, company_signal_position)"
                        " VALUES (:rid, 1, 'rejected', now(), 3)"
                    ),
                    {"rid": run.id},
                )

    async def test_company_delete_nulls_the_promotion_link_but_keeps_the_row(
        self, uow_factory: UowFactory
    ) -> None:
        run, company = await seed(uow_factory)
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "accepted", None)),
            )
        )
        async with uow_factory() as uow:
            await session_of(uow).execute(
                text("DELETE FROM companies WHERE id = :cid"),
                {"cid": company.id},  # type: ignore[union-attr]
            )
            await uow.commit()

        async with uow_factory() as uow:
            saved = await uow.research_runs.get_by_id(run.id)
        assert saved is not None
        promotion = saved.promotion_for(0)
        assert promotion is not None
        assert promotion.company_id is None            # link broken
        assert promotion.decision is PromotionDecision.ACCEPTED  # audit preserved
        assert saved.company_id is None


class TestNoSideEffects:
    async def test_promotion_creates_no_opportunity_or_draft(
        self, uow_factory: UowFactory
    ) -> None:
        """Promotion records facts. Scoring and email are separate acts."""
        run, company = await seed(uow_factory)
        await workflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="Lcc",
                decisions=decisions((0, "accepted", None)),
            )
        )
        async with uow_factory() as uow:
            counts = await session_of(uow).execute(
                text(
                    "SELECT (SELECT count(*) FROM opportunities WHERE company_id = :cid)"
                    " + (SELECT count(*) FROM opportunity_assessments)"
                    " + (SELECT count(*) FROM outreaches)"
                    " + (SELECT count(*) FROM email_drafts)"
                ),
                {"cid": company.id},  # type: ignore[union-attr]
            )
        assert counts.scalar_one() == 0
