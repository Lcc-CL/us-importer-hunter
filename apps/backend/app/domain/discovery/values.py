"""Discovery value objects: what a source claimed, before it becomes truth.

A discovery is a *claim* about a company, not a canonical Company —
deduplication and fact-merging happen in the Company context, consuming
Discovery's events (ADR-0018). Everything here is immutable.
"""

from dataclasses import dataclass

from app.domain.exceptions import DomainError
from app.domain.values import Evidence, SourceReference


@dataclass(frozen=True)
class RawCompanySnapshot:
    """What one source said about one company, verbatim and unvalidated.

    Text fields stay raw on purpose: normalization into CompanyName /
    WebsiteUrl happens when (and if) the Company context accepts the claim.
    """

    name_text: str
    source: SourceReference
    website_text: str | None = None
    location_text: str | None = None
    description_text: str | None = None

    def __post_init__(self) -> None:
        if not self.name_text.strip():
            raise DomainError("snapshot requires a non-empty company name text")


@dataclass(frozen=True)
class Signal:
    """One observed switching hint (e.g. volume trend, cadence gap)."""

    kind: str
    detail: str

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise DomainError("signal requires a kind")
        if not self.detail.strip():
            raise DomainError("signal requires a detail")


@dataclass(frozen=True)
class DiscoveryResult:
    """One discovered company claim: snapshot + supporting evidence + signals.

    Deliberately NOT a Company — creating canonical companies is the
    Company context's job, downstream of the CompanyDiscovered event.
    """

    snapshot: RawCompanySnapshot
    evidence: tuple[Evidence, ...] = ()
    signals: tuple[Signal, ...] = ()


@dataclass(frozen=True)
class DiscoveryStats:
    """Run statistics: how many claims were found, how many source
    queries succeeded/failed."""

    discovered: int = 0
    succeeded: int = 0
    failed: int = 0

    def __post_init__(self) -> None:
        if self.discovered < 0 or self.succeeded < 0 or self.failed < 0:
            raise DomainError("discovery stats must be non-negative")
