"""Deterministic page discovery (ADR-0025 §6, design §4).

This is the load-bearing part of the prompt-injection defence: because page
selection is decided here — by path and anchor keywords, with no model in the
loop — page content cannot steer the crawler at new targets. The fetch set is
frozen before any LLM sees anything.
"""

import re
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlsplit

from app.tools.website.site_scope import SiteScope

NON_HTML_SUFFIXES = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".rar", ".gz", ".mp4", ".mp3", ".avi", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx", ".css", ".js", ".json", ".xml",
)

# (category, weight, patterns) — first matching category wins for a URL.
CATEGORY_RULES: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("about", 10, ("about", "company", "who-we-are", "our-story", "关于", "公司简介")),
    ("products", 8, ("product", "service", "solution", "catalog", "brand", "产品", "服务")),
    ("capabilities", 6, ("capabilit", "facilit", "warehouse", "manufactur", "quality",
                         "distribution", "logistics", "supply", "仓储", "物流")),
    ("contact", 4, ("contact", "location", "office", "联系", "地址")),
    ("news", 2, ("news", "press", "blog", "article", "新闻", "资讯")),
)

PENALTY_PATTERNS = (
    "cart", "checkout", "login", "signin", "sign-in", "register", "account",
    "privacy", "terms", "legal", "cookie", "careers", "jobs", "search",
    "wishlist", "compare", "add-to-cart", "sitemap", "feed", "rss",
)

_TRACKING_PARAMS = re.compile(r"^(utm_|gclid|fbclid|mc_|ref$)", re.IGNORECASE)


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    anchor_text: str = ""


@dataclass(frozen=True)
class RankedPage:
    url: str
    score: int
    category: str

    @property
    def discovery_reason(self) -> str:
        return f"ranked:{self.category}"


def normalize_link(base_url: str, href: str) -> str | None:
    """Absolute, fragment-free, tracking-free URL — or None if unusable."""
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    absolute, _ = urldefrag(urljoin(base_url, href))
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https"):
        return None
    if parts.query:
        kept = [
            pair
            for pair in parts.query.split("&")
            if pair and not _TRACKING_PARAMS.match(pair.split("=")[0])
        ]
        absolute = absolute.split("?")[0] + (("?" + "&".join(kept)) if kept else "")
    return absolute.rstrip("/") or absolute


def score_url(url: str, anchor_text: str = "") -> tuple[int, str]:
    """Score one candidate. Returns (score, category); score <= 0 means skip."""
    parts = urlsplit(url)
    path = parts.path.lower()
    haystack = f"{path} {anchor_text.lower()}"

    if any(path.endswith(suffix) for suffix in NON_HTML_SUFFIXES):
        return (-20, "asset")
    if any(pattern in haystack for pattern in PENALTY_PATTERNS):
        return (-20, "penalized")

    for category, weight, patterns in CATEGORY_RULES:
        if any(pattern in haystack for pattern in patterns):
            depth = len([segment for segment in path.split("/") if segment])
            return (weight - min(depth - 1, 3), category)
    return (0, "other")


def rank_pages(
    *,
    base_url: str,
    links: list[LinkCandidate],
    scope: SiteScope,
    limit: int,
    already_seen: frozenset[str] = frozenset(),
) -> list[RankedPage]:
    """Pick at most `limit` pages, best first, one per category where possible.

    Category spreading stops four product pages from consuming every slot; a
    second pass fills any remaining slots with the next best candidates.
    """
    seen: set[str] = set(already_seen)
    scored: list[RankedPage] = []

    for link in links:
        url = normalize_link(base_url, link.url)
        if url is None or url in seen or not scope.allows(url):
            continue
        seen.add(url)
        score, category = score_url(url, link.anchor_text)
        if score <= 0:
            continue
        scored.append(RankedPage(url=url, score=score, category=category))

    # Best score first; ties break on the shorter path (/about beats
    # /about/history/1998), then alphabetically for full determinism.
    scored.sort(key=lambda page: (-page.score, len(urlsplit(page.url).path), page.url))

    chosen: list[RankedPage] = []
    used_categories: set[str] = set()
    for page in scored:
        if len(chosen) >= limit:
            break
        if page.category in used_categories:
            continue
        chosen.append(page)
        used_categories.add(page.category)

    if len(chosen) < limit:
        chosen_urls = {page.url for page in chosen}
        for page in scored:
            if len(chosen) >= limit:
                break
            if page.url not in chosen_urls:
                chosen.append(page)
                chosen_urls.add(page.url)

    return chosen


def extract_links(html: str) -> list[LinkCandidate]:
    """Anchors with their text. Parsing lives here so callers stay HTML-free."""
    from selectolax.parser import HTMLParser

    candidates: list[LinkCandidate] = []
    for node in HTMLParser(html).css("a[href]"):
        href = node.attributes.get("href")
        if href:
            candidates.append(
                LinkCandidate(url=href, anchor_text=(node.text(deep=True) or "").strip()[:120])
            )
    return candidates
