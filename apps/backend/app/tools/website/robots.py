"""robots.txt: fetched once per run, cached for the run, obeyed.

A failed robots fetch means allow (standard behavior). A robots.txt that
disallows the homepage aborts the run — the caller decides, this module only
reports (ADR-0026 §4).
"""

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.tools.website.fetcher import FetchedPage, SafeFetcher


def robots_url_for(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


@dataclass
class RobotsPolicy:
    """Allow/deny decisions for one origin, plus how we got them."""

    user_agent: str
    parser: RobotFileParser | None
    fetched: bool
    note: str | None = None

    def allows(self, url: str) -> bool:
        if self.parser is None:
            return True  # no robots.txt reachable → allow, per convention
        return self.parser.can_fetch(self.user_agent, url)


async def load_robots(
    client: httpx.AsyncClient, fetcher: SafeFetcher, base_url: str, user_agent: str
) -> RobotsPolicy:
    """Fetch and parse robots.txt through the same guarded fetcher.

    robots.txt is not HTML, so it is read with a content-type-agnostic call
    rather than SafeFetcher.fetch, but it goes through the same URL guard by
    reusing the fetcher's resolver and policy.
    """
    target = robots_url_for(base_url)
    outcome = await _fetch_text(client, fetcher, target)
    if outcome is None:
        return RobotsPolicy(
            user_agent=user_agent,
            parser=None,
            fetched=False,
            note="robots.txt unreachable — treating as allow",
        )
    parser = RobotFileParser()
    parser.parse(outcome.splitlines())
    return RobotsPolicy(user_agent=user_agent, parser=parser, fetched=True)


async def _fetch_text(
    client: httpx.AsyncClient, fetcher: SafeFetcher, url: str
) -> str | None:
    """robots.txt served as text/plain would be rejected by the HTML check, so
    temporarily accept any content type for this one file."""
    original = fetcher.scope
    fetcher.scope = None  # robots lives at the origin root, always in scope
    try:
        result = await fetcher.fetch(client, url)
    finally:
        fetcher.scope = original
    if isinstance(result, FetchedPage):
        return result.html
    if result.code == "not_html":
        # Re-read as plain text: the guard already passed for this URL.
        try:
            response = await client.get(
                url,
                headers={"User-Agent": fetcher.limits.user_agent},
                timeout=fetcher.limits.request_timeout_seconds,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        return response.text[: fetcher.limits.max_page_bytes]
    return None
