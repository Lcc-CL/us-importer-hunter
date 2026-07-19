"""Website research tools (v0.2 phase 1): safe fetching, cleaning, ranking.

No LLM and no persistence here — these are the deterministic primitives the
research workflow will compose in phase 2. Network policy lives in ADR-0026.
"""

from app.tools.website.cleaner import CleanedPage, clean_html
from app.tools.website.fetcher import (
    FetchedPage,
    FetchFailure,
    FetchLimits,
    FetchOutcome,
    SafeFetcher,
    create_research_client,
)
from app.tools.website.page_ranker import (
    LinkCandidate,
    RankedPage,
    extract_links,
    normalize_link,
    rank_pages,
    score_url,
)
from app.tools.website.robots import (
    ROBOTS_TOKEN,
    RobotsPolicy,
    load_robots,
    normalize_robots_text,
    robots_token_from_user_agent,
    robots_url_for,
)
from app.tools.website.site_scope import SiteScope
from app.tools.website.url_guard import (
    HostResolver,
    SystemHostResolver,
    UrlGuardPolicy,
    UrlRejected,
    ValidatedUrl,
    is_public_ip,
    validate_url,
)

__all__ = [
    "ROBOTS_TOKEN",
    "CleanedPage",
    "FetchFailure",
    "FetchLimits",
    "FetchOutcome",
    "FetchedPage",
    "HostResolver",
    "LinkCandidate",
    "RankedPage",
    "RobotsPolicy",
    "SafeFetcher",
    "SiteScope",
    "SystemHostResolver",
    "UrlGuardPolicy",
    "UrlRejected",
    "ValidatedUrl",
    "clean_html",
    "create_research_client",
    "extract_links",
    "is_public_ip",
    "load_robots",
    "normalize_link",
    "normalize_robots_text",
    "rank_pages",
    "robots_token_from_user_agent",
    "robots_url_for",
    "score_url",
    "validate_url",
]
