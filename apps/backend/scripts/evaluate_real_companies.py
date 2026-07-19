"""Phase 6: run the real research pipeline over a fixed set of real US importers.

Runs the production path end to end — SafeFetcher → cleaner → page_ranker →
OpenAIResearchExtractor → ClaimValidator → ResearchRun persistence — one
company at a time, never concurrently, at most one LLM request each.

It exists as a script rather than a test because it costs money and touches
the public internet. It creates no Company, Opportunity, score or draft; the
only rows it writes are research_* audit records.

Output is a JSON report next to this file's --out path. Page bodies are never
written to it: only the short evidence snippets a reviewer must check.

Stop conditions (abort immediately, stop spending):
  - two consecutive companies with a fabricated fact
  - any accepted claim whose snippet cannot be located in the cited page
  - any accepted claim citing a URL this run did not fetch
  - running average total tokens materially above budget
  - two consecutive provider failures
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.database.session import create_engine, create_session_factory  # noqa: E402
from app.database.uow import SqlAlchemyUnitOfWork  # noqa: E402
from app.domain.research import ExtractionResult  # noqa: E402
from app.services.research import (  # noqa: E402
    ExtractionInput,
    OpenAIResearchExtractor,
)
from app.tools.website import FetchLimits, SafeFetcher, SiteScope  # noqa: E402
from app.workflows.research import (  # noqa: E402
    ResearchLimits,
    ResearchRequest,
    ResearchWorkflow,
)

TOKEN_BUDGET = 8_000
TOKEN_ABORT_MULTIPLIER = 1.5


@dataclass(frozen=True)
class Target:
    company: str
    category: str
    website: str


#: Fixed evaluation set: ten real US importers/distributors, two per category.
#: Chosen from public websites only. Harbor Freight (HTTP 403) and Satco
#: (HTTP 429) were probed and excluded because they refuse automated access —
#: the fetcher honours that refusal by design, so they would measure their bot
#: wall rather than our extractor.
TARGETS: tuple[Target, ...] = (
    Target("Klein Tools", "hardware_tools", "https://www.kleintools.com"),
    Target("Great Neck Saw Manufacturers", "hardware_tools", "https://www.greatnecksaw.com"),
    Target("Sauder Woodworking", "furniture_home", "https://www.sauder.com"),
    Target("Ashley Furniture Industries", "furniture_home", "https://www.ashleyfurniture.com"),
    Target("Body-Solid", "fitness_equipment", "https://www.bodysolid.com"),
    Target("Life Fitness", "fitness_equipment", "https://www.lifefitness.com"),
    Target("Global Industrial", "industrial_equipment", "https://www.globalindustrial.com"),
    Target("W.W. Grainger", "industrial_equipment", "https://www.grainger.com"),
    Target("Feit Electric", "lighting_electrical", "https://www.feit.com"),
    Target("Westinghouse Lighting", "lighting_electrical", "https://www.westinghouselighting.com"),
)


@dataclass
class ClaimRecord:
    kind: str
    detail: str
    evidence_snippet: str
    source_url: str
    confidence: float
    snippet_located: bool
    source_fetched: bool


@dataclass
class CompanyRecord:
    company: str
    category: str
    website: str
    status: str = "not_run"
    failure_code: str | None = None
    error: str | None = None
    research_id: str | None = None
    pages_fetched: int = 0
    pages_failed: int = 0
    claims_proposed: int = 0
    claims_validated: int = 0
    unknown_dimensions: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    latency_seconds: float = 0.0
    llm_calls: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    claims: list[ClaimRecord] = field(default_factory=list)


class CountingExtractor:
    """Wraps the real extractor to count calls and capture usage per company.

    Counting matters: "at most one LLM request per company" is an acceptance
    gate, so it is measured rather than assumed.
    """

    def __init__(self, inner: OpenAIResearchExtractor) -> None:
        self._inner = inner
        self.calls = 0
        self.pages_seen: dict[str, str] = {}

    @property
    def identity(self) -> Any:
        return self._inner.identity

    @property
    def last_usage(self) -> Any:
        return self._inner.last_usage

    async def extract(self, payload: ExtractionInput) -> ExtractionResult:
        self.calls += 1
        # Kept so evidence can be re-verified independently of the validator.
        self.pages_seen = {url: text for url, text in payload.pages}
        return await self._inner.extract(payload)


def build_workflow(settings: Settings, extractor: CountingExtractor) -> ResearchWorkflow:
    """Same wiring as app.api.deps.get_research_workflow."""
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(factory)

    def fetcher_factory(scope: SiteScope) -> SafeFetcher:
        return SafeFetcher(
            limits=FetchLimits(
                max_page_bytes=settings.research_max_page_bytes,
                max_decompressed_bytes=settings.research_max_decompressed_bytes,
                request_timeout_seconds=settings.research_request_timeout_seconds,
                max_redirects=settings.research_max_redirects,
                user_agent=settings.research_user_agent,
            ),
            scope=scope,
        )

    workflow = ResearchWorkflow(
        uow_factory=uow_factory,
        extractor=extractor,
        fetcher_factory=fetcher_factory,
        limits=ResearchLimits(
            max_pages=settings.research_max_pages,
            max_page_chars=settings.research_max_page_chars,
            total_budget_seconds=settings.research_total_budget_seconds,
            request_delay_seconds=settings.research_request_delay_seconds,
            user_agent=settings.research_user_agent,
        ),
    )
    workflow._engine = engine  # type: ignore[attr-defined]
    return workflow


async def business_row_counts(settings: Settings) -> dict[str, int]:
    """Company-side tables must be untouched by research (ADR-0025)."""
    engine = create_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            counts = {}
            for table in ("companies", "opportunities", "contacts", "outreaches", "email_drafts"):
                result = await connection.execute(text(f"SELECT count(*) FROM {table}"))
                counts[table] = int(result.scalar_one())
            return counts
    finally:
        await engine.dispose()


async def run_one(settings: Settings, target: Target) -> CompanyRecord:
    record = CompanyRecord(company=target.company, category=target.category, website=target.website)
    extractor = CountingExtractor(
        OpenAIResearchExtractor(
            model=settings.resolved_research_model,
            api_key=settings.openai_api_key or None,
            base_url=settings.openai_base_url or None,
            prompt_version=settings.research_prompt_version,
            timeout_seconds=settings.research_extractor_timeout_seconds,
            max_input_chars=settings.research_extractor_max_input_chars,
        )
    )
    workflow = build_workflow(settings, extractor)
    engine = workflow._engine  # type: ignore[attr-defined]

    started = time.monotonic()
    try:
        outcome = await workflow.handle(
            ResearchRequest(company_name=target.company, website=target.website)
        )
    except Exception as exc:  # noqa: BLE001 — a crash is a result worth recording
        record.status = "crashed"
        record.error = f"{type(exc).__name__}: {exc}"
        record.latency_seconds = round(time.monotonic() - started, 2)
        record.llm_calls = extractor.calls
        await engine.dispose()
        return record

    record.latency_seconds = round(time.monotonic() - started, 2)
    record.status = outcome.status.value if outcome.status else outcome.action.value
    record.failure_code = outcome.failure_code.value if outcome.failure_code else None
    record.research_id = str(outcome.research_id) if outcome.research_id else None
    record.pages_fetched = outcome.pages_fetched
    record.pages_failed = outcome.pages_failed
    record.claims_proposed = outcome.claims_extracted
    record.claims_validated = outcome.claims_validated
    record.unknown_dimensions = list(outcome.unknown_dimensions)
    record.rejections = [w for w in outcome.warnings if "claim rejected" in w]
    record.llm_calls = extractor.calls

    usage = extractor.last_usage
    if usage is not None:
        record.prompt_tokens = usage.prompt_tokens
        record.completion_tokens = usage.completion_tokens
        record.total_tokens = usage.total_tokens

    # Re-verify every accepted claim independently of ClaimValidator, against
    # the page text the extractor was actually shown.
    if outcome.research_id is not None:
        factory = create_session_factory(engine)
        async with SqlAlchemyUnitOfWork(factory) as uow:
            saved = await uow.research_runs.get_by_id(outcome.research_id)
        if saved is not None:
            by_position = {page.position: page for page in saved.pages}
            for claim in saved.claims:
                page = by_position.get(claim.source_page_position)
                page_text = extractor.pages_seen.get(page.url, "") if page else ""
                record.claims.append(
                    ClaimRecord(
                        kind=claim.kind,
                        detail=claim.detail,
                        evidence_snippet=claim.evidence_snippet,
                        source_url=page.url if page else "<missing>",
                        confidence=claim.confidence,
                        snippet_located=claim.evidence_snippet.strip() in page_text,
                        source_fetched=page is not None,
                    )
                )

    await engine.dispose()
    return record


def check_stop_conditions(records: list[CompanyRecord]) -> str | None:
    for record in records:
        for claim in record.claims:
            if not claim.snippet_located:
                return f"{record.company}: accepted claim snippet not located in cited page"
            if not claim.source_fetched:
                return f"{record.company}: accepted claim cites an unfetched page"

    failures = [r for r in records if r.status in ("crashed",) or r.error]
    if len(failures) >= 2 and failures[-1] is records[-1] and failures[-2] is records[-2]:
        return "two consecutive provider/pipeline failures"

    measured = [r.total_tokens for r in records if r.total_tokens]
    if measured:
        average = sum(measured) / len(measured)
        if average > TOKEN_BUDGET * TOKEN_ABORT_MULTIPLIER:
            return f"average total tokens {average:.0f} far above the {TOKEN_BUDGET} budget"
    return None


def write_report(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="scripts/out/real-company-evaluation.json")
    parser.add_argument("--limit", type=int, default=len(TARGETS))
    args = parser.parse_args()

    settings = Settings()
    if settings.research_extractor_provider != "openai":
        print("RESEARCH_EXTRACTOR_PROVIDER must be openai for this evaluation.")
        raise SystemExit(1)
    if not (settings.openai_api_key or "").strip():
        print("OPENAI_API_KEY is not configured.")
        raise SystemExit(1)

    before = await business_row_counts(settings)
    print(f"model={settings.resolved_research_model} prompt={settings.research_prompt_version}")
    print(f"business rows before: {before}\n")

    records: list[CompanyRecord] = []
    stopped: str | None = None
    for index, target in enumerate(TARGETS[: args.limit], start=1):
        print(f"[{index}/{args.limit}] {target.company} ({target.category})")
        record = await run_one(settings, target)
        records.append(record)
        print(
            f"    status={record.status} failure={record.failure_code} "
            f"pages={record.pages_fetched}/{record.pages_fetched + record.pages_failed} "
            f"claims={record.claims_validated}/{record.claims_proposed} "
            f"unknown={len(record.unknown_dimensions)} "
            f"llm_calls={record.llm_calls} tokens={record.total_tokens} "
            f"{record.latency_seconds}s"
        )
        if record.error:
            print(f"    error: {record.error}")

        stopped = check_stop_conditions(records)
        if stopped:
            print(f"\n⛔ STOP CONDITION: {stopped}")
            break

    after = await business_row_counts(settings)
    print(f"\nbusiness rows after: {after}")
    side_effects = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    if side_effects:
        print(f"⛔ SIDE EFFECTS DETECTED: {side_effects}")

    report = json.dumps(
        {
            "model": settings.resolved_research_model,
            "prompt_version": settings.research_prompt_version,
            "stopped": stopped,
            "business_rows_before": before,
            "business_rows_after": after,
            "side_effects": side_effects,
            "companies": [asdict(record) for record in records],
        },
        ensure_ascii=False,
        indent=2,
    )
    write_report(Path(args.out), report)
    print(f"report written to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
