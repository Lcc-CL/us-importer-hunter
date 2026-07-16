"""Value objects: immutable, self-validating domain values.

Every object here validates at construction time and compares by value.
No primitive (bare str/float) crosses an aggregate boundary when one of
these types exists for it — see ADR-0016.
"""

import hashlib
import json
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


class ScoringDimension(StrEnum):
    """The eight v1 scoring dimensions (L9). Weights live in policy."""

    IMPORT_ACTIVITY = "import_activity"
    CHINA_DEPENDENCY = "china_dependency"
    SHIPPING_FIT = "shipping_fit"
    CARGO_VALUE_POTENTIAL = "cargo_value_potential"
    COMPANY_SCALE = "company_scale"
    GROWTH_SIGNAL = "growth_signal"
    CONTACTABILITY = "contactability"
    LOGISTICS_COMPLEXITY = "logistics_complexity"


class DimensionStatus(StrEnum):
    ASSESSED = "assessed"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"


class QualificationDecision(StrEnum):
    QUALIFIED = "qualified"
    REVIEW = "review"
    RESEARCH_MORE = "research_more"
    DISQUALIFIED = "disqualified"


class RecommendedAction(StrEnum):
    PREPARE_OUTREACH = "prepare_outreach"
    HUMAN_REVIEW = "human_review"
    COLLECT_MORE_DATA = "collect_more_data"
    DO_NOT_CONTACT = "do_not_contact"


@dataclass(frozen=True)
class DataCompleteness:
    """Coverage of the judgment: evidence-backed weight ÷ applicable weight.

    Distinct from Confidence (evidence *quality*): unknown data lowers
    completeness, never the score itself — unknown is not negative.
    """

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise DomainError(f"data completeness must be within 0–1, got {self.value}")


@dataclass(frozen=True, kw_only=True)
class DimensionAssessment:
    """One dimension's explainable verdict inside a score breakdown."""

    dimension: ScoringDimension
    weight: float
    status: DimensionStatus
    earned_score: float
    normalized_value: float | None = None
    raw_value: str | None = None
    confidence: float = 0.0
    reasons: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise DomainError(f"{self.dimension}: weight must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise DomainError(f"{self.dimension}: confidence must be within 0–1")
        if self.status is DimensionStatus.ASSESSED:
            if self.normalized_value is None or not 0.0 <= self.normalized_value <= 1.0:
                raise DomainError(f"{self.dimension}: assessed requires normalized_value in 0–1")
            if not self.evidence:
                raise MissingEvidence(f"{self.dimension}: assessed requires evidence")
            expected = self.weight * self.normalized_value
            if abs(self.earned_score - expected) > 1e-6:
                raise DomainError(
                    f"{self.dimension}: earned_score {self.earned_score} != "
                    f"weight × normalized ({expected})"
                )
        else:
            # unknown is not negative: unmeasured dimensions earn exactly 0
            if self.earned_score != 0.0 or self.normalized_value is not None:
                raise DomainError(
                    f"{self.dimension}: {self.status.value} dimensions must earn 0"
                )


@dataclass(frozen=True, kw_only=True)
class ScoreBreakdown:
    """The full explainable decomposition of one assessment."""

    dimensions: tuple[DimensionAssessment, ...]
    total_score: float
    maximum_score: float
    assessed_weight: float
    missing_weight: float

    def __post_init__(self) -> None:
        seen = [d.dimension for d in self.dimensions]
        if len(seen) != len(set(seen)):
            raise DomainError("score breakdown contains duplicate dimensions")
        if abs(self.total_score - sum(d.earned_score for d in self.dimensions)) > 1e-6:
            raise DomainError("total_score does not match the sum of earned scores")
        if abs(self.assessed_weight + self.missing_weight - self.maximum_score) > 1e-6:
            raise DomainError("assessed + missing weight must equal maximum score")

    @classmethod
    def from_dimensions(cls, dimensions: tuple[DimensionAssessment, ...]) -> "ScoreBreakdown":
        maximum = sum(d.weight for d in dimensions)
        assessed = sum(d.weight for d in dimensions if d.status is DimensionStatus.ASSESSED)
        return cls(
            dimensions=dimensions,
            total_score=sum(d.earned_score for d in dimensions),
            maximum_score=maximum,
            assessed_weight=assessed,
            missing_weight=maximum - assessed,
        )


@dataclass(frozen=True, kw_only=True)
class OpportunityAssessment:
    """One immutable scoring judgment — the unit of the append-only history.

    priority / recommended_action / assessed_by are produced by the
    scoring service (its policy owns the thresholds — ADR-0020); when
    priority is absent the aggregate falls back to its ScoringPolicy.
    """

    new_score: OpportunityScore
    confidence: Confidence
    reasons: tuple[str, ...]
    scoring_version: str
    evidence: tuple[Evidence, ...] = ()
    old_score: OpportunityScore | None = None
    priority: Priority | None = None
    recommended_action: str | None = None
    assessed_by: str | None = None
    user_lens_version: str | None = None
    data_completeness: DataCompleteness | None = None
    qualification_decision: QualificationDecision | None = None
    score_breakdown: ScoreBreakdown | None = None
    policy_version: str = "unversioned"  # real scorers always set it; default for bare tests
    assessment_fingerprint: str = ""  # auto-computed (SHA-256) when omitted
    assessed_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.scoring_version.strip():
            raise DomainError("assessment requires a scoring_version")
        if not self.policy_version.strip():
            raise DomainError("assessment requires a policy_version")
        if not self.reasons or not all(reason.strip() for reason in self.reasons):
            raise MissingEvidence("assessment requires at least one non-empty reason")
        object.__setattr__(self, "assessed_at", ensure_utc(self.assessed_at, field="assessed_at"))
        if not self.assessment_fingerprint:
            object.__setattr__(self, "assessment_fingerprint", self._compute_fingerprint())

    def _compute_fingerprint(self) -> str:
        """SHA-256 over canonical, time-independent judgment content:
        same facts + same versions → same fingerprint, always."""
        canonical = json.dumps(
            {
                "scoring_version": self.scoring_version,
                "policy_version": self.policy_version,
                "new_score": self.new_score.value,
                "confidence": self.confidence.value,
                "completeness": self.data_completeness.value if self.data_completeness else None,
                "priority": self.priority.value if self.priority else None,
                "qualification": (
                    self.qualification_decision.value if self.qualification_decision else None
                ),
                "recommended_action": self.recommended_action,
                "reasons": list(self.reasons),
                "evidence_claims": [e.claim for e in self.evidence],
                "user_lens_version": self.user_lens_version,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
