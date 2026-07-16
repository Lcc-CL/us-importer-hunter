"""DeterministicOpportunityScoringService — mvp-deterministic-v1.

Placeholder scorer contract: stable, bounded, explainable, traceable,
and it never invents data it doesn't have.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.services import OpportunityScoringInput
from app.domain.values import Priority, ScoringPolicy, SourceReference
from app.services.scoring import (
    SCORING_VERSION,
    DeterministicOpportunityScoringService,
    DeterministicScoringWeights,
)

FIXED_AT = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def make_input(
    *,
    website_host: str | None = "phg.com",
    verified: bool = True,
    signals: tuple[str, ...] = ("volume_trend: import volume growing",),
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


class TestDeterminism:
    async def test_same_input_same_assessment(self) -> None:
        service = DeterministicOpportunityScoringService()
        scoring_input = make_input()
        first = await service.assess(scoring_input)
        second = await service.assess(scoring_input)
        assert first == second

    async def test_scoring_version_and_assessed_by(self) -> None:
        service = DeterministicOpportunityScoringService()
        assert service.scoring_version == "mvp-deterministic-v1"
        assessment = await service.assess(make_input())
        assert assessment.scoring_version == "mvp-deterministic-v1"
        assert assessment.assessed_by == "DeterministicOpportunityScoringService"


class TestBounds:
    async def test_score_capped_at_100_with_extreme_weights(self) -> None:
        service = DeterministicOpportunityScoringService(
            weights=DeterministicScoringWeights(base=90.0, website_bonus=50.0)
        )
        assessment = await service.assess(make_input())
        assert 0.0 <= assessment.new_score.value <= 100.0

    async def test_confidence_within_unit_interval(self) -> None:
        service = DeterministicOpportunityScoringService()
        many_sources = tuple(
            SourceReference(source=f"s{i}", reference=f"https://r/{i}", retrieved_at=FIXED_AT)
            for i in range(20)
        )
        rich = await service.assess(make_input(sources=many_sources))
        poor = await service.assess(make_input(sources=()))
        assert 0.0 <= poor.confidence.value <= rich.confidence.value <= 1.0


class TestExplainability:
    async def test_reasons_never_empty_even_on_bare_input(self) -> None:
        service = DeterministicOpportunityScoringService()
        assessment = await service.assess(
            make_input(website_host=None, verified=False, signals=(), sources=())
        )
        assert assessment.reasons

    async def test_evidence_traceable_to_sources(self) -> None:
        service = DeterministicOpportunityScoringService()
        assessment = await service.assess(make_input())
        assert len(assessment.evidence) == 1
        assert assessment.evidence[0].sources[0].source == "importyeti"

    async def test_no_fabrication_on_bare_input(self) -> None:
        """No website, no signals, no sources → exactly the baseline score,
        no invented import volume / cargo value / dependency claims."""
        service = DeterministicOpportunityScoringService()
        assessment = await service.assess(
            make_input(website_host=None, verified=False, signals=(), sources=())
        )
        assert assessment.new_score.value == DeterministicScoringWeights().base
        assert assessment.evidence == ()
        text = " ".join(assessment.reasons).lower()
        for fabrication in ("teu", "cargo value", "china dependency"):
            assert fabrication not in text


class TestRules:
    async def test_bonuses_accumulate(self) -> None:
        service = DeterministicOpportunityScoringService()
        weights = DeterministicScoringWeights()
        bare = await service.assess(
            make_input(website_host=None, verified=False, signals=(), sources=())
        )
        full = await service.assess(
            make_input(signals=("import shipments detected", "volume growing"))
        )
        expected = (
            weights.base
            + weights.website_bonus
            + weights.verified_bonus
            + weights.import_signal_bonus
            + weights.growth_signal_bonus
        )
        assert bare.new_score.value == weights.base
        assert full.new_score.value == expected

    async def test_trusted_source_lifts_confidence(self) -> None:
        service = DeterministicOpportunityScoringService()
        trusted = await service.assess(make_input())
        untrusted = await service.assess(
            make_input(
                sources=(
                    SourceReference(
                        source="random-blog", reference="https://r/x", retrieved_at=FIXED_AT
                    ),
                )
            )
        )
        assert trusted.confidence.value > untrusted.confidence.value


class TestPriorityOwnership:
    async def test_priority_decided_by_policy_not_value_object(self) -> None:
        """The same score maps to different priorities under different
        policies — proof the threshold lives in the policy, not the VO."""
        default_service = DeterministicOpportunityScoringService()
        strict_service = DeterministicOpportunityScoringService(
            policy=ScoringPolicy(version=SCORING_VERSION, high_threshold=95.0)
        )
        scoring_input = make_input(signals=("import shipments", "growing volume"))
        default_assessment = await default_service.assess(scoring_input)
        strict_assessment = await strict_service.assess(scoring_input)
        assert default_assessment.new_score == strict_assessment.new_score
        assert default_assessment.priority is Priority.HIGH
        assert strict_assessment.priority is not Priority.HIGH
