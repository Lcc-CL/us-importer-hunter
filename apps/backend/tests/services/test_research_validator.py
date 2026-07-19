"""Claim validation — the anti-hallucination gate (ADR-0025 §5).

Every rejection case here is a claim an extractor could plausibly produce and
that must not reach the database.
"""

from datetime import UTC, datetime

import pytest

from app.domain.research import ClaimRejectionReason, ProposedClaim, ResearchPage
from app.services.research import ClaimValidator, PageContent

FIXED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)

HOME_TEXT = (
    "Acme Hardware imports fasteners from Asia.\n"
    "We operate a 120,000 sq ft warehouse in Long Beach.\n"
    "Our team of 85 people supports retail customers nationwide."
)
ABOUT_TEXT = "Founded in 1961, Acme has grown its import volume every year since 2019."


def page(position: int, url: str, text: str) -> PageContent:
    return PageContent(
        page=ResearchPage(
            position=position,
            url=url,
            final_url=url,
            http_status=200,
            content_type="text/html",
            fetched_at=FIXED_AT,
            content_chars=len(text),
        ),
        cleaned_text=text,
    )


PAGES = (
    page(0, "https://acme.example/", HOME_TEXT),
    page(1, "https://acme.example/about", ABOUT_TEXT),
)


def proposal(**overrides: object) -> ProposedClaim:
    defaults: dict[str, object] = {
        "kind": "company_scale",
        "detail": "company scale: operates a large warehouse",
        "evidence_snippet": "We operate a 120,000 sq ft warehouse in Long Beach.",
        "source_url": "https://acme.example/",
        "confidence": 0.8,
    }
    defaults.update(overrides)
    return ProposedClaim(**defaults)  # type: ignore[arg-type]


class TestAcceptance:
    def test_valid_claim_is_accepted(self) -> None:
        outcome = ClaimValidator().validate((proposal(),), PAGES)
        assert len(outcome.accepted) == 1
        claim = outcome.accepted[0]
        assert claim.kind == "company_scale"
        assert claim.source_page_position == 0
        assert claim.confidence == 0.8
        assert outcome.rejected == ()

    def test_snippet_matched_despite_rewrapped_whitespace(self) -> None:
        """Re-wrapping a copied sentence is formatting, not invention."""
        outcome = ClaimValidator().validate(
            (proposal(evidence_snippet="We operate a 120,000 sq ft\n  warehouse in Long Beach."),),
            PAGES,
        )
        assert len(outcome.accepted) == 1

    def test_claim_can_cite_any_fetched_page(self) -> None:
        outcome = ClaimValidator().validate(
            (
                proposal(
                    kind="growth_signal",
                    detail="growth: import volume rising",
                    evidence_snippet="has grown its import volume every year since 2019",
                    source_url="https://acme.example/about",
                    confidence=0.7,
                ),
            ),
            PAGES,
        )
        assert outcome.accepted[0].source_page_position == 1

    def test_positions_are_assigned_densely(self) -> None:
        outcome = ClaimValidator().validate(
            (
                proposal(),
                proposal(kind="unknown_kind"),  # rejected, must not consume a position
                proposal(
                    kind="import_activity",
                    detail="import activity",
                    evidence_snippet="Acme Hardware imports fasteners from Asia.",
                ),
            ),
            PAGES,
        )
        assert [claim.position for claim in outcome.accepted] == [0, 1]


class TestRejection:
    def test_kind_outside_the_whitelist(self) -> None:
        outcome = ClaimValidator().validate((proposal(kind="revenue_estimate"),), PAGES)
        assert outcome.accepted == ()
        assert outcome.rejected[0].reason is ClaimRejectionReason.UNKNOWN_KIND
        assert "revenue_estimate" in outcome.rejected[0].warning

    def test_source_url_never_fetched(self) -> None:
        """The injection payoff case: a claim citing a page we never read."""
        outcome = ClaimValidator().validate(
            (proposal(source_url="https://evil.example/inject"),), PAGES
        )
        assert outcome.accepted == ()
        assert outcome.rejected[0].reason is ClaimRejectionReason.UNFETCHED_SOURCE

    def test_snippet_absent_from_the_cited_page(self) -> None:
        """Invented evidence is discarded, never downgraded."""
        outcome = ClaimValidator().validate(
            (proposal(evidence_snippet="We ship 50,000 containers every year."),), PAGES
        )
        assert outcome.accepted == ()
        assert outcome.rejected[0].reason is ClaimRejectionReason.SNIPPET_NOT_FOUND

    def test_snippet_from_a_different_fetched_page(self) -> None:
        """Real sentence, wrong attribution — still a rejection."""
        outcome = ClaimValidator().validate(
            (
                proposal(
                    evidence_snippet="Founded in 1961, Acme has grown its import volume",
                    source_url="https://acme.example/",
                ),
            ),
            PAGES,
        )
        assert outcome.accepted == ()
        assert outcome.rejected[0].reason is ClaimRejectionReason.SNIPPET_NOT_FOUND

    @pytest.mark.parametrize("confidence", [-0.1, 1.1, 42.0])
    def test_confidence_outside_zero_to_one(self, confidence: float) -> None:
        outcome = ClaimValidator().validate((proposal(confidence=confidence),), PAGES)
        assert outcome.accepted == ()
        assert outcome.rejected[0].reason is ClaimRejectionReason.CONFIDENCE_OUT_OF_RANGE

    @pytest.mark.parametrize("confidence", [0.0, 1.0])
    def test_confidence_boundaries_are_inclusive(self, confidence: float) -> None:
        outcome = ClaimValidator().validate((proposal(confidence=confidence),), PAGES)
        assert len(outcome.accepted) == 1

    def test_empty_detail_or_snippet(self) -> None:
        for override in ({"detail": "   "}, {"evidence_snippet": ""}):
            outcome = ClaimValidator().validate((proposal(**override),), PAGES)
            assert outcome.accepted == ()
            assert outcome.rejected[0].reason is ClaimRejectionReason.EMPTY_FIELD

    def test_snippet_too_short_to_verify(self) -> None:
        outcome = ClaimValidator().validate((proposal(evidence_snippet="we"),), PAGES)
        assert outcome.accepted == ()
        assert outcome.rejected[0].reason is ClaimRejectionReason.SNIPPET_NOT_FOUND

    def test_every_rejection_produces_a_warning(self) -> None:
        outcome = ClaimValidator().validate(
            (
                proposal(kind="nope"),
                proposal(source_url="https://evil.example/"),
                proposal(evidence_snippet="entirely invented sentence here"),
                proposal(confidence=9.0),
            ),
            PAGES,
        )
        assert outcome.accepted == ()
        assert len(outcome.rejected) == 4
        assert len(outcome.warnings) == 4
        assert all(warning.startswith("claim rejected") for warning in outcome.warnings)

    def test_no_pages_means_nothing_can_be_validated(self) -> None:
        outcome = ClaimValidator().validate((proposal(),), ())
        assert outcome.accepted == ()
        assert outcome.rejected[0].reason is ClaimRejectionReason.UNFETCHED_SOURCE


class TestMixedBatch:
    def test_good_claims_survive_alongside_bad_ones(self) -> None:
        outcome = ClaimValidator().validate(
            (
                proposal(),
                proposal(kind="not_a_kind"),
                proposal(
                    kind="import_activity",
                    detail="import activity observed",
                    evidence_snippet="Acme Hardware imports fasteners from Asia.",
                    confidence=0.9,
                ),
                proposal(evidence_snippet="fabricated evidence that is not present"),
            ),
            PAGES,
        )
        assert len(outcome.accepted) == 2
        assert len(outcome.rejected) == 2
        assert {claim.kind for claim in outcome.accepted} == {
            "company_scale",
            "import_activity",
        }
