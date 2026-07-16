"""Value objects: immutable, self-validating domain values.

Every object here validates at construction time and compares by value.
No primitive (bare str/float) crosses an aggregate boundary when one of
these types exists for it — see ADR-0016.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

from app.domain.clock import ensure_utc, utcnow
from app.domain.exceptions import (
    DomainError,
    InvalidCompanyName,
    InvalidConfidence,
    InvalidEmailAddress,
    InvalidOpportunityScore,
    InvalidWebsiteUrl,
    MissingEvidence,
)

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
_MAX_NAME_LENGTH = 200


@dataclass(frozen=True)
class CompanyName:
    """Canonical or alias name of an importer."""

    value: str

    def __post_init__(self) -> None:
        cleaned = " ".join(self.value.split())
        if not cleaned:
            raise InvalidCompanyName("company name must not be empty")
        if len(cleaned) > _MAX_NAME_LENGTH:
            raise InvalidCompanyName(f"company name exceeds {_MAX_NAME_LENGTH} characters")
        object.__setattr__(self, "value", cleaned)

    @property
    def normalized(self) -> str:
        """Dedup key: lowercased, whitespace-collapsed."""
        return self.value.lower()


@dataclass(frozen=True)
class WebsiteUrl:
    """Company website — http(s) only, host required."""

    value: str

    def __post_init__(self) -> None:
        parsed = urlparse(self.value.strip())
        if parsed.scheme not in ("http", "https"):
            raise InvalidWebsiteUrl(f"unsupported scheme: {self.value!r}")
        if not parsed.netloc or "." not in parsed.netloc:
            raise InvalidWebsiteUrl(f"missing or invalid host: {self.value!r}")
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower()
        ).geturl()
        object.__setattr__(self, "value", normalized)

    @property
    def host(self) -> str:
        return urlparse(self.value).netloc


@dataclass(frozen=True)
class EmailAddress:
    """A deliverable-looking email address."""

    value: str

    def __post_init__(self) -> None:
        cleaned = self.value.strip()
        if not _EMAIL_RE.match(cleaned):
            raise InvalidEmailAddress(f"not a valid email address: {self.value!r}")
        object.__setattr__(self, "value", cleaned.lower())

    @property
    def domain(self) -> str:
        return self.value.rsplit("@", 1)[1]


@dataclass(frozen=True)
class OpportunityScore:
    """How attractive a prospect is, 0–100."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 100.0:
            raise InvalidOpportunityScore(f"score must be within 0–100, got {self.value}")


@dataclass(frozen=True)
class Confidence:
    """How much the evidence supports the score, 0–1."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise InvalidConfidence(f"confidence must be within 0–1, got {self.value}")


class Priority(StrEnum):
    """Ranking bucket — derived via ScoringPolicy, never set by hand."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class ScoringPolicy:
    """Score-to-priority mapping. Owned and versioned by scoring, like the
    scorer itself — thresholds are policy, not domain constants (L4 review)."""

    version: str
    high_threshold: float = 70.0
    medium_threshold: float = 40.0

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise DomainError("scoring policy requires a version")
        if not 0.0 < self.medium_threshold < self.high_threshold <= 100.0:
            raise DomainError(
                "scoring policy thresholds must satisfy 0 < medium < high <= 100, got "
                f"medium={self.medium_threshold}, high={self.high_threshold}"
            )

    def priority_for(self, score: OpportunityScore) -> Priority:
        if score.value >= self.high_threshold:
            return Priority.HIGH
        if score.value >= self.medium_threshold:
            return Priority.MEDIUM
        return Priority.LOW


DEFAULT_SCORING_POLICY = ScoringPolicy(version="policy-v1")


@dataclass(frozen=True)
class SourceReference:
    """Provenance: which source said this, where, and when."""

    source: str
    reference: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise DomainError("source reference requires a source name")
        if not self.reference.strip():
            raise DomainError("source reference requires a reference (url/id)")
        object.__setattr__(
            self, "retrieved_at", ensure_utc(self.retrieved_at, field="retrieved_at")
        )


@dataclass(frozen=True)
class Evidence:
    """A claim plus the provenance that backs it."""

    claim: str
    sources: tuple[SourceReference, ...]

    def __post_init__(self) -> None:
        if not self.claim.strip():
            raise MissingEvidence("evidence requires a claim")
        if not self.sources:
            raise MissingEvidence("evidence requires at least one source reference")


@dataclass(frozen=True, kw_only=True)
class OpportunityAssessment:
    """One immutable scoring judgment — the unit of the append-only history."""

    new_score: OpportunityScore
    confidence: Confidence
    reasons: tuple[str, ...]
    scoring_version: str
    evidence: tuple[Evidence, ...] = ()
    old_score: OpportunityScore | None = None
    user_lens_version: str | None = None
    assessed_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.scoring_version.strip():
            raise DomainError("assessment requires a scoring_version")
        if not self.reasons or not all(reason.strip() for reason in self.reasons):
            raise MissingEvidence("assessment requires at least one non-empty reason")
        object.__setattr__(self, "assessed_at", ensure_utc(self.assessed_at, field="assessed_at"))


@dataclass(frozen=True)
class IdempotencyKey:
    """Deduplication key for operations that must not run twice."""

    value: str

    def __post_init__(self) -> None:
        cleaned = self.value.strip()
        if not cleaned:
            raise DomainError("idempotency key must not be empty")
        object.__setattr__(self, "value", cleaned)

    @classmethod
    def from_parts(cls, *parts: str) -> "IdempotencyKey":
        if not parts or not all(part.strip() for part in parts):
            raise DomainError("idempotency key parts must be non-empty")
        return cls(":".join(part.strip() for part in parts))
