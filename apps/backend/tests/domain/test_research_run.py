"""ResearchRun aggregate invariants."""

from datetime import UTC, datetime

import pytest

from app.domain.exceptions import DomainError, InvalidStateTransition
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

FIXED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def a_page(position: int = 0) -> ResearchPage:
    return ResearchPage(
        position=position,
        url=f"https://acme.example/p{position}",
        final_url=f"https://acme.example/p{position}",
        http_status=200,
        content_type="text/html",
        fetched_at=FIXED_AT,
        content_chars=500,
    )


def a_claim(position: int = 0, source: int = 0) -> ResearchClaim:
    return ResearchClaim(
        position=position,
        kind="company_scale",
        detail="operates a warehouse",
        evidence_snippet="We operate a warehouse in Long Beach.",
        source_page_position=source,
        confidence=0.8,
    )


def a_run() -> ResearchRun:
    run = ResearchRun.start("Acme Hardware", "https://acme.example")
    run.mark_running()
    return run


class TestLifecycle:
    def test_starts_created_then_running(self) -> None:
        run = ResearchRun.start("Acme", "https://acme.example")
        assert run.status.value == "created"
        run.mark_running()
        assert run.status.value == "running"

    def test_completes(self) -> None:
        run = a_run()
        run.complete()
        assert run.status is ResearchRunStatus.COMPLETED
        assert run.completed_at is not None

    def test_completes_partially_with_a_failure_code(self) -> None:
        run = a_run()
        run.complete(partial=True, failure_code=ResearchFailureCode.NEEDS_BROWSER)
        assert run.status is ResearchRunStatus.PARTIAL
        assert run.failure_code is ResearchFailureCode.NEEDS_BROWSER

    def test_fails_with_a_reason(self) -> None:
        run = a_run()
        run.fail(ResearchFailureCode.UNREACHABLE, "DNS failure")
        assert run.status is ResearchRunStatus.FAILED
        assert "DNS failure" in run.warnings

    def test_terminal_runs_are_final(self) -> None:
        run = a_run()
        run.complete()
        with pytest.raises(InvalidStateTransition):
            run.complete()
        with pytest.raises(InvalidStateTransition):
            run.fail(ResearchFailureCode.UNREACHABLE, "x")
        with pytest.raises(InvalidStateTransition):
            run.record_page(a_page(9))

    def test_requires_name_and_website(self) -> None:
        with pytest.raises(DomainError):
            ResearchRun.start("  ", "https://acme.example")
        with pytest.raises(DomainError):
            ResearchRun.start("Acme", "  ")


class TestPagesAndClaims:
    def test_records_pages_and_counts_them(self) -> None:
        run = a_run()
        run.record_page(a_page(0))
        run.record_page(a_page(1))
        assert run.pages_fetched == 2
        assert run.page_at(1) is not None

    def test_duplicate_page_position_refused(self) -> None:
        run = a_run()
        run.record_page(a_page(0))
        with pytest.raises(DomainError):
            run.record_page(a_page(0))

    def test_page_failures_counted_and_warned(self) -> None:
        run = a_run()
        run.record_page_failure("timeout on /about")
        assert run.pages_failed == 1
        assert "timeout on /about" in run.warnings

    def test_claim_must_cite_a_page_in_this_run(self) -> None:
        """The aggregate mirrors the composite FK: a claim cannot point at a
        page the run never fetched."""
        run = a_run()
        run.record_page(a_page(0))
        with pytest.raises(DomainError, match="not in this run"):
            run.record_claim(a_claim(position=0, source=7))

    def test_valid_claim_recorded(self) -> None:
        run = a_run()
        run.record_page(a_page(0))
        run.record_claim(a_claim())
        assert run.claims_validated == 1

    def test_duplicate_claim_position_refused(self) -> None:
        run = a_run()
        run.record_page(a_page(0))
        run.record_claim(a_claim(position=0))
        with pytest.raises(DomainError):
            run.record_claim(a_claim(position=0))

    def test_rejections_recorded_with_their_warning(self) -> None:
        run = a_run()
        run.record_rejection(
            RejectedClaim(
                reason=ClaimRejectionReason.SNIPPET_NOT_FOUND,
                kind="company_scale",
                detail="invented",
                warning="claim rejected (snippet_not_found): not on page",
            )
        )
        assert run.rejection_reasons() == (ClaimRejectionReason.SNIPPET_NOT_FOUND,)
        assert any("snippet_not_found" in warning for warning in run.warnings)


class TestExtractionMetadata:
    def test_extractor_identity_and_counts_recorded(self) -> None:
        run = a_run()
        run.record_extraction(
            profile=ResearchProfile(summary="Hardware importer"),
            extractor=ExtractorIdentity(
                provider="fake", model="fake-research-v1", prompt_version="v1"
            ),
            proposed_count=5,
        )
        assert run.claims_extracted == 5
        assert run.extractor is not None
        assert run.extractor.provider == "fake"
        assert run.profile.summary == "Hardware importer"

    def test_validated_never_exceeds_extracted(self) -> None:
        """Mirrors the database CHECK: validated ⊆ extracted."""
        run = a_run()
        run.record_page(a_page(0))
        run.record_extraction(
            profile=ResearchProfile(),
            extractor=ExtractorIdentity(provider="fake", model="m", prompt_version="v"),
            proposed_count=3,
        )
        run.record_claim(a_claim(position=0))
        assert run.claims_validated <= run.claims_extracted


class TestPromotions:
    def test_promotion_requires_a_known_claim(self) -> None:
        run = a_run()
        with pytest.raises(DomainError, match="unknown claim position"):
            run.record_promotion(
                ResearchPromotion(claim_position=0, decision=PromotionDecision.ACCEPTED)
            )

    def test_accepted_and_edited_are_promotable(self) -> None:
        run = a_run()
        run.record_page(a_page(0))
        run.record_claim(a_claim(position=0))
        run.record_claim(a_claim(position=1))
        run.record_promotion(
            ResearchPromotion(claim_position=0, decision=PromotionDecision.ACCEPTED)
        )
        run.record_promotion(
            ResearchPromotion(
                claim_position=1,
                decision=PromotionDecision.EDITED,
                edited_detail="reworded by reviewer",
            )
        )
        assert len(run.accepted_promotions()) == 2

    def test_rejected_promotions_are_kept_but_not_promoted(self) -> None:
        """Rejections are the only evidence of extractor precision."""
        run = a_run()
        run.record_page(a_page(0))
        run.record_claim(a_claim(position=0))
        run.record_promotion(
            ResearchPromotion(claim_position=0, decision=PromotionDecision.REJECTED)
        )
        assert len(run.promotions) == 1
        assert run.accepted_promotions() == ()

    def test_a_claim_is_reviewed_once(self) -> None:
        run = a_run()
        run.record_page(a_page(0))
        run.record_claim(a_claim(position=0))
        run.record_promotion(
            ResearchPromotion(claim_position=0, decision=PromotionDecision.ACCEPTED)
        )
        with pytest.raises(DomainError, match="already been reviewed"):
            run.record_promotion(
                ResearchPromotion(claim_position=0, decision=PromotionDecision.REJECTED)
            )

    def test_edited_requires_edited_detail(self) -> None:
        with pytest.raises(DomainError, match="requires edited_detail"):
            ResearchPromotion(claim_position=0, decision=PromotionDecision.EDITED)

    def test_edited_detail_only_valid_when_edited(self) -> None:
        with pytest.raises(DomainError, match="only valid for an edited"):
            ResearchPromotion(
                claim_position=0,
                decision=PromotionDecision.ACCEPTED,
                edited_detail="should not be here",
            )


class TestClaimValueObject:
    def test_kind_must_be_whitelisted(self) -> None:
        with pytest.raises(DomainError, match="kind is not allowed"):
            ResearchClaim(
                position=0,
                kind="revenue_estimate",
                detail="d",
                evidence_snippet="s",
                source_page_position=0,
                confidence=0.5,
            )

    @pytest.mark.parametrize("confidence", [-0.01, 1.01])
    def test_confidence_must_be_within_zero_to_one(self, confidence: float) -> None:
        with pytest.raises(DomainError, match="confidence"):
            ResearchClaim(
                position=0,
                kind="company_scale",
                detail="d",
                evidence_snippet="s",
                source_page_position=0,
                confidence=confidence,
            )

    def test_detail_and_snippet_must_be_non_empty(self) -> None:
        for detail, snippet in (("  ", "s"), ("d", "  ")):
            with pytest.raises(DomainError, match="non-empty"):
                ResearchClaim(
                    position=0,
                    kind="company_scale",
                    detail=detail,
                    evidence_snippet=snippet,
                    source_page_position=0,
                    confidence=0.5,
                )
