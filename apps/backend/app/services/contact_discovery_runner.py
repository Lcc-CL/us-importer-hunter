"""Re-read a ResearchRun's fixed page set and discover public contacts."""

from dataclasses import dataclass

from app.domain.research import ResearchRun
from app.services.contact_discovery import ContactSelection, extract_contacts, rank_contacts
from app.tools.website import (
    FetchedPage,
    FetchLimits,
    SafeFetcher,
    SiteScope,
    clean_html,
    create_research_client,
)


@dataclass(frozen=True)
class ContactDiscoveryRunOutcome:
    selection: ContactSelection
    pages_scanned: int
    pages_failed: int


@dataclass(frozen=True)
class WebsiteContactDiscoveryService:
    fetch_limits: FetchLimits
    max_pages: int
    max_page_chars: int

    async def discover(self, run: ResearchRun) -> ContactDiscoveryRunOutcome:
        fetcher = SafeFetcher(
            limits=self.fetch_limits,
            scope=SiteScope.from_url(run.website),
        )
        pages: list[tuple[str, str, str]] = []
        failed = 0
        async with create_research_client(
            timeout=self.fetch_limits.request_timeout_seconds
        ) as client:
            for page in run.pages[: self.max_pages]:
                outcome = await fetcher.fetch(client, page.url)
                if isinstance(outcome, FetchedPage):
                    cleaned = clean_html(outcome.html, max_chars=self.max_page_chars)
                    pages.append((page.url, outcome.html, cleaned.text))
                else:
                    failed += 1
        return ContactDiscoveryRunOutcome(
            selection=rank_contacts(extract_contacts(pages)),
            pages_scanned=len(pages),
            pages_failed=failed,
        )
