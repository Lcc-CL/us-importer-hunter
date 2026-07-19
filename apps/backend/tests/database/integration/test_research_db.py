"""Real PostgreSQL: research run round-trip and the constraints that make the
claim rules database invariants rather than application-only checks.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.company import Company
from app.domain.repositories import UnitOfWork
from app.domain.research import (
    ClaimRejectionReason,
    ExtractorIdentity,
    PromotionDecision,
    RejectedClaim,
    ResearchClaim,
    ResearchFailureCode,
    ResearchPage,
    ResearchProfile,
    ResearchPromotion,
    ResearchRun,
    ResearchRunStatus,
)
from app.domain.values import CompanyName, WebsiteUrl
from tests.database.integration.conftest import UowFactory


def session_of(uow: UnitOfWork) -> AsyncSession:
    """Raw session for constraint probes. The UoW keeps it private because
    application code must not reach past the repositories; these tests are
    deliberately checking the database itself."""
    session = getattr(uow, "_session", None)
    assert isinstance(session, AsyncSession)
    return session

FIXED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
WEBSITE_FOR_TESTS = "https://promotion-target.example"


def build_run() -> ResearchRun:
    run = ResearchRun.start("Acme Hardware", "https://acme.example")
    run.mark_running()
    run.record_page(
        ResearchPage(
            position=0,
            url="https://acme.example/",
            final_url="https://acme.example/",
            http_status=200,
            content_type="text/html",
            fetched_at=FIXED_AT,
            content_chars=812,
            bytes_read=4096,
            discovery_reason="homepage",
        )
    )
    run.record_page(
        ResearchPage(
            position=1,
            url="https://acme.example/about",
            final_url="https://acme.example/about",
            http_status=200,
            content_type="text/html",
            fetched_at=FIXED_AT,
            content_chars=430,
            truncated=True,
            discovery_reason="ranked:about",
        )
    )
    run.record_extraction(
        profile=ResearchProfile(summary="Hardware importer", products=("fasteners",)),
        extractor=ExtractorIdentity(
            provider="fake", model="fake-research-v1", prompt_version="research-extract-fake-v1"
        ),
        proposed_count=3,
    )
    run.record_claim(
        ResearchClaim(
            position=0,
            kind="company_scale",
            detail="operates a large warehouse",
            evidence_snippet="We operate a 120,000 sq ft warehouse in Long Beach.",
            source_page_position=0,
            confidence=0.8,
        )
    )
    run.record_claim(
        ResearchClaim(
            position=1,
            kind="growth_signal",
            detail="import volume rising",
            evidence_snippet="has grown its import volume every year since 2019",
            source_page_position=1,
            confidence=0.6,
        )
    )
    run.record_rejection(
        RejectedClaim(
            reason=ClaimRejectionReason.SNIPPET_NOT_FOUND,
            kind="cargo_value_potential",
            detail="invented value claim",
            warning="claim rejected (snippet_not_found): not present on page",
        )
    )
    run.complete(partial=True, failure_code=ResearchFailureCode.NEEDS_BROWSER)
    return run


class TestRoundTrip:
    async def test_run_survives_a_save_and_reload(self, uow_factory: UowFactory) -> None:
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()

        async with uow_factory() as uow:
            loaded = await uow.research_runs.get_by_id(run.id)

        assert loaded is not None
        assert loaded.company_name == "Acme Hardware"
        assert loaded.status is ResearchRunStatus.PARTIAL
        assert loaded.failure_code is ResearchFailureCode.NEEDS_BROWSER
        assert loaded.pages_fetched == 2
        assert loaded.claims_extracted == 3
        assert loaded.claims_validated == 2
        assert loaded.extractor is not None
        assert loaded.extractor.prompt_version == "research-extract-fake-v1"
        assert loaded.profile.summary == "Hardware importer"
        assert loaded.profile.products == ("fasteners",)
        assert any("snippet_not_found" in warning for warning in loaded.warnings)

    async def test_claim_provenance_survives(self, uow_factory: UowFactory) -> None:
        """The whole point of the table group: which page, which sentence."""
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        async with uow_factory() as uow:
            loaded = await uow.research_runs.get_by_id(run.id)

        assert loaded is not None
        claim = loaded.claims[0]
        assert claim.source_page_position == 0
        assert claim.evidence_snippet.startswith("We operate a 120,000")
        assert claim.confidence == 0.8
        page = loaded.page_at(claim.source_page_position)
        assert page is not None and page.url == "https://acme.example/"

    async def test_truncation_flag_persists(self, uow_factory: UowFactory) -> None:
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        async with uow_factory() as uow:
            loaded = await uow.research_runs.get_by_id(run.id)
        assert loaded is not None
        assert loaded.page_at(1) is not None
        page = loaded.page_at(1)
        assert page is not None and page.truncated is True

    async def test_missing_run_returns_none(self, uow_factory: UowFactory) -> None:
        async with uow_factory() as uow:
            assert await uow.research_runs.get_by_id(uuid4()) is None


class TestPromotionTrace:
    async def test_promotions_persist_including_rejections(
        self, uow_factory: UowFactory
    ) -> None:
        """company_id is a real foreign key since phase 3.3, so the promotion
        must point at a company that exists."""
        run = build_run()
        company = Company.create(CompanyName("Promotion Target"), WebsiteUrl(WEBSITE_FOR_TESTS))
        company_id = company.id
        run.record_promotion(
            ResearchPromotion(
                claim_position=0,
                decision=PromotionDecision.ACCEPTED,
                reviewer_name="Lcc",
                company_id=company_id,
                company_signal_position=4,
            )
        )
        run.record_promotion(
            ResearchPromotion(
                claim_position=1,
                decision=PromotionDecision.REJECTED,
                reviewer_name="Lcc",
            )
        )
        async with uow_factory() as uow:
            await uow.companies.add(company)
            await uow.research_runs.add(run)
            await uow.commit()

        async with uow_factory() as uow:
            loaded = await uow.research_runs.get_by_id(run.id)

        assert loaded is not None
        assert len(loaded.promotions) == 2
        accepted = next(p for p in loaded.promotions if p.decision is PromotionDecision.ACCEPTED)
        assert accepted.company_id == company_id
        assert accepted.company_signal_position == 4
        assert accepted.reviewer_name == "Lcc"
        assert len(loaded.accepted_promotions()) == 1

    async def test_edited_detail_round_trips(self, uow_factory: UowFactory) -> None:
        run = build_run()
        run.record_promotion(
            ResearchPromotion(
                claim_position=0,
                decision=PromotionDecision.EDITED,
                edited_detail="reviewer reworded this claim",
            )
        )
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        async with uow_factory() as uow:
            loaded = await uow.research_runs.get_by_id(run.id)
        assert loaded is not None
        assert loaded.promotions[0].edited_detail == "reviewer reworded this claim"


class TestDatabaseConstraints:
    """These rules must hold even if application code is bypassed."""

    async def test_claim_kind_is_constrained(self, uow_factory: UowFactory) -> None:
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
            with pytest.raises(IntegrityError):
                await session_of(uow).execute(
                    text(
                        "INSERT INTO research_claims (research_id, position, kind, detail,"
                        " evidence_snippet, source_page_position, confidence)"
                        " VALUES (:rid, 99, 'revenue_estimate', 'd', 's', 0, 0.5)"
                    ),
                    {"rid": run.id},
                )

    async def test_claim_confidence_is_constrained(self, uow_factory: UowFactory) -> None:
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
            with pytest.raises(IntegrityError):
                await session_of(uow).execute(
                    text(
                        "INSERT INTO research_claims (research_id, position, kind, detail,"
                        " evidence_snippet, source_page_position, confidence)"
                        " VALUES (:rid, 98, 'company_scale', 'd', 's', 0, 1.5)"
                    ),
                    {"rid": run.id},
                )

    async def test_claim_cannot_cite_a_page_outside_its_run(
        self, uow_factory: UowFactory
    ) -> None:
        """The composite FK is a real database invariant, not just an
        application check. It is DEFERRABLE INITIALLY DEFERRED, so the
        violation surfaces when constraints are checked rather than on the
        INSERT itself — forced here with SET CONSTRAINTS IMMEDIATE, which is
        what COMMIT would do anyway.
        """
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
            await session_of(uow).execute(
                text(
                    "INSERT INTO research_claims (research_id, position, kind, detail,"
                    " evidence_snippet, source_page_position, confidence)"
                    " VALUES (:rid, 97, 'company_scale', 'd', 's', 42, 0.5)"
                ),
                {"rid": run.id},
            )
            with pytest.raises(IntegrityError):
                await session_of(uow).execute(
                    text("SET CONSTRAINTS fk_research_claims_source_page IMMEDIATE")
                )

    async def test_a_valid_page_reference_passes_the_same_check(
        self, uow_factory: UowFactory
    ) -> None:
        """Mirror of the test above: citing a page that does exist is fine
        even under immediate checking."""
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
            await session_of(uow).execute(
                text(
                    "INSERT INTO research_claims (research_id, position, kind, detail,"
                    " evidence_snippet, source_page_position, confidence)"
                    " VALUES (:rid, 96, 'company_scale', 'd', 's', 1, 0.5)"
                ),
                {"rid": run.id},
            )
            await session_of(uow).execute(
                text("SET CONSTRAINTS fk_research_claims_source_page IMMEDIATE")
            )

    async def test_run_status_is_constrained(self, uow_factory: UowFactory) -> None:
        async with uow_factory() as uow:
            with pytest.raises(IntegrityError):
                await session_of(uow).execute(
                    text(
                        "INSERT INTO research_runs (id, company_name, website, status,"
                        " started_at, pages_fetched, pages_failed, claims_extracted,"
                        " claims_validated, profile_json, warnings_json)"
                        " VALUES (:rid, 'X', 'https://x.example', 'exploded', now(),"
                        " 0, 0, 0, 0, '{}', '[]')"
                    ),
                    {"rid": uuid4()},
                )

    async def test_edited_promotion_requires_edited_detail(
        self, uow_factory: UowFactory
    ) -> None:
        run = build_run()
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
            with pytest.raises(IntegrityError):
                await session_of(uow).execute(
                    text(
                        "INSERT INTO research_promotions (research_id, claim_position,"
                        " decision, reviewed_at) VALUES (:rid, 0, 'edited', now())"
                    ),
                    {"rid": run.id},
                )

    async def test_deleting_a_run_cascades_to_its_children(
        self, uow_factory: UowFactory
    ) -> None:
        run = build_run()
        run.record_promotion(
            ResearchPromotion(claim_position=0, decision=PromotionDecision.ACCEPTED)
        )
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
            await session_of(uow).execute(
                text("DELETE FROM research_runs WHERE id = :rid"), {"rid": run.id}
            )
            remaining = await session_of(uow).execute(
                text(
                    "SELECT (SELECT count(*) FROM research_pages WHERE research_id = :rid)"
                    " + (SELECT count(*) FROM research_claims WHERE research_id = :rid)"
                    " + (SELECT count(*) FROM research_promotions WHERE research_id = :rid)"
                ),
                {"rid": run.id},
            )
            assert remaining.scalar_one() == 0


class TestCompanyLink:
    """research_runs.company_id links a run to a company *without* making the
    run depend on it. Phase 3.2 replaced the earlier no-foreign-key approach:
    the FK gives referential integrity, and ON DELETE SET NULL preserves the
    audit record. Deleting a company must never delete its research history.
    """

    async def test_the_only_links_out_of_research_are_the_nullable_company_fks(
        self, uow_factory: UowFactory
    ) -> None:
        """Two links since phase 3.3 — the run and the promotion each point at
        a company, both nullable and both ON DELETE SET NULL."""
        async with uow_factory() as uow:
            result = await session_of(uow).execute(
                text(
                    "SELECT tc.constraint_name, ccu.table_name"
                    " FROM information_schema.table_constraints tc"
                    " JOIN information_schema.constraint_column_usage ccu"
                    "   ON tc.constraint_name = ccu.constraint_name"
                    " WHERE tc.constraint_type = 'FOREIGN KEY'"
                    "   AND tc.table_name LIKE 'research%'"
                    "   AND ccu.table_name NOT LIKE 'research%'"
                )
            )
            links = result.all()
        assert sorted((name, table) for name, table in links) == [
            ("fk_research_promotions_company", "companies"),
            ("fk_research_runs_company", "companies"),
        ]

    async def test_company_fk_is_on_delete_set_null(self, uow_factory: UowFactory) -> None:
        async with uow_factory() as uow:
            result = await session_of(uow).execute(
                text(
                    "SELECT confdeltype::text FROM pg_constraint"
                    " WHERE conname = 'fk_research_runs_company'"
                )
            )
            assert result.scalar_one() == "n"  # 'n' = SET NULL

    async def test_company_id_is_nullable_so_prospects_can_be_researched(
        self, uow_factory: UowFactory
    ) -> None:
        run = build_run()  # built without a company_id
        assert run.company_id is None
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        async with uow_factory() as uow:
            loaded = await uow.research_runs.get_by_id(run.id)
        assert loaded is not None and loaded.company_id is None

    async def test_rejected_claims_are_persisted_not_only_warned(
        self, uow_factory: UowFactory
    ) -> None:
        """Rejection detail must survive a reload, otherwise a stored run
        cannot explain why a proposal was refused."""
        run = build_run()  # contains one rejected claim
        async with uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        async with uow_factory() as uow:
            loaded = await uow.research_runs.get_by_id(run.id)

        assert loaded is not None
        assert len(loaded.rejected_claims) == 1
        rejection = loaded.rejected_claims[0]
        assert rejection.reason is ClaimRejectionReason.SNIPPET_NOT_FOUND
        assert rejection.kind == "cargo_value_potential"
        assert "snippet_not_found" in rejection.warning
