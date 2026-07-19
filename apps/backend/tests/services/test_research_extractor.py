"""FakeResearchExtractor: deterministic, offline, and honest.

Honest matters most — everything it proposes must survive the validator, so
the fake can never mask a validation bug by producing unverifiable claims.
"""

from datetime import UTC, datetime

from app.domain.research import ALLOWED_CLAIM_KINDS, ResearchPage
from app.services.research import (
    ClaimValidator,
    ExtractionInput,
    FakeResearchExtractor,
    PageContent,
)

FIXED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)

HOME = (
    "Acme Hardware imports fasteners and tools from China. "
    "We operate a 120,000 sq ft warehouse in Long Beach. "
    "Our FCL ocean freight arrives weekly from Shenzhen. "
    "We are growing and hiring across the distribution center network."
)

PAYLOAD = ExtractionInput(
    company_name="Acme Hardware",
    website="https://acme.example",
    pages=(("https://acme.example/", HOME),),
)


class TestDeterminism:
    async def test_same_input_same_output(self) -> None:
        extractor = FakeResearchExtractor()
        first = await extractor.extract(PAYLOAD)
        second = await extractor.extract(PAYLOAD)
        assert first == second

    async def test_identity_is_reported(self) -> None:
        identity = FakeResearchExtractor().identity
        assert identity.provider == "fake"
        assert identity.model == "fake-research-v1"
        assert identity.prompt_version


class TestOutputShape:
    async def test_proposes_only_allowed_kinds(self) -> None:
        result = await FakeResearchExtractor().extract(PAYLOAD)
        assert result.claims
        for claim in result.claims:
            assert claim.kind in ALLOWED_CLAIM_KINDS

    async def test_confidence_within_zero_to_one(self) -> None:
        result = await FakeResearchExtractor().extract(PAYLOAD)
        for claim in result.claims:
            assert 0.0 <= claim.confidence <= 1.0

    async def test_cites_only_supplied_urls(self) -> None:
        """The fake must not invent a source any more than a real model may."""
        result = await FakeResearchExtractor().extract(PAYLOAD)
        supplied = {url for url, _ in PAYLOAD.pages}
        assert all(claim.source_url in supplied for claim in result.claims)

    async def test_names_unknown_dimensions_instead_of_guessing(self) -> None:
        sparse = ExtractionInput(
            company_name="Quiet Co",
            website="https://quiet.example",
            pages=(("https://quiet.example/", "This company has a website and little else."),),
        )
        result = await FakeResearchExtractor().extract(sparse)
        assert result.unknown_dimensions
        assert "import_activity" in result.unknown_dimensions

    async def test_empty_input_yields_no_claims_and_no_crash(self) -> None:
        result = await FakeResearchExtractor().extract(
            ExtractionInput(company_name="X", website="https://x.example", pages=())
        )
        assert result.claims == ()


class TestValidatorCompatibility:
    async def test_every_proposed_claim_survives_validation(self) -> None:
        """The fake's evidence snippets are real substrings of the pages it was
        given, so nothing it proposes may be rejected."""
        result = await FakeResearchExtractor().extract(PAYLOAD)
        pages = tuple(
            PageContent(
                page=ResearchPage(
                    position=index,
                    url=url,
                    final_url=url,
                    http_status=200,
                    content_type="text/html",
                    fetched_at=FIXED_AT,
                    content_chars=len(text),
                ),
                cleaned_text=text,
            )
            for index, (url, text) in enumerate(PAYLOAD.pages)
        )
        outcome = ClaimValidator().validate(result.claims, pages)
        assert outcome.rejected == (), outcome.warnings
        assert len(outcome.accepted) == len(result.claims)
