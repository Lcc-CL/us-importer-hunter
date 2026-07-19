"""Localized conclusions, verbatim evidence.

The split under test is the whole point: `detail`, `company_profile` and
`warnings` are written for a reviewer and may be translated; `evidence_snippet`
is quoted for ClaimValidator and may not. Translating evidence would make it
unverifiable, which is the one failure mode this system is built to prevent.
"""

import json
from datetime import UTC, datetime
from typing import Any, cast

from app.database.mappers.research import ResearchRunMapper
from app.domain.research import (
    ExtractorIdentity,
    OutputLanguage,
    ResearchPage,
    ResearchProfile,
    ResearchRun,
)
from app.prompts.research.website_research import system_prompt_for
from app.schemas.research import ResearchRunRequest, ResearchRunResponse
from app.services.research import (
    ClaimValidator,
    ExtractionInput,
    FakeResearchExtractor,
    OpenAIResearchExtractor,
    PageContent,
)

FIXED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
URL = "https://acme.example/"

ENGLISH_PAGE = (
    "Acme Hardware imports fasteners and tools from China every month. "
    "We operate a 120,000 sq ft warehouse in Long Beach. "
    "Our FCL ocean freight arrives weekly from Shenzhen. "
    "We are growing and hiring across the distribution center network."
)


def payload(language: OutputLanguage) -> ExtractionInput:
    return ExtractionInput(
        company_name="Acme Hardware",
        website="https://acme.example",
        pages=((URL, ENGLISH_PAGE),),
        output_language=language,
    )


def has_han(value: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in value)


# -- Fake extractor -------------------------------------------------------


class TestFakeExtractorIsBilingual:
    """The Fake backs `make e2e`. If it only spoke English, the browser suite
    would pass on behaviour the real provider does not have."""

    async def test_english_conclusions_by_default(self) -> None:
        result = await FakeResearchExtractor().extract(payload(OutputLanguage.EN_US))

        assert result.claims
        assert not any(has_han(claim.detail) for claim in result.claims)

    async def test_chinese_conclusions_when_asked(self) -> None:
        result = await FakeResearchExtractor().extract(payload(OutputLanguage.ZH_CN))

        assert result.claims
        assert all(has_han(claim.detail) for claim in result.claims)
        assert any(has_han(note) for note in result.notes)

    async def test_evidence_stays_in_the_pages_language(self) -> None:
        result = await FakeResearchExtractor().extract(payload(OutputLanguage.ZH_CN))

        for claim in result.claims:
            assert not has_han(claim.evidence_snippet), "evidence must not be translated"
            assert claim.evidence_snippet in ENGLISH_PAGE

    async def test_chinese_claims_still_pass_validation(self) -> None:
        """A localized detail must not cost the claim its verifiability."""
        result = await FakeResearchExtractor().extract(payload(OutputLanguage.ZH_CN))
        content = PageContent(
            page=ResearchPage(
                position=0,
                url=URL,
                final_url=URL,
                http_status=200,
                content_type="text/html",
                fetched_at=FIXED_AT,
                content_chars=len(ENGLISH_PAGE),
            ),
            cleaned_text=ENGLISH_PAGE,
        )
        outcome = ClaimValidator().validate(result.claims, (content,))

        assert outcome.rejected == ()
        assert len(outcome.accepted) == len(result.claims)

    async def test_same_language_same_output(self) -> None:
        first = await FakeResearchExtractor().extract(payload(OutputLanguage.ZH_CN))
        second = await FakeResearchExtractor().extract(payload(OutputLanguage.ZH_CN))
        assert first == second


# -- prompt ---------------------------------------------------------------


class TestPromptCarriesTheLanguageContract:
    def test_chinese_prompt_asks_for_simplified_chinese(self) -> None:
        prompt = system_prompt_for(OutputLanguage.ZH_CN)
        assert "Simplified Chinese" in prompt
        assert "简体中文" in prompt

    def test_chinese_prompt_forbids_translating_evidence(self) -> None:
        prompt = system_prompt_for(OutputLanguage.ZH_CN)
        assert "Never translate it" in prompt
        assert "verbatim" in prompt

    def test_english_prompt_asks_for_english(self) -> None:
        prompt = system_prompt_for(OutputLanguage.EN_US)
        assert "in English" in prompt
        assert "Never translate" in prompt

    def test_both_languages_keep_the_base_rules(self) -> None:
        for language in OutputLanguage:
            prompt = system_prompt_for(language)
            assert "UNTRUSTED THIRD-PARTY DATA" in prompt
            assert "Absent evidence is never a claim" in prompt


# -- OpenAI extractor (mocked) --------------------------------------------


class FakeResponse:
    def __init__(self, content: str) -> None:
        message = type("Message", (), {"content": content})()
        self.choices = [type("Choice", (), {"message": message})()]
        self.usage = None


class FakeCompletions:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response: Any) -> None:
        self.completions = FakeCompletions(response)
        self.chat = type("Chat", (), {"completions": self.completions})()


CHINESE_BODY = json.dumps(
    {
        "company_profile": {"summary": "Acme 是一家进口五金件的美国分销商。"},
        "claims": [
            {
                "kind": "import_activity",
                "detail": "该公司每月从中国进口紧固件和工具。",
                "source_url": URL,
                "evidence_snippet": (
                    "Acme Hardware imports fasteners and tools from China every month."
                ),
                "confidence": 0.9,
            }
        ],
        "unknown_dimensions": ["cargo_value_potential"],
        "warnings": ["该网站未说明具体货量。"],
    },
    ensure_ascii=False,
)


class TestOpenAIExtractorLanguage:
    def _extractor(self, response: Any) -> OpenAIResearchExtractor:
        return OpenAIResearchExtractor(
            model="test-model", api_key="sk-test-not-real", client=FakeClient(response)
        )

    async def test_chinese_run_sends_the_chinese_system_prompt(self) -> None:
        instance = self._extractor(FakeResponse(CHINESE_BODY))
        await instance.extract(payload(OutputLanguage.ZH_CN))
        client = cast(FakeClient, instance._client)
        system = client.completions.calls[0]["messages"][0]["content"]

        assert "简体中文" in system

    async def test_english_run_sends_the_english_system_prompt(self) -> None:
        instance = self._extractor(FakeResponse(CHINESE_BODY))
        await instance.extract(payload(OutputLanguage.EN_US))
        client = cast(FakeClient, instance._client)
        system = client.completions.calls[0]["messages"][0]["content"]

        assert "简体中文" not in system
        assert "in English" in system

    async def test_chinese_conclusions_parse_and_evidence_survives_validation(self) -> None:
        result = await self._extractor(FakeResponse(CHINESE_BODY)).extract(
            payload(OutputLanguage.ZH_CN)
        )

        assert has_han(result.claims[0].detail)
        assert has_han(str(result.profile.summary))
        assert any(has_han(note) for note in result.notes)
        assert not has_han(result.claims[0].evidence_snippet)

        content = PageContent(
            page=ResearchPage(
                position=0,
                url=URL,
                final_url=URL,
                http_status=200,
                content_type="text/html",
                fetched_at=FIXED_AT,
                content_chars=len(ENGLISH_PAGE),
            ),
            cleaned_text=ENGLISH_PAGE,
        )
        outcome = ClaimValidator().validate(result.claims, (content,))
        assert outcome.rejected == ()


# -- persistence and API --------------------------------------------------


def run_with(language: OutputLanguage) -> ResearchRun:
    run = ResearchRun.start("Acme", "https://acme.example", output_language=language)
    run.mark_running()
    run.record_extraction(
        profile=ResearchProfile(summary="摘要"),
        extractor=ExtractorIdentity(
            provider="openai", model="m", prompt_version="website-research-v1"
        ),
        proposed_count=0,
    )
    run.complete()
    return run


class TestLanguagePersistence:
    def test_default_is_english(self) -> None:
        assert ResearchRun.start("A", "https://a.example").output_language is (
            OutputLanguage.EN_US
        )

    def test_language_round_trips_through_the_mapper(self) -> None:
        run = run_with(OutputLanguage.ZH_CN)
        restored = ResearchRunMapper.to_domain(ResearchRunMapper.to_model(run))

        assert restored.output_language is OutputLanguage.ZH_CN

    def test_reload_reports_the_language_it_was_produced_in(self) -> None:
        response = ResearchRunResponse.from_run(run_with(OutputLanguage.ZH_CN))
        assert response.output_language == "zh-CN"

    def test_legacy_rows_without_a_language_read_as_english(self) -> None:
        model = ResearchRunMapper.to_model(run_with(OutputLanguage.ZH_CN))
        model.output_language = ""  # a row written before the column existed

        assert ResearchRunMapper.to_domain(model).output_language is OutputLanguage.EN_US

    def test_unknown_locale_falls_back_instead_of_raising(self) -> None:
        """A research run costs a real request; a stray locale string must not
        throw it away."""
        assert OutputLanguage.parse("fr-FR") is OutputLanguage.EN_US
        assert OutputLanguage.parse(None) is OutputLanguage.EN_US
        assert OutputLanguage.parse(" zh-CN ") is OutputLanguage.ZH_CN


class TestApiContract:
    def test_request_defaults_to_english(self) -> None:
        request = ResearchRunRequest(company_name="A", website="https://a.example")
        assert request.output_language == "en-US"

    def test_request_accepts_chinese(self) -> None:
        request = ResearchRunRequest(
            company_name="A", website="https://a.example", output_language="zh-CN"
        )
        assert request.output_language == "zh-CN"
