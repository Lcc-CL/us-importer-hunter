"""Explainable deterministic scorer — mvp-explainable-scoring-v1.

⚠ NOT a business scoring model. Dimension weights, detectors and
normalized values are MVP placeholders so the pipeline runs end-to-end
with explainable, stable numbers; they will be recalibrated against real
outcomes (ADR-0021).

Honesty rules (tested):
- every ASSESSED dimension carries Evidence built from real sources;
- dimensions without evidence are UNKNOWN / INSUFFICIENT_EVIDENCE and
  earn exactly 0 — unknown is never negative;
- nothing is fabricated: no TEU, cargo value, China dependency, revenue
  or import frequency is invented from thin air;
- same input + same versions → identical assessment (and fingerprint).

Two explicit steps behind one interface: (1) score the dimensions,
(2) qualify via the versioned QualificationPolicy. The workflow only
orchestrates; both policies are injected and replaceable.
"""

from dataclasses import dataclass

from app.domain.scoring import (
    DimensionWeights,
    HardGatePolicy,
    QualificationPolicy,
)
from app.domain.services import OpportunityScoringInput
from app.domain.values import (
    Confidence,
    DataCompleteness,
    DimensionAssessment,
    DimensionStatus,
    Evidence,
    OpportunityAssessment,
    OpportunityScore,
    ScoreBreakdown,
    ScoringDimension,
    ScoringPolicy,
)

SCORING_VERSION = "mvp-explainable-scoring-v1"

_TRUSTED_SOURCES = frozenset({"importyeti", "import_evidence"})

# keyword detectors per dimension: (keywords, normalized_value_when_found).
# normalized values are placeholder calibrations: a matched signal is treated
# as strong-but-not-perfect evidence; with every dimension evidenced the
# total lands just above the QUALIFIED threshold — signals, not certainty.
_DETECTORS: dict[ScoringDimension, tuple[tuple[str, ...], float]] = {
    ScoringDimension.IMPORT_ACTIVITY: (("import", "shipment", "bol", "customs"), 0.8),
    ScoringDimension.CHINA_DEPENDENCY: (("china", "cnsha", "cn origin"), 0.7),
    ScoringDimension.SHIPPING_FIT: (("fcl", "lcl", "ocean", "container", "air freight"), 0.8),
    ScoringDimension.CARGO_VALUE_POTENTIAL: (("high value", "cargo value"), 0.6),
    ScoringDimension.COMPANY_SCALE: (("employees", "warehouse", "facility"), 0.6),
    ScoringDimension.GROWTH_SIGNAL: (("grow", "increas", "expand", "hiring", "funding"), 0.8),
    ScoringDimension.LOGISTICS_COMPLEXITY: (
        ("hazmat", "cold chain", "oversized", "multi-origin"),
        0.7,
    ),
}
_CONTACTABILITY_NORMALIZED = 0.5  # a reachable website is a path to contacts, nothing more

# Structured signal-kind → dimension. The pipeline stores every signal as
# "<kind>: <detail>", so a dimension is recognized from its declared kind
# regardless of the detail's language — the keyword detectors above are only a
# fallback for legacy free-text signals that carry no recognizable kind.
# Legacy/aliased kinds fold to the canonical dimension; kinds absent here
# (e.g. pain_point) are stored but never score, and add no weight.
_KIND_TO_DIMENSION: dict[str, ScoringDimension] = {
    "import_activity": ScoringDimension.IMPORT_ACTIVITY,
    "china_dependency": ScoringDimension.CHINA_DEPENDENCY,
    "shipping_fit": ScoringDimension.SHIPPING_FIT,
    "cargo_value": ScoringDimension.CARGO_VALUE_POTENTIAL,
    "cargo_value_potential": ScoringDimension.CARGO_VALUE_POTENTIAL,
    "company_scale": ScoringDimension.COMPANY_SCALE,
    "growth": ScoringDimension.GROWTH_SIGNAL,
    "growth_signal": ScoringDimension.GROWTH_SIGNAL,
    "complexity": ScoringDimension.LOGISTICS_COMPLEXITY,
    "logistics_complexity": ScoringDimension.LOGISTICS_COMPLEXITY,
}


@dataclass(frozen=True)
class DeterministicConfidenceWeights:
    """Confidence (evidence quality) knobs — separate from completeness."""

    base: float = 0.2
    per_source: float = 0.15
    trusted_source: float = 0.2
    maximum: float = 0.9


class DeterministicOpportunityScoringService:
    def __init__(
        self,
        weights: DimensionWeights | None = None,
        qualification_policy: QualificationPolicy | None = None,
        hard_gate_policy: HardGatePolicy | None = None,
        priority_policy: ScoringPolicy | None = None,
        confidence_weights: DeterministicConfidenceWeights | None = None,
    ) -> None:
        self._weights = weights or DimensionWeights()
        self._qualification = qualification_policy or QualificationPolicy()
        self._hard_gates = hard_gate_policy or HardGatePolicy()
        self._priority_policy = priority_policy or ScoringPolicy(version=SCORING_VERSION)
        self._confidence = confidence_weights or DeterministicConfidenceWeights()

    @property
    def scoring_version(self) -> str:
        return SCORING_VERSION

    async def assess(self, scoring_input: OpportunityScoringInput) -> OpportunityAssessment:
        # step 1 — score each dimension explainably
        dimensions = tuple(
            self._assess_dimension(dimension, scoring_input) for dimension in ScoringDimension
        )
        breakdown = ScoreBreakdown.from_dimensions(dimensions)
        score = OpportunityScore(min(breakdown.total_score, 100.0))
        completeness = DataCompleteness(
            breakdown.assessed_weight / breakdown.maximum_score if breakdown.maximum_score else 0.0
        )
        confidence = self._overall_confidence(scoring_input)

        reasons = self._reasons(dimensions, completeness, scoring_input)
        evidence = tuple(e for d in dimensions for e in d.evidence)

        # step 2 — qualification via the versioned policy (hard gates first)
        hits = self._hard_gates.evaluate(scoring_input.signals, scoring_input.sources)
        decision, action = self._qualification.decide(
            score=score, confidence=confidence, completeness=completeness, hard_gate_hits=hits
        )
        if hits:
            reasons += tuple(f"hard gate {hit.gate.value}: {hit.reason}" for hit in hits)
            evidence += tuple(hit.evidence for hit in hits)

        return OpportunityAssessment(
            new_score=score,
            confidence=confidence,
            data_completeness=completeness,
            reasons=reasons,
            evidence=evidence,
            priority=self._priority_policy.priority_for(score),
            qualification_decision=decision,
            recommended_action=action.value,
            score_breakdown=breakdown,
            assessed_by=type(self).__name__,
            scoring_version=SCORING_VERSION,
            policy_version=self._qualification.version,
            user_lens_version=scoring_input.user_lens_version,
            assessed_at=scoring_input.assessed_at,
        )

    # -- dimension evaluation -------------------------------------------

    def _assess_dimension(
        self, dimension: ScoringDimension, scoring_input: OpportunityScoringInput
    ) -> DimensionAssessment:
        weight = self._weights.of(dimension)
        if not scoring_input.sources:
            return DimensionAssessment(
                dimension=dimension,
                weight=weight,
                status=DimensionStatus.INSUFFICIENT_EVIDENCE,
                earned_score=0.0,
                reasons=("no source references — cannot evidence this dimension",),
            )

        if dimension is ScoringDimension.CONTACTABILITY:
            return self._assess_contactability(weight, scoring_input)

        keywords, normalized = _DETECTORS[dimension]
        # Prefer the structured signal kind (locale-independent); fall back to
        # English keyword detection only for legacy signals with no known kind.
        match = self._first_kind_match(scoring_input.signals, dimension)
        if match is None:
            match = self._first_match(scoring_input.signals, keywords)
        if match is None:
            return DimensionAssessment(
                dimension=dimension,
                weight=weight,
                status=DimensionStatus.UNKNOWN,
                earned_score=0.0,
                reasons=(f"no {dimension.value} signal observed — unknown, not negative",),
            )
        return DimensionAssessment(
            dimension=dimension,
            weight=weight,
            status=DimensionStatus.ASSESSED,
            normalized_value=normalized,
            earned_score=weight * normalized,
            raw_value=match,
            confidence=self._dimension_confidence(scoring_input),
            reasons=(f"signal observed: {match!r} (+{weight * normalized:g})",),
            evidence=(Evidence(claim=match, sources=scoring_input.sources),),
        )

    def _assess_contactability(
        self, weight: float, scoring_input: OpportunityScoringInput
    ) -> DimensionAssessment:
        if not scoring_input.website_host:
            return DimensionAssessment(
                dimension=ScoringDimension.CONTACTABILITY,
                weight=weight,
                status=DimensionStatus.UNKNOWN,
                earned_score=0.0,
                reasons=("no website known — contact path unknown, not negative",),
            )
        normalized = _CONTACTABILITY_NORMALIZED
        return DimensionAssessment(
            dimension=ScoringDimension.CONTACTABILITY,
            weight=weight,
            status=DimensionStatus.ASSESSED,
            normalized_value=normalized,
            earned_score=weight * normalized,
            raw_value=scoring_input.website_host,
            confidence=self._dimension_confidence(scoring_input),
            reasons=(
                f"reachable website {scoring_input.website_host} — a contact path exists "
                f"(+{weight * normalized:g})",
            ),
            evidence=(
                Evidence(
                    claim=f"website {scoring_input.website_host} recorded by sources",
                    sources=scoring_input.sources,
                ),
            ),
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _first_kind_match(signals: tuple[str, ...], dimension: ScoringDimension) -> str | None:
        """Match by the signal's declared kind (the "<kind>:" prefix), mapped
        through the alias table — language-independent, unlike keyword search."""
        for signal in signals:
            kind = signal.split(":", 1)[0].strip().lower()
            if _KIND_TO_DIMENSION.get(kind) is dimension:
                return signal
        return None

    @staticmethod
    def _first_match(signals: tuple[str, ...], keywords: tuple[str, ...]) -> str | None:
        for signal in signals:
            lowered = signal.lower()
            if any(keyword in lowered for keyword in keywords):
                return signal
        return None

    def _dimension_confidence(self, scoring_input: OpportunityScoringInput) -> float:
        trusted = {ref.source for ref in scoring_input.sources} & _TRUSTED_SOURCES
        return 0.8 if trusted else 0.5

    def _overall_confidence(self, scoring_input: OpportunityScoringInput) -> Confidence:
        w = self._confidence
        distinct = {ref.source for ref in scoring_input.sources}
        value = w.base + w.per_source * len(distinct)
        if distinct & _TRUSTED_SOURCES:
            value += w.trusted_source
        return Confidence(min(value, w.maximum))

    @staticmethod
    def _reasons(
        dimensions: tuple[DimensionAssessment, ...],
        completeness: DataCompleteness,
        scoring_input: OpportunityScoringInput,
    ) -> tuple[str, ...]:
        reasons = [reason for d in dimensions for reason in d.reasons]
        reasons.append(
            f"data completeness {completeness.value:.0%} — unknown dimensions lower "
            "coverage, never the score"
        )
        if not scoring_input.sources:
            reasons.append("no source references — confidence floor applied")
        reasons.extend(scoring_input.signal_selection_reasons)
        return tuple(reasons)
