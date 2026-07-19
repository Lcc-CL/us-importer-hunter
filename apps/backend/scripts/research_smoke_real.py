"""One real LLM extraction against fixed, controlled page text.

Deliberately NOT a pytest test: `uv run pytest` must never spend money or
need a network. Run it explicitly:

    make research-smoke-real

What it proves, and nothing more:

- the configured provider/model/base URL actually answer;
- the model's claims survive the real ClaimValidator, with every evidence
  snippet locatable in the controlled text;
- provider / model / prompt_version persist on a ResearchRun row.

What it must never do: fetch a live website (the page text is a fixture, so
the check is reproducible and no third party is crawled), or create/modify a
Company, Opportunity, score, or email draft. The ResearchRun it writes is
deleted before the script exits.
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.database.session import create_engine, create_session_factory  # noqa: E402
from app.database.uow import SqlAlchemyUnitOfWork  # noqa: E402
from app.domain.clock import utcnow  # noqa: E402
from app.domain.research import ResearchPage, ResearchRun  # noqa: E402
from app.services.research import (  # noqa: E402
    ClaimValidator,
    ExtractionError,
    ExtractionInput,
    OpenAIResearchExtractor,
    PageContent,
)

HOME_URL = "https://smoke-fixture.example/"
ABOUT_URL = "https://smoke-fixture.example/about"

#: Fixed fixture text. Rich enough that a working model finds several
#: dimensions, and every fact is quotable — so a claim that cannot be located
#: in this text is the model inventing, not the fixture being thin.
HOME_TEXT = (
    "Harborline Industrial Supply is a US importer and distributor of "
    "industrial fasteners, hand tools and workshop consumables. "
    "We import containers of hardware from Shenzhen and Ningbo every month, "
    "and our ocean freight arrives as full container loads at the Port of "
    "Long Beach. "
    "Our team operates a 95,000 square foot distribution center in Compton, "
    "California, staffed by 140 employees. "
    "Import volume has grown by double digits for three consecutive years as "
    "we added suppliers in Vietnam and Malaysia."
)

ABOUT_TEXT = (
    "Founded in 2009, Harborline serves contractors and industrial resellers "
    "across the western United States. "
    "Coordinating shipments from four origin countries into two US warehouses "
    "has made customs clearance and inland trucking our biggest operational "
    "headache, and delays at origin regularly push out our lead times. "
    "We carry high value precision tooling that must be tracked carefully "
    "through the supply chain."
)

PAGES = ((HOME_URL, HOME_TEXT), (ABOUT_URL, ABOUT_TEXT))
MIN_VALID_CLAIMS = 2


def fail(message: str) -> None:
    print(f"\n❌ Real Research Smoke Test: FAIL\n   {message}")
    raise SystemExit(1)


def preflight(settings: Settings) -> str:
    """Confirm a credential and model exist. The key is never printed."""
    key = (settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        fail("OPENAI_API_KEY is not set. Put a real key in the root .env, then re-run.")
    model = settings.resolved_research_model
    if not model:
        fail("No model configured. Set RESEARCH_MODEL or OPENAI_MODEL.")

    print("Pre-flight")
    print(f"  credential      : present ({len(key)} chars, never printed)")
    print(f"  model           : {model}")
    print(f"  base url        : {settings.openai_base_url or 'provider default'}")
    print(f"  prompt version  : {settings.research_prompt_version}")
    return model


def run_pages() -> tuple[PageContent, ...]:
    now = utcnow()
    return tuple(
        PageContent(
            page=ResearchPage(
                position=index,
                url=url,
                final_url=url,
                http_status=200,
                content_type="text/html",
                fetched_at=now,
                content_chars=len(text),
                discovery_reason="smoke-fixture",
            ),
            cleaned_text=text,
        )
        for index, (url, text) in enumerate(PAGES)
    )


async def persist(settings: Settings, run: ResearchRun) -> UUID:
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        async with SqlAlchemyUnitOfWork(factory) as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        async with SqlAlchemyUnitOfWork(factory) as uow:
            saved = await uow.research_runs.get_by_id(run.id)
            if saved is None or saved.extractor is None:
                fail("the research run did not persist its extractor identity")
            assert saved is not None and saved.extractor is not None
            print("\nPersistence")
            print(f"  research_id     : {saved.id}")
            print(f"  provider        : {saved.extractor.provider}")
            print(f"  model           : {saved.extractor.model}")
            print(f"  prompt_version  : {saved.extractor.prompt_version}")
            print(f"  claims stored   : {len(saved.claims)}")
            print(f"  company_id      : {saved.company_id} (no Company was created)")
        return run.id
    finally:
        await engine.dispose()


async def cleanup(settings: Settings, research_id: UUID) -> None:
    """Delete the smoke run.

    Raw SQL on purpose: the domain repository has no `delete`, and adding one
    to the production contract just so a smoke script can tidy up would be the
    wrong trade. Child rows (pages, claims, promotions) go with it through
    their ON DELETE CASCADE foreign keys.
    """
    engine = create_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM research_runs WHERE id = :id"), {"id": str(research_id)}
            )
        factory = create_session_factory(engine)
        async with SqlAlchemyUnitOfWork(factory) as uow:
            if await uow.research_runs.get_by_id(research_id) is not None:
                fail(f"cleanup failed — research run {research_id} still exists")
        print(f"  cleanup         : research run {research_id} deleted")
    finally:
        await engine.dispose()


async def main() -> None:
    settings = Settings()
    model = preflight(settings)

    extractor = OpenAIResearchExtractor(
        model=model,
        api_key=settings.openai_api_key or None,
        base_url=settings.openai_base_url or None,
        prompt_version=settings.research_prompt_version,
        timeout_seconds=settings.research_extractor_timeout_seconds,
        max_input_chars=settings.research_extractor_max_input_chars,
    )

    print("\nCalling the provider once…")
    try:
        result = await extractor.extract(
            ExtractionInput(
                company_name="Harborline Industrial Supply",
                website=HOME_URL,
                pages=PAGES,
            )
        )
    except ExtractionError as exc:
        fail(f"extraction failed ({exc.code.value}): {exc}")
        return

    usage = extractor.last_usage
    print("\nProvider call")
    print(f"  latency         : {usage.latency_seconds if usage else '?'}s")
    if usage and usage.total_tokens is not None:
        print(
            f"  tokens          : {usage.prompt_tokens} in / "
            f"{usage.completion_tokens} out / {usage.total_tokens} total"
        )
    else:
        print("  tokens          : not reported by this provider")
    print(f"  claims proposed : {len(result.claims)}")
    print(f"  unknown dims    : {', '.join(result.unknown_dimensions) or 'none'}")

    pages = run_pages()
    outcome = ClaimValidator().validate(result.claims, pages)

    print("\nValidation (real ClaimValidator, unmodified)")
    print(f"  accepted        : {len(outcome.accepted)}")
    print(f"  rejected        : {len(outcome.rejected)}")
    for rejection in outcome.rejected:
        print(f"    - {rejection.reason.value}: {rejection.kind}")

    text_by_position = {content.page.position: content.cleaned_text for content in pages}
    for claim in outcome.accepted:
        source = text_by_position[claim.source_page_position]
        located = claim.evidence_snippet.strip() in source
        mark = "✓" if located else "✗"
        print(f"    {mark} {claim.kind} (confidence {claim.confidence})")
        if not located:
            fail(f"accepted claim {claim.kind!r} could not be located in its source page")

    if len(outcome.accepted) < MIN_VALID_CLAIMS:
        fail(
            f"only {len(outcome.accepted)} claim(s) passed validation; "
            f"the gate requires at least {MIN_VALID_CLAIMS}"
        )

    run = ResearchRun.start("Harborline Industrial Supply", HOME_URL, company_id=None)
    run.mark_running()
    for content in pages:
        run.record_page(content.page)
    run.record_extraction(
        profile=result.profile, extractor=extractor.identity, proposed_count=len(result.claims)
    )
    for claim in outcome.accepted:
        run.record_claim(claim)
    for rejection in outcome.rejected:
        run.record_rejection(rejection)
    run.complete(partial=False, failure_code=None)

    research_id = await persist(settings, run)
    await cleanup(settings, research_id)

    print("\n✅ Real Research Smoke Test: PASS")
    print(
        f"   {len(outcome.accepted)} validated claims, "
        f"100% of evidence snippets located in the fixture text."
    )


if __name__ == "__main__":
    asyncio.run(main())
