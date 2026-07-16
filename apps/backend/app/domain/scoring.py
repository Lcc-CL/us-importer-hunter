"""Scoring policies (L9): weights, qualification thresholds, hard gates.

Everything here is a **versioned MVP assumption** — initial hypotheses to
be recalibrated against real reply/deal outcomes (ADR-0021). Policies are
pure domain objects: no database, no network, no framework.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from app.domain.exceptions import DomainError, MissingEvidence
from app.domain.values import (
    Confidence,
    DataCompleteness,
    Evidence,
    OpportunityScore,
    QualificationDecision,
    RecommendedAction,
    ScoringDimension,
    SourceReference,
)

DEFAULT_DIMENSION_WEIGHTS: Mapping[ScoringDimension, float] = MappingProxyType(
    {
        ScoringDimension.IMPORT_ACTIVITY: 20.0,
        ScoringDimension.CHINA_DEPENDENCY: 15.0,
        ScoringDimension.SHIPPING_FIT: 15.0,
        ScoringDimension.CARGO_VALUE_POTENTIAL: 10.0,
        ScoringDimension.COMPANY_SCALE: 10.0,
        ScoringDimension.GROWTH_SIGNAL: 10.0,
        ScoringDimension.CONTACTABILITY: 10.0,
        ScoringDimension.LOGISTICS_COMPLEXITY: 10.0,
    }
)


@dataclass(frozen=True)
class DimensionWeights:
    """The v1 weight table. Total must be exactly 100."""

    weights: Mapping[ScoringDimension, float] = field(
        default_factory=lambda: DEFAULT_DIMENSION_WEIGHTS
    )

    def __post_init__(self) -> None:
        if set(self.weights) != set(ScoringDimension):
            raise DomainError("weights must cover every scoring dimension exactly once")
        if any(weight <= 0 for weight in self.weights.values()):
            raise DomainError("dimension weights must be positive")
        total = sum(self.weights.values())
        if abs(total - 100.0) > 1e-6:
            raise DomainError(f"dimension weights must sum to 100, got {total}")
        object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))

    def of(self, dimension: ScoringDimension) -> float:
        return self.weights[dimension]


class HardGate(StrEnum):
    """Explicit negative facts that end pursuit — never data absence."""

    NON_US_TARGET = "non_us_target"
    NO_INTERNATIONAL_IMPORT_ACTIVITY = "no_international_import_activity"
    OUT_OF_SCOPE_INDUSTRY = "out_of_scope_industry"


@dataclass(frozen=True)
class HardGateHit:
    """A triggered gate. Evidence is mandatory — no evidence, no gate."""

    gate: HardGate
    reason: str
    evidence: Evidence

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise DomainError("hard gate hit requires a reason")


class HardGatePolicy:
    """Detects explicit disqualifying facts in signals.

    Gates fire only on machine-explicit signal markers (`<gate>: detail`)
    AND only when source references exist to build evidence from —
    a gate without evidence is a rumor, and rumors don't disqualify.
    """

    version = "mvp-hard-gates-v1"

    def evaluate(
        self, signals: tuple[str, ...], sources: tuple[SourceReference, ...]
    ) -> tuple[HardGateHit, ...]:
        if not sources:
            return ()
        hits: list[HardGateHit] = []
        for signal in signals:
            marker = signal.split(":", 1)[0].strip().lower()
            for gate in HardGate:
                if marker == gate.value:
                    hits.append(
                        HardGateHit(
                            gate=gate,
                            reason=signal,
                            evidence=Evidence(claim=signal, sources=sources),
                        )
                    )
        return tuple(hits)


@dataclass(frozen=True)
class QualificationPolicy:
    """mvp-qualification-policy-v1 — initial thresholds, NOT validated
    against real outcomes yet; recalibrated once reply/deal data exists.

    Rules (in order):
    - hard gate hit (with evidence)        → DISQUALIFIED / DO_NOT_CONTACT
    - completeness < research_threshold    → RESEARCH_MORE / COLLECT_MORE_DATA
    - score ≥ 70 ∧ conf ≥ 0.65 ∧ compl ≥ 0.50 → QUALIFIED / PREPARE_OUTREACH
    - score ≥ 50                           → REVIEW / HUMAN_REVIEW
    - otherwise                            → REVIEW (weak but complete data
      is a human call — data thinness alone never disqualifies)
    """

    version: str = "mvp-qualification-policy-v1"
    qualified_score: float = 70.0
    qualified_confidence: float = 0.65
    qualified_completeness: float = 0.50
    review_score: float = 50.0
    research_completeness: float = 0.40

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise DomainError("qualification policy requires a version")
        if not 0.0 <= self.research_completeness <= self.qualified_completeness <= 1.0:
            raise DomainError(
                "completeness thresholds must satisfy 0 <= research <= qualified <= 1"
            )
        if not 0.0 < self.review_score < self.qualified_score <= 100.0:
            raise DomainError("score thresholds must satisfy 0 < review < qualified <= 100")

    def decide(
        self,
        *,
        score: OpportunityScore,
        confidence: Confidence,
        completeness: DataCompleteness,
        hard_gate_hits: tuple[HardGateHit, ...] = (),
    ) -> tuple[QualificationDecision, RecommendedAction]:
        for hit in hard_gate_hits:
            if not hit.evidence.sources:  # defensive: HardGateHit already enforces
                raise MissingEvidence(f"hard gate {hit.gate} triggered without evidence")
        if hard_gate_hits:
            return QualificationDecision.DISQUALIFIED, RecommendedAction.DO_NOT_CONTACT
        if completeness.value < self.research_completeness:
            return QualificationDecision.RESEARCH_MORE, RecommendedAction.COLLECT_MORE_DATA
        if (
            score.value >= self.qualified_score
            and confidence.value >= self.qualified_confidence
            and completeness.value >= self.qualified_completeness
        ):
            return QualificationDecision.QUALIFIED, RecommendedAction.PREPARE_OUTREACH
        return QualificationDecision.REVIEW, RecommendedAction.HUMAN_REVIEW
