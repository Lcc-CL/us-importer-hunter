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
)
from app.tools.website.page_ranker import (
    LinkCandidate,
    RankedPage,
    extract_links,
    normalize_link,
    rank_pages,
    score_url,
)
from app.tools.website.robots import RobotsPolicy, load_robots, robots_url_for
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
    "extract_links",
    "is_public_ip",
    "load_robots",
    "normalize_link",
    "rank_pages",
    "robots_url_for",
    "score_url",
    "validate_url",
]
