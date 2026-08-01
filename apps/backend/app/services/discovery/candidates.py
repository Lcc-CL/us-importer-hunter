"""Normalize and deduplicate provider candidates before Company ingestion."""

from dataclasses import dataclass
from urllib.parse import urlparse

from app.domain.discovery import CompanyCandidate
from app.shared.normalization import normalize_company_name


@dataclass(frozen=True)
class PreparedCandidate:
    candidate: CompanyCandidate
    normalized_name: str
    normalized_domain: str | None
    duplicate_of_index: int | None = None


def normalize_domain(website: str | None) -> str | None:
    if not website or not website.strip():
        return None
    candidate = website.strip()
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host or None


def _address_key(address: str | None) -> str:
    return " ".join((address or "").lower().split())


def prepare_candidates(candidates: tuple[CompanyCandidate, ...]) -> tuple[PreparedCandidate, ...]:
    prepared: list[PreparedCandidate] = []
    seen_domains: dict[str, int] = {}
    seen_name_addresses: dict[tuple[str, str], int] = {}

    for candidate in candidates:
        normalized_name = normalize_company_name(candidate.company_name)
        normalized_domain = normalize_domain(candidate.website)
        duplicate_of: int | None = None
        if normalized_domain:
            duplicate_of = seen_domains.get(normalized_domain)
        else:
            duplicate_of = seen_name_addresses.get(
                (normalized_name, _address_key(candidate.address))
            )

        index = len(prepared)
        prepared.append(
            PreparedCandidate(
                candidate=candidate,
                normalized_name=normalized_name,
                normalized_domain=normalized_domain,
                duplicate_of_index=duplicate_of,
            )
        )
        if duplicate_of is None:
            if normalized_domain:
                seen_domains[normalized_domain] = index
            else:
                seen_name_addresses[(normalized_name, _address_key(candidate.address))] = index

    return tuple(prepared)
