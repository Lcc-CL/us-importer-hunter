"""Deterministic public-contact extraction from already-researched pages.

Reads only pages a ResearchRun actually fetched — discovery never widens the
crawl. Everything here is rule-based: regex over the page's own bytes, the
existing role taxonomy for ranking. No LLM, no external contact API, and
nothing is invented — every email, phone and name ships with the verbatim
snippet it was read from and the page URL it came from.

MVP boundary: only addresses literally present in a page are usable; nothing
is marked verified, and inferred addresses are not produced at all.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from html import unescape

from app.domain.contact.roles import DecisionRole
from app.services.contact.role_matcher import RoleClassification, classify_title

#: Local parts that address a function, not a person. Order is preference:
#: earlier prefixes make better fallback recipients for logistics outreach.
DEPARTMENT_PREFIXES = (
    "purchasing",
    "procurement",
    "import",
    "imports",
    "logistics",
    "supplychain",
    "operations",
    "sales",
    "info",
    "contact",
    "office",
    "hello",
)

#: Local parts that are useless for outreach and dropped outright.
_IGNORED_PREFIXES = ("noreply", "no-reply", "donotreply", "webmaster", "abuse", "privacy")

_EMAIL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MAILTO_RE = re.compile(r"""mailto:([^"'?\s>]+)""", re.IGNORECASE)
_TEL_RE = re.compile(r"""tel:([+0-9().\-\s]{7,20})""", re.IGNORECASE)
#: "Jane Doe, Director of Purchasing" / "Jane Doe – VP Operations" nearby text.
#: Lowercase connectors (of/and/&) are part of real titles and must not cut
#: the match short.
_NAME_TITLE_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*[,–—\-|:]\s*"
    r"([A-Z][A-Za-z&/.]*(?:\s+(?:of|and|the|&|[A-Z][A-Za-z&/.]*)){0,5})"
)
#: How much page text around a hit is kept as evidence.
_SNIPPET_RADIUS = 120

#: Capitalized phrases that look like "First Last" but are org/nav vocabulary,
#: not people. A false person is worse than a missed one (the anti-fabrication
#: rule), so any hit containing one of these words is dropped.
_NON_NAME_WORDS = frozenset(
    """product products development customer customers service services quality
    team sales support manufacturing engineering operations company tools about
    contact contacts privacy policy terms united states america american new free
    shop home careers press media news catalog warranty resources training safety
    education distributor distributors dealer locator search account order orders
    international global corporate group division department journeyman lineman
    """.split()
)


def _plausible_person_name(name: str) -> bool:
    words = name.split()
    if not 2 <= len(words) <= 3:
        return False
    return not any(word.lower() in _NON_NAME_WORDS for word in words)


def _title_names_a_role(classification: RoleClassification) -> bool:
    """Only a confidently-classified real role makes a name+title pair a person.

    Product listings and "City, ST" patterns match the name regex constantly;
    demanding a known decision role with real confidence is what keeps them out.
    """
    roles = set(classification.roles)
    return (
        classification.confidence >= 0.5
        and bool(roles)
        and DecisionRole.UNKNOWN not in roles
    )


class DiscoverySourceType(StrEnum):
    NAMED = "named"          # a person with a name (title/email may follow)
    DEPARTMENT = "department"  # a functional mailbox such as sales@
    GENERIC = "generic"        # any other real mailbox with no person attached


@dataclass(frozen=True)
class DiscoveredContact:
    """One extraction hit. Every field is either verbatim page content or empty."""

    name: str
    title: str
    email: str
    phone: str
    source_url: str
    source_type: DiscoverySourceType
    evidence_snippet: str
    confidence: float


@dataclass(frozen=True)
class RankedContact:
    contact: DiscoveredContact
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ContactSelection:
    primary: RankedContact | None
    alternatives: tuple[RankedContact, ...]
    supporting: tuple[RankedContact, ...] = ()
    rejected: tuple[RankedContact, ...] = ()
    review_required: bool = False
    selection_reasons: tuple[str, ...] = ()


@dataclass
class _PageText:
    url: str
    html: str
    text: str
    #: text with whitespace collapsed, for snippet search
    flat: str = field(init=False)

    def __post_init__(self) -> None:
        self.flat = re.sub(r"\s+", " ", self.text).strip()


def _snippet(flat: str, needle: str) -> str:
    index = flat.find(needle)
    if index < 0:
        return needle
    start = max(0, index - _SNIPPET_RADIUS)
    end = min(len(flat), index + len(needle) + _SNIPPET_RADIUS)
    return flat[start:end].strip()


def _classify_email(local: str) -> DiscoverySourceType | None:
    lowered = local.lower().replace("-", "").replace("_", "").replace(".", "")
    if any(lowered.startswith(prefix) for prefix in _IGNORED_PREFIXES):
        return None
    if any(lowered == p or lowered.startswith(p) for p in DEPARTMENT_PREFIXES):
        return DiscoverySourceType.DEPARTMENT
    return DiscoverySourceType.GENERIC


def _emails_in(page: _PageText) -> dict[str, str]:
    """address → evidence snippet. mailto: first, then visible text."""
    found: dict[str, str] = {}
    for match in _MAILTO_RE.finditer(page.html):
        address = unescape(match.group(1)).strip().lower()
        if _EMAIL_RE.fullmatch(address) and address not in found:
            found[address] = _snippet(page.flat, address) if address in page.flat else address
    for match in _EMAIL_RE.finditer(page.flat):
        address = match.group(0).lower()
        if address not in found:
            found[address] = _snippet(page.flat, match.group(0))
    return found


def _name_near(flat: str, needle: str) -> tuple[str, str] | None:
    """A '(Name, Title)' pair within snippet range of the needle, else None."""
    index = flat.find(needle)
    if index < 0:
        return None
    window = flat[max(0, index - 200) : index + len(needle) + 200]
    best: tuple[str, str] | None = None
    for match in _NAME_TITLE_RE.finditer(window):
        name, raw_title = match.group(1).strip(), match.group(2).strip(" ,–—-|:")
        if not _plausible_person_name(name):
            continue
        classification = classify_title(raw_title)
        if _title_names_a_role(classification):
            best = (name, raw_title)
    return best


def extract_contacts(pages: list[tuple[str, str, str]]) -> list[DiscoveredContact]:
    """(url, html, cleaned_text) per fetched page → deduplicated contacts.

    Nothing is fabricated: a contact only exists here because its email, phone
    or name/title pair is literally present in one of the given pages.
    """
    contacts: list[DiscoveredContact] = []
    seen: set[tuple[str, str, str]] = set()

    for url, html, text in pages:
        page = _PageText(url=url, html=html, text=text)

        for address, snippet in _emails_in(page).items():
            local = address.split("@", 1)[0]
            kind = _classify_email(local)
            if kind is None:
                continue
            name, title = "", ""
            if kind is DiscoverySourceType.GENERIC:
                pair = _name_near(page.flat, address)
                if pair:
                    name, title = pair
                    kind = DiscoverySourceType.NAMED
            key = (name.lower(), address, url)
            if key in seen:
                continue
            seen.add(key)
            contacts.append(
                DiscoveredContact(
                    name=name,
                    title=title,
                    email=address,
                    phone="",
                    source_url=url,
                    source_type=kind,
                    evidence_snippet=snippet,
                    confidence=0.85 if kind is DiscoverySourceType.NAMED else 0.6,
                )
            )

        for match in _NAME_TITLE_RE.finditer(page.flat):
            name, raw_title = match.group(1).strip(), match.group(2).strip(" ,–—-|:")
            if not _plausible_person_name(name):
                continue
            classification = classify_title(raw_title)
            if not _title_names_a_role(classification):
                continue
            key = (name.lower(), "", url)
            if key in seen or any(
                c.name.lower() == name.lower() and c.source_url == url for c in contacts
            ):
                continue
            seen.add(key)
            contacts.append(
                DiscoveredContact(
                    name=name,
                    title=raw_title,
                    email="",
                    phone="",
                    source_url=url,
                    source_type=DiscoverySourceType.NAMED,
                    evidence_snippet=_snippet(page.flat, match.group(0)),
                    confidence=min(0.75, 0.4 + classification.confidence / 2),
                )
            )

        for match in _TEL_RE.finditer(page.html):
            phone = match.group(1).strip()
            key = ("", f"tel:{phone}", url)
            if key in seen:
                continue
            seen.add(key)
            contacts.append(
                DiscoveredContact(
                    name="",
                    title="",
                    email="",
                    phone=phone,
                    source_url=url,
                    source_type=DiscoverySourceType.GENERIC,
                    evidence_snippet=_snippet(page.flat, phone),
                    confidence=0.3,
                )
            )

    return contacts


def rank_contacts(contacts: list[DiscoveredContact]) -> ContactSelection:
    """Order by decision-making relevance using the existing role taxonomy.

    Named contacts are classified through classify_title (semantic matcher, not
    string equality); department mailboxes rank by outreach preference; bare
    phone numbers are supporting evidence only.
    """
    ranked: list[RankedContact] = []
    supporting: list[RankedContact] = []

    for contact in contacts:
        if contact.source_type is DiscoverySourceType.NAMED and contact.name:
            classification = classify_title(contact.title or None)
            role_names = ",".join(r.value for r in classification.roles)
            score = classification.confidence * 0.7 + (0.2 if contact.email else 0.0) + 0.1
            ranked.append(
                RankedContact(
                    contact=contact,
                    score=round(score, 3),
                    reasons=(
                        f"roles={role_names}",
                        f"role_confidence={classification.confidence:.2f}",
                        "reachable_email" if contact.email else "no_direct_email",
                    ),
                )
            )
        elif contact.email:
            local = contact.email.split("@", 1)[0].lower()
            try:
                preference = next(
                    i for i, p in enumerate(DEPARTMENT_PREFIXES) if local.startswith(p)
                )
            except StopIteration:
                preference = len(DEPARTMENT_PREFIXES)
            score = max(0.05, 0.5 - preference * 0.03)
            ranked.append(
                RankedContact(
                    contact=contact,
                    score=round(score, 3),
                    reasons=(f"department_mailbox={local}",),
                )
            )
        else:
            supporting.append(
                RankedContact(contact=contact, score=0.1, reasons=("phone_only",))
            )

    ranked.sort(key=lambda r: (-r.score, r.contact.email, r.contact.name))

    if not ranked:
        return ContactSelection(
            primary=None,
            alternatives=(),
            supporting=tuple(supporting),
            review_required=True,
            selection_reasons=("no usable contact was found on the researched pages",),
        )

    primary, rest = ranked[0], ranked[1:]
    reasons = ("primary selected by role relevance and reachability", *primary.reasons)
    return ContactSelection(
        primary=primary,
        alternatives=tuple(rest[:4]),
        supporting=tuple(supporting),
        rejected=tuple(rest[4:]),
        review_required=primary.contact.source_type is not DiscoverySourceType.NAMED,
        selection_reasons=reasons,
    )
