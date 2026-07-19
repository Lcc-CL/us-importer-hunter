"""HTML → text, for extraction and for evidence-snippet verification.

Block-level boundaries become newlines so sentences stay intact: the snippet
check in phase 2 asserts that a quoted sentence appears verbatim in this text,
which fails if inline elements silently concatenate neighbouring words.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from selectolax.parser import HTMLParser

DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "form",
    "nav",
    "header",
    "footer",
    "template",
)

BOILERPLATE_HINTS = (
    "cookie",
    "banner",
    "menu",
    "breadcrumb",
    "sidebar",
    "navbar",
    "footer",
    "subscribe",
    "newsletter",
)

BLOCK_TAGS = frozenset(
    {
        "p", "div", "section", "article", "li", "tr", "br", "h1", "h2",
        "h3", "h4", "h5", "h6", "td", "th", "blockquote", "pre", "figcaption",
    }
)

# Patterns that suggest the page is talking to our model rather than describing
# a company. Detection only — the structural defences in ADR-0025 §6 are what
# actually contain injection.
INJECTION_HINTS = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard the above",
    "disregard previous",
    "system prompt",
    "you are now",
    "act as",
    "api key",
    "reveal your",
    "print your instructions",
)

_WHITESPACE = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")

# Short lines that are site furniture rather than statements about the company.
# Matched only against SHORT lines: a paragraph that merely mentions "cookie"
# or "privacy" is content, while a standalone "Cookie Settings" is chrome.
_CHROME_LINE_MAX_CHARS = 120
_CHROME_HINTS = (
    "cookie",
    "privacy policy",
    "privacy choices",
    "terms of use",
    "terms of service",
    "terms and conditions",
    "all rights reserved",
    "do not sell",
    "accept all",
    "reject all",
    "sign up for our newsletter",
    "subscribe to our",
    "skip to content",
    "skip to main",
    "add to cart",
    "view cart",
    "log in",
    "sign in",
    "my account",
)

# Below this, a page is almost certainly a JS shell rather than content.
# Policy, not a constant of nature — callers may pass their own threshold.
THIN_PAGE_CHARS = 200


@dataclass(frozen=True)
class CleanedPage:
    title: str | None
    meta_description: str | None
    text: str
    char_count: int
    truncated: bool
    injection_hits: tuple[str, ...]

    def is_thin(self, min_chars: int = THIN_PAGE_CHARS) -> bool:
        """Too little text to extract from — usually a JS-rendered shell.
        The caller turns this into failure_code `needs_browser`."""
        return self.char_count < min_chars


def clean_html(html: str, *, max_chars: int = 40_000) -> CleanedPage:
    tree = HTMLParser(html)

    title = None
    if tree.head is not None:
        title_node = tree.head.css_first("title")
        if title_node is not None:
            title = _collapse(title_node.text(deep=True)) or None

    meta_description = None
    for node in tree.css("meta"):
        if (node.attributes.get("name") or "").lower() == "description":
            meta_description = _collapse(node.attributes.get("content") or "") or None
            break

    for tag in DROP_TAGS:
        for node in tree.css(tag):
            node.decompose()

    for node in tree.css("[class], [id]"):
        marker = f"{node.attributes.get('class') or ''} {node.attributes.get('id') or ''}".lower()
        if any(hint in marker for hint in BOILERPLATE_HINTS):
            node.decompose()

    body = tree.body if tree.body is not None else tree.root
    text = _extract_text(body) if body is not None else ""
    text = _BLANK_LINES.sub("\n\n", text).strip()

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    lowered = text.lower()
    hits = tuple(hint for hint in INJECTION_HINTS if hint in lowered)

    return CleanedPage(
        title=title,
        meta_description=meta_description,
        text=text,
        char_count=len(text),
        truncated=truncated,
        injection_hits=hits,
    )


def _extract_text(node: object) -> str:
    parts: list[str] = []
    _walk(node, parts)
    lines = [_collapse(line) for line in "".join(parts).split("\n")]
    return "\n".join(_denoise(line for line in lines if len(line) >= 3))


def _denoise(lines: "Iterable[str]") -> list[str]:
    """Drop repeated blocks and site chrome.

    This runs inside the cleaner, not at prompt-build time, on purpose. The
    cleaned text is what ClaimValidator checks evidence snippets against, so
    removing text here keeps the model's view and the validator's view
    identical. Stripping only from the prompt would let a model quote across a
    hole and be rejected for text it faithfully copied.

    Repetition is judged per line so a menu rendered outside <nav> collapses to
    its first occurrence, while genuine prose — which does not repeat verbatim
    — is untouched.
    """
    kept: list[str] = []
    seen: set[str] = set()
    for line in lines:
        marker = line.casefold()
        if marker in seen:
            continue
        if len(line) <= _CHROME_LINE_MAX_CHARS and any(
            hint in marker for hint in _CHROME_HINTS
        ):
            continue
        seen.add(marker)
        kept.append(line)
    return kept


def _walk(node: object, parts: list[str]) -> None:
    for child in getattr(node, "iter", lambda include_text=True: [])(include_text=True):
        tag = getattr(child, "tag", None)
        if tag == "-text":
            parts.append(child.text(deep=False) or "")
            continue
        if tag in BLOCK_TAGS:
            parts.append("\n")
        _walk(child, parts)
        if tag in BLOCK_TAGS:
            parts.append("\n")


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()
