"""Scoring value objects and policies (L9): weights, breakdowns,
completeness, hard gates, qualification thresholds, fingerprints."""

from datetime import UTC, datetime

import pytest

from app.domain.exceptions import DomainError, MissingEvidence
from app.domain.scoring import (
    DEFAULT_DIMENSION_WEIGHTS,
    DimensionWeights,
    HardGate,
    HardGateHit,
    HardGatePolicy,
    QualificationPolicy,
)
from app.domain.values import (
    Confidence,
    DataCompleteness,
    DimensionAssessment,
    DimensionStatus,
    Evidence,
    OpportunityScore,
    QualificationDecision,
    RecommendedAction,
    ScoreBreakdown,
    ScoringDimension,
    SourceReference,
)
from tests.domain.conftest import make_assessment

FIXED_AT = datetime(2026, 7, 16, tzinfo=UTC)
SOURCES = (SourceReference(source="importyeti", reference="https://r/1", retrieved_at=FIXED_AT),)
EVIDENCE = Evidence(claim="import signal observed", sources=SOURCES)


def assessed(dimension: ScoringDimension, weight: float, normalized: float) -> DimensionAssessment:
    return DimensionAssessment(
        dimension=dimension,
        weight=weight,
        status=DimensionStatus.ASSESSED,
        normalized_value=normalized,
        earned_score=weight * normalized,
        confidence=0.8,
        reasons=("observed",),
        evidence=(EVIDENCE,),
    )


def unknown(dimension: ScoringDimension, weight: float) -> DimensionAssessment:
    return DimensionAssessment(
        dimension=dimension, weight=weight, status=DimensionStatus.UNKNOWN, earned_score=0.0
    )


class TestDimensionWeights:
    def test_default_weights_sum_to_100(self) -> None:
        assert sum(DimensionWeights().weights.values()) == 100.0

    def test_wrong_total_rejected(self) -> None:
        broken = dict(DEFAULT_DIMENSION_WEIGHTS)
        broken[ScoringDimension.IMPORT_ACTIVITY] = 25.0
        with pytest.raises(DomainError, match="sum to 100"):
            DimensionWeights(weights=broken)

    def test_missing_dimension_rejected(self) -> None:
        partial = dict(DEFAULT_DIMENSION_WEIGHTS)
        del partial[ScoringDimension.CONTACTABILITY]
        with pytest.raises(DomainError, match="every scoring dimension"):
            DimensionWeights(weights=partial)

    def test_negative_weight_rejected(self) -> None:
        broken = dict(DEFAULT_DIMENSION_WEIGHTS)
        broken[ScoringDimension.IMPORT_ACTIVITY] = -20.0
        broken[ScoringDimension.CHINA_DEPENDENCY] = 55.0
        with pytest.raises(DomainError, match="positive"):
            DimensionWeights(weights=broken)


class TestDimensionAssessment:
    def test_assessed_requires_evidence(self) -> None:
        with pytest.raises(MissingEvidence):
            DimensionAssessment(
                dimension=ScoringDimension.IMPORT_ACTIVITY,
                weight=20.0,
                status=DimensionStatus.ASSESSED,
                normalized_value=0.5,
                earned_score=10.0,
            )

    def test_earned_score_must_match_weight_times_normalized(self) -> None:
        with pytest.raises(DomainError, match="earned_score"):
            DimensionAssessment(
                dimension=ScoringDimension.IMPORT_ACTIVITY,
                weight=20.0,
                status=DimensionStatus.ASSESSED,
                normalized_value=0.5,
                earned_score=99.0,
                evidence=(EVIDENCE,),
            )

    def test_unknown_must_earn_zero(self) -> None:
        """Unknown data is not negative data — and not positive either."""
        with pytest.raises(DomainError, match="must earn 0"):
            DimensionAssessment(
                dimension=ScoringDimension.CARGO_VALUE_POTENTIAL,
                weight=10.0,
                status=DimensionStatus.UNKNOWN,
                earned_score=-5.0,
            )

    def test_normalized_range_enforced(self) -> None:
        with pytest.raises(DomainError):
            DimensionAssessment(
                dimension=ScoringDimension.IMPORT_ACTIVITY,
                weight=20.0,
                status=DimensionStatus.ASSESSED,
                normalized_value=1.5,
                earned_score=30.0,
                evidence=(EVIDENCE,),
            )


class TestScoreBreakdown:
    def test_from_dimensions_math(self) -> None:
        breakdown = ScoreBreakdown.from_dimensions(
            (
                assessed(ScoringDimension.IMPORT_ACTIVITY, 20.0, 0.7),
                unknown(ScoringDimension.CARGO_VALUE_POTENTIAL, 10.0),
            )
        )
        assert breakdown.total_score == 14.0
        assert breakdown.maximum_score == 30.0
        assert breakdown.assessed_weight == 20.0
        assert breakdown.missing_weight == 10.0

    def test_duplicate_dimensions_rejected(self) -> None:
        with pytest.raises(DomainError, match="duplicate"):
            ScoreBreakdown.from_dimensions(
                (
                    unknown(ScoringDimension.IMPORT_ACTIVITY, 20.0),
                    unknown(ScoringDimension.IMPORT_ACTIVITY, 20.0),
                )
            )


class TestDataCompleteness:
    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_range_enforced(self, value: float) -> None:
        with pytest.raises(DomainError):
            DataCompleteness(value)


class TestHardGatePolicy:
    def test_marker_signal_with_sources_triggers_gate(self) -> None:
        hits = HardGatePolicy().evaluate(
            ("non_us_target: registered and operating in Canada",), SOURCES
        )
        assert len(hits) == 1
        assert hits[0].gate is HardGate.NON_US_TARGET
        assert hits[0].evidence.sources == SOURCES

    def test_no_sources_means_no_gate(self) -> None:
        """A gate without evidence is a rumor — rumors don't disqualify."""
        hits = HardGatePolicy().evaluate(("non_us_target: allegedly Canadian",), ())
        assert hits == ()

    def test_ordinary_signals_never_trigger(self) -> None:
        hits = HardGatePolicy().evaluate(("volume_trend: growing imports",), SOURCES)
        assert hits == ()

    def test_hit_requires_reason(self) -> None:
        with pytest.raises(DomainError):
            HardGateHit(gate=HardGate.NON_US_TARGET, reason="  ", evidence=EVIDENCE)


class TestQualificationPolicy:
    POLICY = QualificationPolicy()

    def decide(
        self,
        score: float,
        confidence: float,
        completeness: float,
        hits: tuple[HardGateHit, ...] = (),
    ) -> tuple[QualificationDecision, RecommendedAction]:
        return self.POLICY.decide(
            score=OpportunityScore(score),
            confidence=Confidence(confidence),
            completeness=DataCompleteness(completeness),
            hard_gate_hits=hits,
        )

    def test_qualified_at_exact_thresholds(self) -> None:
        assert self.decide(70.0, 0.65, 0.50) == (
            QualificationDecision.QUALIFIED,
            RecommendedAction.PREPARE_OUTREACH,
        )

    @pytest.mark.parametrize(
        ("score", "confidence", "completeness"),
        [(69.9, 0.65, 0.50), (70.0, 0.64, 0.50), (70.0, 0.65, 0.49)],
    )
    def test_just_below_any_threshold_is_review(
        self, score: float, confidence: float, completeness: float
    ) -> None:
        assert self.decide(score, confidence, completeness) == (
            QualificationDecision.REVIEW,
            RecommendedAction.HUMAN_REVIEW,
        )

    def test_thin_data_means_research_not_low_value(self) -> None:
        """completeness < 0.40 → RESEARCH_MORE even with a high score."""
        assert self.decide(95.0, 0.9, 0.39) == (
            QualificationDecision.RESEARCH_MORE,
            RecommendedAction.COLLECT_MORE_DATA,
        )

    def test_weak_but_complete_data_is_a_human_call(self) -> None:
        assert self.decide(20.0, 0.8, 0.9) == (
            QualificationDecision.REVIEW,
            RecommendedAction.HUMAN_REVIEW,
        )

    def test_hard_gate_wins_over_everything(self) -> None:
        hit = HardGateHit(
            gate=HardGate.NO_INTERNATIONAL_IMPORT_ACTIVITY,
            reason="no_international_import_activity: domestic distributor only",
            evidence=EVIDENCE,
        )
        assert self.decide(95.0, 0.9, 0.9, hits=(hit,)) == (
            QualificationDecision.DISQUALIFIED,
            RecommendedAction.DO_NOT_CONTACT,
        )

    def test_invalid_thresholds_rejected(self) -> None:
        with pytest.raises(DomainError):
            QualificationPolicy(review_score=80.0, qualified_score=70.0)
        with pytest.raises(DomainError):
            QualificationPolicy(research_completeness=0.6, qualified_completeness=0.5)


class TestAssessmentFingerprint:
    def test_same_content_same_fingerprint_despite_time(self) -> None:
        first = make_assessment(80.0)
        second = make_assessment(80.0)  # different assessed_at (utcnow)
        assert first.assessed_at != second.assessed_at
        assert first.assessment_fingerprint == second.assessment_fingerprint

    def test_different_score_different_fingerprint(self) -> None:
        assert (
            make_assessment(80.0).assessment_fingerprint
            != make_assessment(81.0).assessment_fingerprint
        )

    def test_fingerprint_is_sha256_hex(self) -> None:
        fingerprint = make_assessment().assessment_fingerprint
        assert len(fingerprint) == 64
        assert all(c in "0123456789abcdef" for c in fingerprint)
