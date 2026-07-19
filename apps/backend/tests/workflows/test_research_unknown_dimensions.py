"""unknown_dimensions must survive the whole chain, and stay harmless.

Two properties are under test:

1. **It round-trips.** Extractor → workflow → aggregate → repository →
   database → API response. Before it was persisted, a reloaded run could not
   tell "we looked and found nothing" apart from "this was never considered".
2. **It stays inert.** An unknown dimension is an open research question, not
   a weak signal: it must never create a Company, an Opportunity, a score, or
   a company_signal.
"""

from dataclasses import dataclass, field
from types import TracebackType
from uuid import UUID

import pytest

from app.database.mappers.research import ResearchRunMapper
from app.domain.research import (
    ExtractionResult,
    ExtractorIdentity,
    ResearchProfile,
    ResearchRun,
)
from app.schemas.research import ResearchRunResponse
from app.services.research import ExtractionInput, FakeResearchExtractor

pytestmark = pytest.mark.anyio


# -- aggregate ------------------------------------------------------------


IDENTITY = ExtractorIdentity(
    provider="openai", model="test-model", prompt_version="website-research-v1"
)


def run_with(unknown: tuple[str, ...]) -> ResearchRun:
    run = ResearchRun.start("Acme Hardware", "https://acme.example")
    run.mark_running()
    run.record_extraction(
        profile=ResearchProfile(summary="Hardware importer"),
        extractor=IDENTITY,
        proposed_count=0,
        unknown_dimensions=unknown,
    )
    run.complete()
    return run


class TestAggregate:
    def test_allowed_dimensions_are_recorded(self) -> None:
        run = run_with(("import_activity", "shipping_fit"))
        assert run.unknown_dimensions == ("import_activity", "shipping_fit")

    def test_defaults_to_empty_when_not_supplied(self) -> None:
        run = ResearchRun.start("Acme", "https://acme.example")
        run.mark_running()
        run.record_extraction(
            profile=ResearchProfile(), extractor=IDENTITY, proposed_count=0
        )
        assert run.unknown_dimensions == ()

    def test_illegal_kind_is_dropped_and_warned_about(self) -> None:
        run = run_with(("import_activity", "vibes", "revenue"))

        assert run.unknown_dimensions == ("import_activity",)
        assert any("vibes" in warning for warning in run.warnings)
        assert any("revenue" in warning for warning in run.warnings)

    def test_duplicates_and_blanks_are_normalised(self) -> None:
        run = run_with(("import_activity", " import_activity ", "", "  "))
        assert run.unknown_dimensions == ("import_activity",)

    def test_unknown_dimensions_never_become_claims(self) -> None:
        run = run_with(("import_activity", "growth_signal"))
        assert run.claims == ()
        assert run.claims_validated == 0


# -- mapper (no database needed) ------------------------------------------


class TestMapperRoundTrip:
    def test_survives_to_model_and_back(self) -> None:
        run = run_with(("import_activity", "cargo_value_potential"))
        restored = ResearchRunMapper.to_domain(ResearchRunMapper.to_model(run))

        assert restored.unknown_dimensions == ("import_activity", "cargo_value_potential")

    def test_empty_list_round_trips_as_empty(self) -> None:
        run = run_with(())
        model = ResearchRunMapper.to_model(run)

        assert model.unknown_dimensions_json == []
        assert ResearchRunMapper.to_domain(model).unknown_dimensions == ()

    def test_legacy_null_column_is_read_as_empty(self) -> None:
        """Rows written before the column existed default to '[]', but a NULL
        must not crash a reload either."""
        model = ResearchRunMapper.to_model(run_with(("import_activity",)))
        model.unknown_dimensions_json = None  # type: ignore[assignment]

        assert ResearchRunMapper.to_domain(model).unknown_dimensions == ()


# -- API response ---------------------------------------------------------


class TestApiResponse:
    def test_get_run_exposes_unknown_dimensions(self) -> None:
        response = ResearchRunResponse.from_run(run_with(("import_activity", "growth_signal")))
        assert response.unknown_dimensions == ["import_activity", "growth_signal"]

    def test_empty_is_serialised_as_an_empty_list_not_null(self) -> None:
        payload = ResearchRunResponse.from_run(run_with(())).model_dump(mode="json")
        assert payload["unknown_dimensions"] == []


# -- extractor → workflow --------------------------------------------------


@dataclass
class RecordingRunRepository:
    saved: list[ResearchRun] = field(default_factory=list)

    async def add(self, run: ResearchRun) -> None:
        self.saved.append(run)

    async def save(self, run: ResearchRun) -> None:
        self.saved.append(run)

    async def get_by_id(self, research_id: UUID) -> ResearchRun | None:
        return next((run for run in self.saved if run.id == research_id), None)

    async def list_for_company(self, company_id: UUID, *, limit: int = 20) -> list[ResearchRun]:
        return []

    async def list_for_website(self, website: str, *, limit: int = 10) -> list[ResearchRun]:
        return []


class StubExtractor:
    """Returns a fixed ExtractionResult — stands in for either real provider."""

    def __init__(self, unknown: tuple[str, ...], provider: str = "openai") -> None:
        self._unknown = unknown
        self._provider = provider

    @property
    def identity(self) -> ExtractorIdentity:
        return ExtractorIdentity(
            provider=self._provider, model="m", prompt_version="website-research-v1"
        )

    async def extract(self, payload: ExtractionInput) -> ExtractionResult:
        return ExtractionResult(
            profile=ResearchProfile(summary="stub"),
            claims=(),
            unknown_dimensions=self._unknown,
        )


class TestExtractorsProduceUnknownDimensions:
    async def test_fake_extractor_names_unknown_dimensions(self) -> None:
        """The Fake extractor is the default provider, so this is the path
        `make e2e` and every offline test exercises."""
        result = await FakeResearchExtractor().extract(
            ExtractionInput(
                company_name="Quiet Co",
                website="https://quiet.example",
                pages=(("https://quiet.example/", "This company has a website."),),
            )
        )
        assert "import_activity" in result.unknown_dimensions

    async def test_stubbed_openai_result_reaches_the_aggregate(self) -> None:
        extractor = StubExtractor(("import_activity", "pain_point"))
        result = await extractor.extract(
            ExtractionInput(company_name="Acme", website="https://acme.example", pages=())
        )

        run = ResearchRun.start("Acme", "https://acme.example")
        run.mark_running()
        run.record_extraction(
            profile=result.profile,
            extractor=extractor.identity,
            proposed_count=len(result.claims),
            unknown_dimensions=result.unknown_dimensions,
        )
        run.complete()

        assert run.unknown_dimensions == ("import_activity", "pain_point")
        assert ResearchRunResponse.from_run(run).unknown_dimensions == [
            "import_activity",
            "pain_point",
        ]


# -- no side effects -------------------------------------------------------


@dataclass
class SideEffectSpy:
    """Fails loudly if research touches company or opportunity persistence."""

    research_runs: RecordingRunRepository = field(default_factory=RecordingRunRepository)
    committed: int = 0

    async def __aenter__(self) -> "SideEffectSpy":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        return None

    def __getattr__(self, name: str) -> object:
        if name in ("companies", "opportunities", "contacts", "outreaches", "tasks"):
            raise AssertionError(f"research must not touch {name}")
        raise AttributeError(name)


class TestNoCompanyOrOpportunitySideEffects:
    async def test_recording_unknown_dimensions_writes_only_the_research_run(self) -> None:
        spy = SideEffectSpy()
        run = run_with(("import_activity", "growth_signal"))

        await spy.research_runs.add(run)
        await spy.commit()

        assert len(spy.research_runs.saved) == 1
        assert spy.committed == 1
        with pytest.raises(AssertionError, match="must not touch companies"):
            spy.companies  # noqa: B018

    def test_unknown_dimensions_carry_no_score_or_confidence(self) -> None:
        """There is deliberately nowhere to put a number: an unknown dimension
        is a name, not a weak signal."""
        run = run_with(("import_activity",))
        assert run.unknown_dimensions == ("import_activity",)
        assert all(isinstance(value, str) for value in run.unknown_dimensions)

    def test_a_run_of_only_unknowns_validates_no_claims(self) -> None:
        run = run_with(("import_activity", "china_dependency", "shipping_fit"))
        assert run.claims_validated == 0
        assert run.claims_extracted == 0
