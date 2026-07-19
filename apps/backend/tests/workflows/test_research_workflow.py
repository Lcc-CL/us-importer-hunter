"""ResearchWorkflow: website → validated claims, and nothing else.

The fetcher is stubbed, so these tests are offline and deterministic. The
extractor is the real Fake one — it is part of the contract under test.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from uuid import UUID, uuid4

import httpx
import pytest

from app.domain.company import Company
from app.domain.repositories import (
    CompanyRepository,
    ContactRepository,
    OpportunityRepository,
    OutreachRepository,
    ResearchRunRepository,
    TaskRepository,
)
from app.domain.research import ResearchFailureCode, ResearchRun, ResearchRunStatus
from app.domain.values import CompanyName, WebsiteUrl
from app.services.research import ClaimValidator, ExtractionInput, FakeResearchExtractor
from app.tools.website import FetchedPage, FetchFailure, FetchOutcome, SiteScope
from app.workflows.research import ResearchAction, ResearchLimits, ResearchWorkflow

WEBSITE = "https://acme.example"

HOME_HTML = """
<html><head><title>Acme Hardware</title></head><body>
  <a href="/about">About us</a>
  <a href="/products">Products</a>
  <a href="/cart">Cart</a>
  <a href="https://linkedin.com/company/acme">LinkedIn</a>
  <main>
    <p>Acme Hardware imports fasteners and tools from China every month.</p>
    <p>We operate a 120,000 sq ft warehouse in Long Beach, California.</p>
    <p>Our FCL ocean freight arrives weekly from Shenzhen and Ningbo.</p>
    <p>We are growing and hiring across our distribution center network.</p>
  </main>
</body></html>
"""

ABOUT_HTML = """
<html><body><main>
  <p>Founded in 1961, Acme has grown its import volume every year since 2019.</p>
  <p>Our customers include national retail chains across the United States.</p>
</main></body></html>
"""

JS_SHELL_HTML = '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'


# --- fakes -----------------------------------------------------------------


class FakeCompanyRepository:
    """Implements the full CompanyRepository protocol; the workflow only reads."""

    def __init__(self, companies: dict[UUID, Company] | None = None) -> None:
        self._companies = companies or {}

    async def get_by_id(self, company_id: UUID) -> Company | None:
        return self._companies.get(company_id)

    async def add(self, company: Company) -> None:
        self._companies[company.id] = company

    async def save(self, company: Company) -> None:
        self._companies[company.id] = company

    async def exists(self, company_id: UUID) -> bool:
        return company_id in self._companies

    async def find_by_normalized_name(self, name: CompanyName) -> Company | None:
        return next(
            (c for c in self._companies.values() if c.name.normalized == name.normalized), None
        )

    async def find_by_website_host(self, host: str) -> Company | None:
        return next(
            (
                c
                for c in self._companies.values()
                if c.website and c.website.host == host.lower()
            ),
            None,
        )


class FakeResearchRunRepository:
    def __init__(self) -> None:
        self.saved: list[ResearchRun] = []

    async def get_by_id(self, research_id: UUID) -> ResearchRun | None:
        return next((run for run in self.saved if run.id == research_id), None)

    async def add(self, run: ResearchRun) -> None:
        self.saved.append(run)

    async def save(self, run: ResearchRun) -> None:
        self.saved.append(run)

    async def list_for_website(self, website: str, *, limit: int = 10) -> list[ResearchRun]:
        return [run for run in self.saved if run.website == website][:limit]


@dataclass
class FakeUnitOfWork:
    companies: CompanyRepository
    research_runs: ResearchRunRepository
    contacts: ContactRepository = None  # type: ignore[assignment]
    opportunities: OpportunityRepository = None  # type: ignore[assignment]
    outreaches: OutreachRepository = None  # type: ignore[assignment]
    tasks: TaskRepository = None  # type: ignore[assignment]
    committed: int = 0

    async def __aenter__(self) -> "FakeUnitOfWork":
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


@dataclass
class StubFetcher:
    """Serves canned responses by URL; anything unmapped is a failure.

    Satisfies the PageFetcher protocol, which is all the workflow and robots
    loading depend on — no SafeFetcher internals are reachable from here.
    """

    responses: dict[str, FetchOutcome] = field(default_factory=dict)
    requested: list[str] = field(default_factory=list)

    async def fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        accept: tuple[str, ...] = ("text/html",),
    ) -> FetchOutcome:
        self.requested.append(url)
        if url in self.responses:
            return self.responses[url]
        return FetchFailure(requested_url=url, code="http_error", detail="HTTP 404")


class StubClient:
    """Stands in for httpx.AsyncClient — the stub fetcher never uses it."""

    async def __aenter__(self) -> "StubClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(404)


def page(url: str, html: str) -> FetchedPage:
    return FetchedPage(
        requested_url=url,
        final_url=url,
        status_code=200,
        content_type="text/html",
        html=html,
        bytes_read=len(html),
        truncated=False,
        redirect_hops=0,
        elapsed_ms=12,
    )


# --- harness ---------------------------------------------------------------


@dataclass
class Harness:
    workflow: ResearchWorkflow
    runs: FakeResearchRunRepository
    fetcher: StubFetcher
    company: Company


def build(
    responses: dict[str, FetchOutcome] | None = None,
    *,
    with_company: bool = True,
    limits: ResearchLimits | None = None,
    now: Callable[[], float] | None = None,
) -> Harness:
    company = Company.create(CompanyName("Acme Hardware"), WebsiteUrl(WEBSITE))
    companies = FakeCompanyRepository({company.id: company} if with_company else {})
    runs = FakeResearchRunRepository()
    fetcher = StubFetcher(responses=responses or {})

    def uow_factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(companies=companies, research_runs=runs)

    workflow = ResearchWorkflow(
        uow_factory=uow_factory,
        extractor=FakeResearchExtractor(),
        fetcher_factory=lambda scope: fetcher,
        client_factory=StubClient,  # type: ignore[arg-type]
        validator=ClaimValidator(),
        limits=limits or ResearchLimits(request_delay_seconds=0.0),
        now=now or (lambda: 0.0),
    )
    return Harness(workflow=workflow, runs=runs, fetcher=fetcher, company=company)


# --- tests -----------------------------------------------------------------


class TestSuccessfulResearch:
    async def test_completes_and_persists_validated_claims(self) -> None:
        harness = build(
            {
                WEBSITE: page(WEBSITE, HOME_HTML),
                "https://acme.example/about": page("https://acme.example/about", ABOUT_HTML),
                "https://acme.example/products": page(
                    "https://acme.example/products", ABOUT_HTML
                ),
            }
        )
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )

        assert outcome.action is ResearchAction.COMPLETED
        assert outcome.status is ResearchRunStatus.COMPLETED
        assert outcome.failure_code is None
        assert outcome.pages_fetched >= 2
        assert outcome.claims_validated > 0
        assert outcome.claims_validated == outcome.claims_extracted

        saved = harness.runs.saved[0]
        assert saved.company_name == "Acme Hardware"
        assert saved.extractor is not None and saved.extractor.provider == "fake"

    async def test_every_claim_traces_to_a_fetched_page(self) -> None:
        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})
        await harness.workflow.handle(company_id=harness.company.id, website=WEBSITE)

        saved = harness.runs.saved[0]
        fetched = {p.position for p in saved.pages}
        for claim in saved.claims:
            assert claim.source_page_position in fetched
            cited = saved.page_at(claim.source_page_position)
            assert cited is not None
            assert claim.evidence_snippet

    async def test_page_discovery_is_deterministic_and_on_site(self) -> None:
        """Junk and off-site links must never be requested."""
        harness = build(
            {
                WEBSITE: page(WEBSITE, HOME_HTML),
                "https://acme.example/about": page("https://acme.example/about", ABOUT_HTML),
                "https://acme.example/products": page(
                    "https://acme.example/products", ABOUT_HTML
                ),
            }
        )
        await harness.workflow.handle(company_id=harness.company.id, website=WEBSITE)

        assert not any("linkedin.com" in url for url in harness.fetcher.requested)
        assert not any("/cart" in url for url in harness.fetcher.requested)

    async def test_does_not_touch_company_signals(self) -> None:
        """The workflow proposes; it never writes company state."""
        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})
        before = harness.company.signals
        await harness.workflow.handle(company_id=harness.company.id, website=WEBSITE)
        assert harness.company.signals == before == ()
        assert harness.company.sources == ()


class TestPartialResearch:
    async def test_subpage_failures_make_the_run_partial(self) -> None:
        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})  # sub-pages 404
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )

        assert outcome.action is ResearchAction.PARTIAL
        assert outcome.pages_fetched == 1
        assert outcome.pages_failed > 0
        assert any("could not be read" in warning for warning in outcome.warnings)
        # Partial still produces usable claims from what was read.
        assert outcome.claims_validated > 0

    async def test_js_shell_reports_needs_browser(self) -> None:
        harness = build({WEBSITE: page(WEBSITE, JS_SHELL_HTML)})
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )

        assert outcome.action is ResearchAction.PARTIAL
        assert outcome.failure_code is ResearchFailureCode.NEEDS_BROWSER
        assert any("requires a browser" in warning for warning in outcome.warnings)

    async def test_time_budget_stops_further_fetching(self) -> None:
        """The homepage is always read; the budget then stops sub-pages.

        The first clock read establishes the deadline, every later read is past
        it — so the loop breaks before requesting anything more.
        """
        reads = {"count": 0}

        def clock() -> float:
            reads["count"] += 1
            return 0.0 if reads["count"] == 1 else 999.0

        harness = build(
            {
                WEBSITE: page(WEBSITE, HOME_HTML),
                "https://acme.example/about": page("https://acme.example/about", ABOUT_HTML),
            },
            limits=ResearchLimits(total_budget_seconds=1.0),
            now=clock,
        )
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )

        assert outcome.action is ResearchAction.PARTIAL
        assert outcome.failure_code is ResearchFailureCode.BUDGET_EXCEEDED
        assert outcome.pages_fetched == 1
        assert any("time budget exhausted" in warning for warning in outcome.warnings)

    async def test_truncation_is_warned_not_hidden(self) -> None:
        harness = build(
            {WEBSITE: page(WEBSITE, HOME_HTML)},
            limits=ResearchLimits(max_page_chars=80),
        )
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )
        assert any("truncated" in warning for warning in outcome.warnings)


class TestValidationRejection:
    async def test_invented_claims_are_rejected_and_warned(self) -> None:
        """An extractor citing a page it was never given must not persist."""

        class LyingExtractor:
            @property
            def identity(self) -> object:
                return FakeResearchExtractor().identity

            async def extract(self, payload: ExtractionInput) -> object:
                from app.domain.research import (
                    ExtractionResult,
                    ProposedClaim,
                    ResearchProfile,
                )

                return ExtractionResult(
                    profile=ResearchProfile(summary="fabricated"),
                    claims=(
                        ProposedClaim(
                            kind="company_scale",
                            detail="invented",
                            evidence_snippet="We ship 50,000 containers every single year.",
                            source_url=payload.pages[0][0],
                            confidence=0.9,
                        ),
                        ProposedClaim(
                            kind="not_a_real_kind",
                            detail="bad kind",
                            evidence_snippet="Acme Hardware imports fasteners",
                            source_url=payload.pages[0][0],
                            confidence=0.5,
                        ),
                        ProposedClaim(
                            kind="import_activity",
                            detail="cites a page we never fetched",
                            evidence_snippet="Acme Hardware imports fasteners",
                            source_url="https://evil.example/inject",
                            confidence=0.5,
                        ),
                        ProposedClaim(
                            kind="growth_signal",
                            detail="confidence out of range",
                            evidence_snippet="Acme Hardware imports fasteners",
                            source_url=payload.pages[0][0],
                            confidence=7.0,
                        ),
                    ),
                )

        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})
        harness.workflow.extractor = LyingExtractor()  # type: ignore[assignment]

        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )

        assert outcome.claims_extracted == 4
        assert outcome.claims_validated == 0
        saved = harness.runs.saved[0]
        assert saved.claims == ()
        assert len(saved.rejected_claims) == 4
        assert len(outcome.warnings) >= 4
        assert all(
            any(warning.startswith("claim rejected") for warning in outcome.warnings)
            for _ in saved.rejected_claims
        )

    async def test_valid_claims_survive_alongside_rejected_ones(self) -> None:
        class MixedExtractor:
            @property
            def identity(self) -> object:
                return FakeResearchExtractor().identity

            async def extract(self, payload: ExtractionInput) -> object:
                from app.domain.research import (
                    ExtractionResult,
                    ProposedClaim,
                    ResearchProfile,
                )

                real = "We operate a 120,000 sq ft warehouse in Long Beach, California."
                return ExtractionResult(
                    profile=ResearchProfile(),
                    claims=(
                        ProposedClaim(
                            kind="company_scale",
                            detail="real claim",
                            evidence_snippet=real,
                            source_url=payload.pages[0][0],
                            confidence=0.8,
                        ),
                        ProposedClaim(
                            kind="cargo_value_potential",
                            detail="invented",
                            evidence_snippet="Annual revenue exceeds one billion dollars.",
                            source_url=payload.pages[0][0],
                            confidence=0.9,
                        ),
                    ),
                )

        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})
        harness.workflow.extractor = MixedExtractor()  # type: ignore[assignment]

        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )
        assert outcome.claims_extracted == 2
        assert outcome.claims_validated == 1
        saved = harness.runs.saved[0]
        assert saved.claims[0].kind == "company_scale"
        assert len(saved.rejected_claims) == 1


class TestFailedResearch:
    async def test_unknown_company_is_rejected_without_a_run(self) -> None:
        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)}, with_company=False)
        outcome = await harness.workflow.handle(company_id=uuid4(), website=WEBSITE)

        assert outcome.action is ResearchAction.REJECTED
        assert outcome.research_id is None
        assert harness.runs.saved == []
        assert harness.fetcher.requested == []

    async def test_unreachable_homepage_fails_the_run(self) -> None:
        harness = build({})  # nothing serves
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )

        assert outcome.action is ResearchAction.FAILED
        assert outcome.status is ResearchRunStatus.FAILED
        assert outcome.failure_code is ResearchFailureCode.UNREACHABLE
        assert outcome.pages_fetched == 0
        assert outcome.claims_validated == 0
        # A failed run is still persisted — it is the audit record.
        assert len(harness.runs.saved) == 1

    async def test_invalid_website_fails_before_any_request(self) -> None:
        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website="not-a-url"
        )

        assert outcome.action is ResearchAction.FAILED
        assert outcome.failure_code is ResearchFailureCode.INVALID_URL
        assert harness.fetcher.requested == []

    async def test_guard_rejection_is_reported_not_raised(self) -> None:
        """A blocked URL is a recorded failure, never an exception."""
        harness = build(
            {
                WEBSITE: FetchFailure(
                    requested_url=WEBSITE,
                    code="private_address",
                    detail="host resolves to a non-public address",
                )
            }
        )
        outcome = await harness.workflow.handle(
            company_id=harness.company.id, website=WEBSITE
        )
        assert outcome.action is ResearchAction.FAILED
        assert any("private_address" in warning for warning in outcome.warnings)


class TestPersistence:
    async def test_run_is_committed_once(self) -> None:
        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})
        await harness.workflow.handle(company_id=harness.company.id, website=WEBSITE)
        assert len(harness.runs.saved) == 1

    async def test_site_scope_comes_from_the_requested_website(self) -> None:
        harness = build({WEBSITE: page(WEBSITE, HOME_HTML)})
        captured: list[SiteScope] = []

        def capturing_factory(scope: SiteScope) -> StubFetcher:
            captured.append(scope)
            return harness.fetcher

        harness.workflow.fetcher_factory = capturing_factory
        await harness.workflow.handle(company_id=harness.company.id, website=WEBSITE)

        assert captured and captured[0].bare_host == "acme.example"


@pytest.mark.parametrize(
    "website", ["https://acme.example", "https://acme.example/", "https://www.acme.example"]
)
async def test_accepts_common_website_forms(website: str) -> None:
    harness = build({website: page(website, HOME_HTML)})
    outcome = await harness.workflow.handle(company_id=harness.company.id, website=website)
    assert outcome.action in (ResearchAction.COMPLETED, ResearchAction.PARTIAL)
