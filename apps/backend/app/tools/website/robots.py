"""robots.txt: fetched once per run, cached for the run, obeyed.

A failed robots fetch means allow (standard behavior). A robots.txt that
disallows the homepage aborts the run — the caller decides, this module only
reports (ADR-0026 §4).

**Two different agent strings.** `RobotFileParser.can_fetch` matches on the
token before "/" in whatever you hand it, so passing the full HTTP User-Agent
(`USImporterHunterBot/0.2`) makes a robots.txt line naming
`USImporterHunterBot/0.2` *fail* to apply — it is longer than the token being
matched, and the `*` group silently wins instead. We therefore match robots
rules with the bare product token and keep the versioned string for the HTTP
header only.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.tools.website.fetcher import FetchedPage, SafeFetcher

#: Product token used for robots matching — never the versioned HTTP UA.
ROBOTS_TOKEN = "USImporterHunterBot"


def robots_token_from_user_agent(user_agent: str) -> str:
    """`USImporterHunterBot/0.2 (+url)` → `USImporterHunterBot`."""
    return user_agent.split("/", 1)[0].strip() or ROBOTS_TOKEN


def normalize_robots_text(text: str) -> str:
    """Strip version suffixes from `User-agent:` lines before parsing.

    RFC 9309 says a robots product token carries no version, and
    `RobotFileParser` matches by testing whether the robots agent is a
    *substring* of ours. So a site that writes `User-agent: OurBot/0.2`
    (a common mistake) would match nothing and silently fall through to the
    `*` group — which may be more permissive than what the site intended for
    us specifically.

    Normalizing `OurBot/0.2` to `OurBot` makes that line apply. This can only
    ever make us obey *more* rules, never fewer: an unrelated agent still fails
    the substring test after normalization.
    """
    lines: list[str] = []
    for line in text.splitlines():
        head, sep, value = line.partition(":")
        if sep and head.strip().lower() == "user-agent":
            agent = value.strip()
            if agent != "*" and "/" in agent:
                agent = agent.split("/", 1)[0].strip()
            lines.append(f"{head}:{' ' if value.startswith(' ') else ''}{agent}")
        else:
            lines.append(line)
    return "\n".join(lines)


def robots_url_for(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


@dataclass
class RobotsPolicy:
    """Allow/deny decisions for one origin, plus how we got them.

    `robots_token` is the bare product token, not the HTTP User-Agent.
    """

    robots_token: str
    parser: RobotFileParser | None
    fetched: bool
    note: str | None = None

    def allows(self, url: str) -> bool:
        if self.parser is None:
            return True  # no robots.txt reachable → allow, per convention
        return self.parser.can_fetch(self.robots_token, url)


async def load_robots(
    client: httpx.AsyncClient, fetcher: SafeFetcher, base_url: str, user_agent: str
) -> RobotsPolicy:
    """Fetch and parse robots.txt through the same guarded fetcher.

    robots.txt is not HTML, so it is read with a content-type-agnostic call
    rather than SafeFetcher.fetch, but it goes through the same URL guard by
    reusing the fetcher's resolver and policy.
    """
    token = robots_token_from_user_agent(user_agent)
    target = robots_url_for(base_url)
    outcome = await _fetch_text(client, fetcher, target)
    if outcome is None:
        return RobotsPolicy(
            robots_token=token,
            parser=None,
            fetched=False,
            note="robots.txt unreachable — treating as allow",
        )
    parser = RobotFileParser()
    parser.parse(normalize_robots_text(outcome).splitlines())
    return RobotsPolicy(robots_token=token, parser=parser, fetched=True)


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
