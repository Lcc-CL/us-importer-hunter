"""Job title → a normalized, tokenized form a matcher can reason about.

A pure function with no policy in it: it decides what the words *are*, never
what they mean. Meaning lives in the taxonomy, so the two can be tested and
changed independently.

Two flags matter more than they look. `historical_role` marks "Former
Purchasing Manager" — a real procurement history and the wrong person to email
today. `assistant_role` marks "Assistant Buyer", who buys but does not decide.
Both were silently treated as current decision makers before.
"""

import re
import unicodedata
from dataclasses import dataclass

from app.domain.contact import SeniorityLevel

#: Expanded before matching so "VP, Purch." and "Vice President, Purchasing"
#: reach the taxonomy as the same phrase.
_ABBREVIATIONS: tuple[tuple[str, str], ...] = (
    ("evp", "executive vice president"),
    ("svp", "senior vice president"),
    ("avp", "assistant vice president"),
    ("vp", "vice president"),
    ("sr", "senior"),
    ("jr", "junior"),
    ("mgr", "manager"),
    ("mgmt", "management"),
    ("dir", "director"),
    ("asst", "assistant"),
    ("assoc", "associate"),
    ("ops", "operations"),
    ("purch", "purchasing"),
    ("proc", "procurement"),
    ("procure", "procurement"),
    ("scm", "supply chain management"),
    ("sc", "supply chain"),
    ("gm", "general manager"),
    ("md", "managing director"),
    ("qa", "quality assurance"),
    ("intl", "international"),
    ("natl", "national"),
)

#: Region and scope suffixes carry no responsibility information.
_NOISE_TOKENS = frozenset(
    {
        "na",
        "emea",
        "apac",
        "latam",
        "usa",
        "us",
        "uk",
        "north",
        "south",
        "east",
        "west",
        "americas",
        "region",
        "regional",
        "global",
        "worldwide",
        "corporate",
        "group",
        "inc",
        "llc",
        "ltd",
        "co",
    }
)

_HISTORICAL_MARKERS = ("former", "formerly", "retired", " ex ", "ex-", "previous", "past")
_ASSISTANT_MARKERS = ("assistant", "associate", "deputy", "junior", "trainee", "intern")
_INTERIM_MARKERS = ("interim", "acting", "temporary", "temp")

_SENIORITY_PHRASES: tuple[tuple[SeniorityLevel, tuple[str, ...]], ...] = (
    (
        SeniorityLevel.C_LEVEL,
        (
            " ceo ",
            " coo ",
            " cfo ",
            " cio ",
            " cto ",
            "chief",
            "president",
            "founder",
            "owner",
            "proprietor",
        ),
    ),
    (SeniorityLevel.VP, ("vice president",)),
    (SeniorityLevel.DIRECTOR, ("director",)),
    (SeniorityLevel.HEAD, ("head of", "head,")),
    (SeniorityLevel.MANAGER, ("manager", "supervisor", " lead ")),
    (
        SeniorityLevel.SPECIALIST,
        ("specialist", "coordinator", "analyst", "assistant", "associate", "clerk", "agent"),
    ),
)

_SEPARATORS = re.compile(r"[/,;|\-–—()\[\]]+")
_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")


@dataclass(frozen=True)
class NormalizedTitle:
    """What the words are. What they mean is the matcher's job."""

    original_title: str
    normalized_title: str
    tokens: tuple[str, ...]
    #: Comma/slash-separated segments, so "Sales and Purchasing" keeps both
    #: halves as candidate phrases rather than one blurred string.
    phrases: tuple[str, ...]
    historical_role: bool
    assistant_role: bool
    interim_role: bool
    seniority: SeniorityLevel

    @property
    def padded(self) -> str:
        """Space-padded, so a phrase written with spaces matches whole words."""
        return f" {self.normalized_title} "


def normalize_title(raw: str | None) -> NormalizedTitle:
    """Lowercase, de-accent, expand abbreviations, split, and flag modifiers."""
    original = (raw or "").strip()
    if not original:
        return NormalizedTitle(
            original_title="",
            normalized_title="",
            tokens=(),
            phrases=(),
            historical_role=False,
            assistant_role=False,
            interim_role=False,
            seniority=SeniorityLevel.UNKNOWN,
        )

    folded = unicodedata.normalize("NFKD", original)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.lower().replace("&", " and ")

    # Segment before stripping punctuation: the separators are what tell us
    # "Owner / Buyer" is two responsibilities rather than one job called
    # "owner buyer".
    segments = [segment.strip() for segment in _SEPARATORS.split(folded) if segment.strip()]

    cleaned_segments: list[str] = []
    for segment in segments:
        text = _NON_WORD.sub(" ", segment)
        text = _WHITESPACE.sub(" ", text).strip()
        if text:
            cleaned_segments.append(_expand(text))

    normalized = _WHITESPACE.sub(" ", " ".join(cleaned_segments)).strip()
    padded = f" {normalized} "

    tokens = tuple(token for token in normalized.split(" ") if token)
    meaningful = tuple(token for token in tokens if token not in _NOISE_TOKENS)

    return NormalizedTitle(
        original_title=original,
        normalized_title=normalized,
        tokens=meaningful,
        phrases=tuple(cleaned_segments),
        historical_role=any(marker in padded for marker in _HISTORICAL_MARKERS),
        assistant_role=any(marker in padded for marker in _ASSISTANT_MARKERS),
        interim_role=any(marker in padded for marker in _INTERIM_MARKERS),
        seniority=_seniority(padded),
    )


def _expand(text: str) -> str:
    """Expand abbreviations as whole tokens only.

    Token-wise rather than substring: "sc" inside "scale" is not supply chain,
    and "co" inside "coordinator" is not a company.
    """
    tokens = text.split(" ")
    expanded: list[str] = []
    for token in tokens:
        replacement = next(
            (full for short, full in _ABBREVIATIONS if token == short), None
        )
        expanded.append(replacement if replacement else token)
    return " ".join(expanded)


def _seniority(padded: str) -> SeniorityLevel:
    """First match wins, most senior first — but an assistant is never senior.

    "Assistant Vice President" reads as specialist, not VP: the modifier is the
    load-bearing word, and treating it as VP is how an assistant buyer used to
    rank alongside the buyer.
    """
    if any(marker in padded for marker in _ASSISTANT_MARKERS):
        return SeniorityLevel.SPECIALIST
    for level, phrases in _SENIORITY_PHRASES:
        if any(phrase in padded for phrase in phrases):
            return level
    return SeniorityLevel.UNKNOWN
