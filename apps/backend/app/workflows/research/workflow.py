"""Research application workflow: a website → validated claims.

Orchestration only. It fetches, cleans, extracts and validates, then persists
one ResearchRun. It deliberately does **not**:

- write company_signals or any Company / Opportunity state (ADR-0025);
- call qualification, decision-maker selection or draft generation;
- ask a model which pages to visit — page selection is the deterministic
  page_ranker, which is what stops page content from steering the crawler
  (ADR-0025 §6).

Everything carrying a policy (fetching, extraction, validation, limits) is
injected, so the workflow itself stays a readable sequence of steps.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

import httpx

from app.domain.clock import utcnow
from app.domain.repositories import UnitOfWork
from app.domain.research import (
    OutputLanguage,
    ResearchFailureCode,
    ResearchPage,
    ResearchProfile,
    ResearchRun,
    ResearchRunStatus,
)
from app.services.research import (
    ClaimValidator,
    ExtractionError,
    ExtractionInput,
    PageContent,
    ResearchExtractor,
)
from app.tools.website import (
    CleanedPage,
    FetchedPage,
    PageFetcher,
    SiteScope,
    clean_html,
    create_research_client,
    extract_links,
    load_robots,
    rank_pages,
)


class ResearchAction(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    REJECTED = "rejected"


class ResearchInputError(Exception):
    """The request cannot be turned into a runnable research command."""


@dataclass(frozen=True)
class ResearchRequest:
    """Two ways to ask for research, validated here so the workflow body has
    no branching on which one it got.

    A. An existing company — `company_id` is given. The name snapshot comes
       from the database, and `website` defaults to the company's own website.
    B. A prospect not yet in the database — `company_name` and `website` are
       given, `company_id` stays None. No Company is created.
    """

    company_id: UUID | None = None
    company_name: str | None = None
    website: str | None = None
    #: Language for conclusions. Evidence is never translated.
    output_language: OutputLanguage = OutputLanguage.EN_US

    def __post_init__(self) -> None:
        if self.company_id is None:
            if not (self.company_name or "").strip():
                raise ResearchInputError(
                    "company_name is required when company_id is not given"
                )
            if not (self.website or "").strip():
                raise ResearchInputError("website is required when company_id is not given")


@dataclass(frozen=True)
class ResearchOutcome:
    action: ResearchAction
    company_id: UUID | None
    research_id: UUID | None = None
    status: ResearchRunStatus | None = None
    failure_code: ResearchFailureCode | None = None
    pages_fetched: int = 0
    pages_failed: int = 0
    claims_extracted: int = 0
    claims_validated: int = 0
    unknown_dimensions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchLimits:
    """Mirrors the settings block; injected so the workflow has no globals."""

    max_pages: int = 5
    max_page_chars: int = 40_000
    total_budget_seconds: float = 45.0
    request_delay_seconds: float = 0.0
    user_agent: str = "USImporterHunterBot/0.2"
    thin_page_chars: int = 200


@dataclass(frozen=True)
class ReadPage:
    """One page we read: its record, its cleaned text, and the HTML it came
    from. The raw HTML exists only to extract links and is never persisted."""

    record: ResearchPage
    cleaned: CleanedPage
    raw_html: str


#: Builds a fetcher bound to one site's scope. SafeFetcher satisfies PageFetcher.
FetcherFactory = Callable[[SiteScope], PageFetcher]
ClientFactory = Callable[[], httpx.AsyncClient]


@dataclass
class ResearchWorkflow:
    uow_factory: Callable[[], UnitOfWork]
    extractor: ResearchExtractor
    fetcher_factory: FetcherFactory
    client_factory: ClientFactory = create_research_client
    validator: ClaimValidator = field(default_factory=ClaimValidator)
    limits: ResearchLimits = field(default_factory=ResearchLimits)
    now: Callable[[], float] = time.monotonic

    async def handle(self, request: ResearchRequest) -> ResearchOutcome:
        resolved = await self._resolve(request)
        if resolved is None:
            return ResearchOutcome(
                action=ResearchAction.REJECTED,
                company_id=request.company_id,
                notes=("company not found — nothing to research",),
            )
        company_name, website = resolved

        run = ResearchRun.start(
            company_name,
            website,
            company_id=request.company_id,
            output_language=request.output_language,
        )
        run.mark_running()

        try:
            scope = SiteScope.from_url(website)
        except ValueError:
            run.fail(ResearchFailureCode.INVALID_URL, f"unusable website url: {website!r}")
            return await self._persist(run)

        pages, budget_exhausted, aborted = await self._collect_pages(run, website, scope)
        if aborted is not None:
            return await self._persist(run)

        extraction_failed = await self._extract_and_validate(run, company_name, website, pages)

        failure_code = extraction_failed or self._failure_code(pages, budget_exhausted, run)
        run.complete(
            partial=bool(failure_code) or run.pages_failed > 0, failure_code=failure_code
        )
        return await self._persist(run)

    # -- steps ----------------------------------------------------------

    async def _resolve(self, request: ResearchRequest) -> tuple[str, str] | None:
        """(company_name, website), or None when a named company is missing.

        Reading the company is the only thing this workflow ever does to
        Company state — it never writes.
        """
        if request.company_id is None:
            # ResearchRequest already guaranteed both are present.
            return str(request.company_name), str(request.website)

        async with self.uow_factory() as uow:
            company = await uow.companies.get_by_id(request.company_id)
        if company is None:
            return None

        website = (request.website or "").strip() or (
            company.website.value if company.website else ""
        )
        if not website:
            return None
        return company.name.value, website

    async def _collect_pages(
        self, run: ResearchRun, website: str, scope: SiteScope
    ) -> tuple[list[ReadPage], bool, ResearchFailureCode | None]:
        """Homepage, then deterministically ranked sub-pages within budget."""
        deadline = self.now() + self.limits.total_budget_seconds
        pages: list[ReadPage] = []
        fetcher = self.fetcher_factory(scope)

        async with self.client_factory() as client:
            robots = await load_robots(client, fetcher, website, self.limits.user_agent)
            if robots.note:
                run.add_warning(robots.note)
            if not robots.allows(website):
                run.fail(
                    ResearchFailureCode.ROBOTS_DENIED,
                    f"robots.txt disallows the homepage: {website}",
                )
                return pages, False, ResearchFailureCode.ROBOTS_DENIED

            home = await self._read(client, fetcher, run, website, 0, "homepage")
            if home is None:
                run.fail(
                    ResearchFailureCode.UNREACHABLE, f"homepage could not be read: {website}"
                )
                return pages, False, ResearchFailureCode.UNREACHABLE
            pages.append(home)

            budget_exhausted = False
            for ranked in rank_pages(
                base_url=website,
                links=extract_links(home.raw_html),
                scope=scope,
                limit=self.limits.max_pages - 1,
            ):
                if self.now() >= deadline:
                    budget_exhausted = True
                    run.add_warning("time budget exhausted — extracting from pages read so far")
                    break
                if not robots.allows(ranked.url):
                    run.add_warning(f"robots.txt disallows {ranked.url}")
                    continue
                page = await self._read(
                    client, fetcher, run, ranked.url, len(pages), ranked.discovery_reason
                )
                if page is not None:
                    pages.append(page)

        return pages, budget_exhausted, None

    async def _read(
        self,
        client: httpx.AsyncClient,
        fetcher: PageFetcher,
        run: ResearchRun,
        url: str,
        position: int,
        reason: str,
    ) -> ReadPage | None:
        if self.limits.request_delay_seconds:
            await asyncio.sleep(self.limits.request_delay_seconds)

        result = await fetcher.fetch(client, url)
        if not isinstance(result, FetchedPage):
            run.record_page_failure(f"{url} could not be read ({result.code}): {result.detail}")
            return None

        content = clean_html(result.html, max_chars=self.limits.max_page_chars)
        record = ResearchPage(
            position=position,
            url=result.requested_url,
            final_url=result.final_url,
            http_status=result.status_code,
            content_type=result.content_type,
            fetched_at=utcnow(),
            content_chars=content.char_count,
            bytes_read=result.bytes_read,
            truncated=content.truncated,
            discovery_reason=reason,
        )
        run.record_page(record)
        if content.truncated:
            run.add_warning(f"{url} was truncated at {self.limits.max_page_chars} characters")
        for hit in content.injection_hits:
            run.add_warning(f"{url} contains suspicious instruction text: {hit!r}")
        return ReadPage(record=record, cleaned=content, raw_html=result.html)

    async def _extract_and_validate(
        self, run: ResearchRun, company_name: str, website: str, pages: list[ReadPage]
    ) -> ResearchFailureCode | None:
        """Extraction sees a frozen page set and cannot cause new fetches.

        A provider failure is recorded, never retried behind the Fake
        extractor (ADR-0027): the run keeps the pages it read, names the
        extractor that failed, and ends PARTIAL with `extraction_failed`.
        """
        try:
            result = await self.extractor.extract(
                ExtractionInput(
                    company_name=company_name,
                    website=website,
                    pages=tuple((page.record.url, page.cleaned.text) for page in pages),
                    output_language=run.output_language,
                )
            )
        except ExtractionError as exc:
            run.record_extraction(
                profile=ResearchProfile(), extractor=self.extractor.identity, proposed_count=0
            )
            run.add_warning(f"extraction failed ({exc.code.value})")
            return ResearchFailureCode.EXTRACTION_FAILED
        run.record_extraction(
            profile=result.profile,
            extractor=self.extractor.identity,
            proposed_count=len(result.claims),
            unknown_dimensions=result.unknown_dimensions,
        )

        outcome = self.validator.validate(
            result.claims,
            tuple(
                PageContent(page=page.record, cleaned_text=page.cleaned.text) for page in pages
            ),
        )
        for claim in outcome.accepted:
            run.record_claim(claim)
        for rejection in outcome.rejected:
            run.record_rejection(rejection)
        return None

    def _failure_code(
        self, pages: list[ReadPage], budget_exhausted: bool, run: ResearchRun
    ) -> ResearchFailureCode | None:
        if pages and all(page.cleaned.is_thin(self.limits.thin_page_chars) for page in pages):
            run.add_warning("pages yielded almost no text — the site likely requires a browser")
            return ResearchFailureCode.NEEDS_BROWSER
        if budget_exhausted:
            return ResearchFailureCode.BUDGET_EXCEEDED
        return None

    async def _persist(self, run: ResearchRun) -> ResearchOutcome:
        async with self.uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        return ResearchOutcome(
            action=_action_for(run.status),
            company_id=run.company_id,
            research_id=run.id,
            status=run.status,
            failure_code=run.failure_code,
            pages_fetched=run.pages_fetched,
            pages_failed=run.pages_failed,
            claims_extracted=run.claims_extracted,
            claims_validated=run.claims_validated,
            unknown_dimensions=run.unknown_dimensions,
            warnings=run.warnings,
        )


def _action_for(status: ResearchRunStatus) -> ResearchAction:
    if status is ResearchRunStatus.COMPLETED:
        return ResearchAction.COMPLETED
    if status is ResearchRunStatus.PARTIAL:
        return ResearchAction.PARTIAL
    return ResearchAction.FAILED
