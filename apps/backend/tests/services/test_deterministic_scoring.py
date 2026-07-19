"""DeterministicOpportunityScoringService — mvp-explainable-scoring-v1.

Contract: eight explainable dimensions, evidence-backed or unknown,
stable, bounded, and never fabricating data that doesn't exist.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.scoring import DEFAULT_DIMENSION_WEIGHTS, QualificationPolicy
from app.domain.services import OpportunityScoringInput
from app.domain.values import (
    DimensionAssessment,
    DimensionStatus,
    OpportunityAssessment,
    Priority,
    QualificationDecision,
    ScoringDimension,
    ScoringPolicy,
    SourceReference,
)
from app.services.scoring import SCORING_VERSION, DeterministicOpportunityScoringService

FIXED_AT = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)

RICH_SIGNALS = (
    "volume_trend: import shipments growing",
    "shipping: FCL ocean containers from CNSHA",
    "scale: 3 warehouse facilities",
    "value: high value cargo",
    "ops: cold chain required",
    "origin: china suppliers",
)


def make_input(
    *,
    website_host: str | None = "phg.com",
    verified: bool = True,
    signals: tuple[str, ...] = RICH_SIGNALS,
    sources: tuple[SourceReference, ...] | None = None,
) -> OpportunityScoringInput:
    if sources is None:
        sources = (
            SourceReference(
                source="importyeti", reference="https://ref/bol/1", retrieved_at=FIXED_AT
            ),
        )
    return OpportunityScoringInput(
        company_id=uuid4(),
        company_name="Pacific Home Goods Inc.",
        website_host=website_host,
        verified=verified,
        signals=signals,
        sources=sources,
        scoring_version=SCORING_VERSION,
        assessed_at=FIXED_AT,
    )


class TestDimensionalOutput:
    async def test_all_eight_dimensions_present(self) -> None:
        assessment = await DeterministicOpportunityScoringService().assess(make_input())
        assert assessment.score_breakdown is not None
        assert {d.dimension for d in assessment.score_breakdown.dimensions} == set(
            ScoringDimension
        )

    async def test_assessed_dimensions_all_carry_evidence(self) -> None:
        assessment = await DeterministicOpportunityScoringService().assess(make_input())
        assert assessment.score_breakdown is not None
        for dim in assessment.score_breakdown.dimensions:
            if dim.status is DimensionStatus.ASSESSED:
                assert dim.evidence, f"{dim.dimension} assessed without evidence"

    async def test_unmatched_dimensions_are_unknown_not_negative(self) -> None:
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=(), website_host=None)
        )
        assert assessment.score_breakdown is not None
        for dim in assessment.score_breakdown.dimensions:
            assert dim.status is DimensionStatus.UNKNOWN
            assert dim.earned_score == 0.0  # unknown earns zero, never subtracts
        assert assessment.new_score.value == 0.0
        assert assessment.data_completeness is not None
        assert assessment.data_completeness.value == 0.0

    async def test_no_sources_means_insufficient_evidence_everywhere(self) -> None:
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(sources=())
        )
        assert assessment.score_breakdown is not None
        assert all(
            d.status is DimensionStatus.INSUFFICIENT_EVIDENCE
            for d in assessment.score_breakdown.dimensions
        )
        assert assessment.qualification_decision is QualificationDecision.RESEARCH_MORE

    async def test_breakdown_totals_are_consistent(self) -> None:
        assessment = await DeterministicOpportunityScoringService().assess(make_input())
        breakdown = assessment.score_breakdown
        assert breakdown is not None
        assert breakdown.maximum_score == 100.0
        assert abs(
            breakdown.total_score - sum(d.earned_score for d in breakdown.dimensions)
        ) < 1e-6
        assert assessment.new_score.value == min(breakdown.total_score, 100.0)


class TestHonesty:
    async def test_no_fabrication_on_bare_input(self) -> None:
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=(), website_host=None, verified=False)
        )
        text = " ".join(assessment.reasons).lower()
        for fabrication in ("teu", "revenue", "import frequency"):
            assert fabrication not in text
        assert assessment.new_score.value == 0.0

    async def test_confidence_and_completeness_are_separate(self) -> None:
        service = DeterministicOpportunityScoringService()
        # trusted source but zero signals: decent confidence, zero completeness
        thin = await service.assess(make_input(signals=(), website_host=None))
        assert thin.confidence.value >= 0.5
        assert thin.data_completeness is not None and thin.data_completeness.value == 0.0
        # same source, rich signals: same confidence, high completeness
        rich = await service.assess(make_input())
        assert rich.confidence == thin.confidence
        assert rich.data_completeness is not None
        assert rich.data_completeness.value > 0.8


class TestDeterminism:
    async def test_same_input_same_assessment_and_fingerprint(self) -> None:
        service = DeterministicOpportunityScoringService()
        scoring_input = make_input()
        first = await service.assess(scoring_input)
        second = await service.assess(scoring_input)
        assert first == second
        assert first.assessment_fingerprint == second.assessment_fingerprint

    async def test_versions_are_stamped(self) -> None:
        service = DeterministicOpportunityScoringService()
        assessment = await service.assess(make_input())
        assert service.scoring_version == "mvp-explainable-scoring-v1"
        assert assessment.scoring_version == "mvp-explainable-scoring-v1"
        assert assessment.policy_version == "mvp-qualification-policy-v1"
        assert assessment.assessed_by == "DeterministicOpportunityScoringService"


class TestQualificationIntegration:
    async def test_rich_input_reaches_qualified(self) -> None:
        two_sources = (
            SourceReference(
                source="importyeti", reference="https://ref/bol/1", retrieved_at=FIXED_AT
            ),
            SourceReference(
                source="website", reference="https://phg.com/about", retrieved_at=FIXED_AT
            ),
        )
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(sources=two_sources)
        )
        # all 8 dimensions evidenced + two distinct sources (one trusted)
        assert assessment.new_score.value >= 70.0
        assert assessment.confidence.value >= 0.65
        assert assessment.qualification_decision is QualificationDecision.QUALIFIED
        assert assessment.recommended_action == "prepare_outreach"

    async def test_hard_gate_disqualifies_with_evidence(self) -> None:
        signals = (*RICH_SIGNALS, "non_us_target: HQ and operations in Canada only")
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals)
        )
        assert assessment.qualification_decision is QualificationDecision.DISQUALIFIED
        assert assessment.recommended_action == "do_not_contact"
        # scoring input preserved for audit: breakdown still complete
        assert assessment.score_breakdown is not None
        assert any("hard gate" in reason for reason in assessment.reasons)

    async def test_priority_comes_from_policy_not_value_object(self) -> None:
        scoring_input = make_input()
        default = await DeterministicOpportunityScoringService().assess(scoring_input)
        strict = await DeterministicOpportunityScoringService(
            priority_policy=ScoringPolicy(version=SCORING_VERSION, high_threshold=95.0)
        ).assess(scoring_input)
        assert default.new_score == strict.new_score
        assert default.priority is Priority.HIGH
        assert strict.priority is not Priority.HIGH


def _dimension(
    assessment: OpportunityAssessment, dimension: ScoringDimension
) -> DimensionAssessment:
    assert assessment.score_breakdown is not None
    return next(
        d for d in assessment.score_breakdown.dimensions if d.dimension is dimension
    )


class TestKindBasedDetection:
    """P0 fix: recognize a dimension from the structured signal kind, so
    non-English (e.g. Chinese) detail still scores; keyword search is only a
    fallback for legacy signals with no recognizable kind."""

    async def test_chinese_detail_with_kind_scores_via_kind(self) -> None:
        # These details carry NO English detector keyword — before the fix all
        # three were UNKNOWN; only the structured kind can match them now.
        signals = (
            "shipping_fit: 经常有DDP需求，没有固定货代",
            "company_scale: 员工人数在50人以上，规模中等",
            "logistics_complexity: 多供应商采购并向两个仓库补货",
        )
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals)
        )
        for dimension in (
            ScoringDimension.SHIPPING_FIT,
            ScoringDimension.COMPANY_SCALE,
            ScoringDimension.LOGISTICS_COMPLEXITY,
        ):
            dim = _dimension(assessment, dimension)
            assert dim.status is DimensionStatus.ASSESSED
            assert dim.earned_score > 0.0

    async def test_legacy_english_detail_without_kind_uses_keyword_fallback(self) -> None:
        # kind "note" is unknown → the English keywords in the detail still win.
        signals = ("note: FCL ocean containers from CNSHA suppliers",)
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals)
        )
        assert _dimension(assessment, ScoringDimension.SHIPPING_FIT).status is (
            DimensionStatus.ASSESSED
        )
        assert _dimension(assessment, ScoringDimension.CHINA_DEPENDENCY).status is (
            DimensionStatus.ASSESSED
        )

    async def test_cargo_value_alias_maps_to_cargo_value_potential(self) -> None:
        # Chinese detail with no keyword: only the alias can produce a score.
        signals = ("cargo_value: 货值较高的五金产品",)
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals)
        )
        dim = _dimension(assessment, ScoringDimension.CARGO_VALUE_POTENTIAL)
        assert dim.status is DimensionStatus.ASSESSED
        assert dim.earned_score == (
            DEFAULT_DIMENSION_WEIGHTS[ScoringDimension.CARGO_VALUE_POTENTIAL] * 0.6
        )

    async def test_growth_alias_maps_to_growth_signal(self) -> None:
        signals = ("growth: 最近在招聘新的采购，新开了仓库",)
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals)
        )
        assert _dimension(assessment, ScoringDimension.GROWTH_SIGNAL).status is (
            DimensionStatus.ASSESSED
        )

    async def test_complexity_alias_maps_to_logistics_complexity(self) -> None:
        # No hazmat/cold chain/oversized/multi-origin keyword: alias only.
        signals = ("complexity: 多供应商与多仓库补货协调",)
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals)
        )
        assert _dimension(assessment, ScoringDimension.LOGISTICS_COMPLEXITY).status is (
            DimensionStatus.ASSESSED
        )

    async def test_unknown_kind_does_not_score(self) -> None:
        signals = ("mystery_kind: 一些无法识别的中文描述",)
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals, website_host=None)
        )
        assert assessment.score_breakdown is not None
        for dim in assessment.score_breakdown.dimensions:
            assert dim.status is not DimensionStatus.ASSESSED
        assert assessment.new_score.value == 0.0

    async def test_pain_point_is_saved_but_not_scored(self) -> None:
        # pain_point is a legitimate signal kind but maps to no dimension and
        # adds no weight — it must never contribute to the score.
        signals = ("pain_point: 旺季舱位波动和到仓时间不稳定",)
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(signals=signals, website_host=None)
        )
        assert assessment.score_breakdown is not None
        for dim in assessment.score_breakdown.dimensions:
            assert dim.status is not DimensionStatus.ASSESSED
        assert assessment.new_score.value == 0.0

    async def test_chinese_signals_with_kinds_reach_qualified(self) -> None:
        # Regression mirror of the real JESKE data that previously capped at
        # REVIEW / 39.5 because its Chinese detail matched no English keyword.
        signals = (
            "import_activity: 存在整柜运输记录 最近进口频率上升",
            "china_dependency: 过去12个月有100次中国发货记录 主要进口五金",
            "shipping_fit: 经常有DDP需求，没有固定货代",
            "cargo_value: 货价单价高，一年内总进口金额约100万美金",
            "company_scale: 公司成立64年，员工人数在50人以上",
            "growth: 最近在招聘新的采购，新开了仓库，营业额翻倍",
            "logistics_complexity: 最近在扩大市场，有新的供应商和新的海运需求",
            "pain_point: 旺季舱位波动和到仓时间不稳定",
        )
        two_sources = (
            SourceReference(
                source="importyeti", reference="https://ref/bol/jeske", retrieved_at=FIXED_AT
            ),
            SourceReference(
                source="company_website",
                reference="https://jeskehardware.com/",
                retrieved_at=FIXED_AT,
            ),
        )
        assessment = await DeterministicOpportunityScoringService().assess(
            make_input(
                signals=signals, sources=two_sources, website_host="jeskehardware.com"
            )
        )
        assert assessment.new_score.value >= 70.0
        assert assessment.qualification_decision is QualificationDecision.QUALIFIED
        assert assessment.recommended_action == "prepare_outreach"


class TestWeightOwnership:
    def test_weights_live_in_policy_and_sum_to_100(self) -> None:
        assert sum(DEFAULT_DIMENSION_WEIGHTS.values()) == 100.0
        assert DEFAULT_DIMENSION_WEIGHTS[ScoringDimension.IMPORT_ACTIVITY] == 20.0
        assert DEFAULT_DIMENSION_WEIGHTS[ScoringDimension.CHINA_DEPENDENCY] == 15.0
        assert DEFAULT_DIMENSION_WEIGHTS[ScoringDimension.SHIPPING_FIT] == 15.0

    def test_qualification_thresholds_live_in_policy(self) -> None:
        policy = QualificationPolicy()
        assert policy.version == "mvp-qualification-policy-v1"
        assert policy.qualified_score == 70.0
        assert policy.qualified_confidence == 0.65
        assert policy.qualified_completeness == 0.50
