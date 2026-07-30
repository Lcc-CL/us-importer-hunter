"""Provider-neutral contracts for importer company discovery."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class DiscoveryProviderError(Exception):
    """A configured discovery source could not complete the search."""


class DiscoveryProviderUnavailable(DiscoveryProviderError):
    """The source cannot be used because capability or credentials are absent."""


@dataclass(frozen=True)
class CompanyDiscoveryQuery:
    original_prompt: str
    requested_count: int
    effective_count: int
    region: str
    category: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class CompanyCandidate:
    """One provider claim about a company, before canonical ingestion."""

    source: str
    company_name: str
    source_url: str | None = None
    external_id: str | None = None
    website: str | None = None
    address: str | None = None
    region: str | None = None
    product_description: str | None = None
    import_evidence: str | None = None
    raw_metadata_json: str = "{}"

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("company candidate requires a source")
        if not self.company_name.strip():
            raise ValueError("company candidate requires a company name")
        if not (self.source_url and self.source_url.strip()) and not (
            self.external_id and self.external_id.strip()
        ):
            raise ValueError("company candidate requires a source URL or external ID")


@dataclass(frozen=True)
class DiscoveryProviderFailure:
    reason: str
    external_id: str | None = None

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("provider failure requires a reason")


@dataclass(frozen=True)
class CompanyDiscoverySearchResult:
    candidates: tuple[CompanyCandidate, ...] = ()
    failures: tuple[DiscoveryProviderFailure, ...] = ()


class CompanyDiscoveryProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def search(self, query: CompanyDiscoveryQuery) -> CompanyDiscoverySearchResult: ...


def limit_candidates(
    candidates: Sequence[CompanyCandidate], *, limit: int
) -> tuple[CompanyCandidate, ...]:
    return tuple(candidates[:limit])
