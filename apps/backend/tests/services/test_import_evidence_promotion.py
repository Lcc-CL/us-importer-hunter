"""Deterministic Stage 4A.4.3 promotion policy and fake ledger lifecycle."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.import_evidence.models import (
    AggregateStatus,
    ImporterEvidenceAggregate,
    ImportEvidenceCompanySignal,
    ImportEvidenceScoringProjection,
    InclusionStatus,
    PromotionStatus,
    QualityAssessment,
    QualityStatus,
    ShipmentInclusion,
    SignalPromotionCandidate,
)
from app.domain.values import SourceReference
from app.services.import_evidence.fake_promotion_repository import (
    FakeImportEvidencePromotionRepository,
)
from app.services.import_evidence.promotion import PromotionEligibilityPolicy
from app.services.scoring.evidence_merge import ScoringEvidenceMergePolicy

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
COMPANY_ID = uuid4()


def _quality(
    shipment_id: UUID,
    *,
    status: QualityStatus = QualityStatus.VERIFIED,
    score: float = 90.0,
) -> QualityAssessment:
    return QualityAssessment(
        normalized_shipment_id=shipment_id,
        total_score=score,
        quality_status=status,
        input_fingerprint=f"quality-{shipment_id}",
        assessed_at=NOW,
        created_at=NOW,
    )


def _aggregate(
    *,
    status: AggregateStatus = AggregateStatus.READY,
    company_id: UUID | None = COMPANY_ID,
    promotable: bool = True,
    fingerprint: str = "aggregate-fingerprint",
    qualities: tuple[QualityAssessment, ...] | None = None,
) -> tuple[ImporterEvidenceAggregate, tuple[QualityAssessment, ...]]:
    rows = qualities or tuple(_quality(uuid4()) for _ in range(4))
    inclusions = tuple(
        ShipmentInclusion(
            normalized_shipment_id=quality.normalized_shipment_id or uuid4(),
            quality_assessment_id=quality.id,
            shipment_fingerprint=f"shipment-{index}",
            inclusion_status=InclusionStatus.TRUSTED,
            inclusion_reason="quality_trusted",
            source_provider_count=2,
            created_at=NOW,
        )
        for index, quality in enumerate(rows)
    )
    return (
        ImporterEvidenceAggregate(
            company_id=company_id,
            importer_identity="acme imports",
            status=status,
            promotable=promotable,
            input_fingerprint=fingerprint,
            as_of_date=date(2026, 7, 21),
            source_provider_count=2,
            trusted_shipment_count=4,
            verified_shipment_count=sum(
                quality.quality_status is QualityStatus.VERIFIED for quality in rows
            ),
            usable_shipment_count=sum(
                quality.quality_status is QualityStatus.USABLE for quality in rows
            ),
            active_month_count=4,
            unique_supplier_count=4,
            unique_destination_port_count=2,
            unique_carrier_count=2,
            known_origin_shipment_count=3,
            china_origin_shipment_count=2,
            unknown_origin_shipment_count=1,
            total_container_count=4,
            shipment_count_90d=2,
            shipment_count_365d=4,
            shipment_count_730d=4,
            shipment_count_previous_365d=2,
            trend_candidate="increasing",
            inclusions=inclusions,
            created_at=NOW,
        ),
        rows,
    )


class TestPromotionPolicy:
    def test_ready_verified_generates_supported_candidates(self) -> None:
        aggregate, qualities = _aggregate()
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        assert {
            row.signal_kind for row in candidates if row.status is PromotionStatus.CANDIDATE
        } == {
            "import_activity",
            "china_dependency",
            "logistics_complexity",
        }
        assert all(row.quality_status is QualityStatus.VERIFIED for row in candidates)
        assert all(str(aggregate.id) in row.signal_detail for row in candidates)

    def test_usable_is_eligible_and_preserves_conservative_score(self) -> None:
        shipment_id = uuid4()
        aggregate, qualities = _aggregate(
            qualities=(_quality(shipment_id, status=QualityStatus.USABLE, score=72.0),)
        )
        aggregate = replace(
            aggregate,
            trusted_shipment_count=1,
            shipment_count_90d=1,
            shipment_count_365d=1,
            verified_shipment_count=0,
            usable_shipment_count=1,
            known_origin_shipment_count=0,
            china_origin_shipment_count=0,
        )
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        assert all(row.quality_status is QualityStatus.USABLE for row in candidates)
        assert all(row.quality_score == 72.0 for row in candidates)

    @pytest.mark.parametrize("quality_status", [QualityStatus.REVIEW, QualityStatus.REJECTED])
    def test_review_and_rejected_never_become_candidates(
        self, quality_status: QualityStatus
    ) -> None:
        aggregate, qualities = _aggregate(
            qualities=(_quality(uuid4(), status=quality_status, score=40.0),)
        )
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        assert all(row.status is PromotionStatus.BLOCKED for row in candidates)

    @pytest.mark.parametrize(
        ("status", "promotable", "expected"),
        [
            (AggregateStatus.PARTIAL, True, PromotionStatus.CANDIDATE),
            (AggregateStatus.INSUFFICIENT_DATA, False, PromotionStatus.SKIPPED),
            (AggregateStatus.BLOCKED, False, PromotionStatus.BLOCKED),
        ],
    )
    def test_aggregate_status_is_applied_before_dimension_rules(
        self,
        status: AggregateStatus,
        promotable: bool,
        expected: PromotionStatus,
    ) -> None:
        aggregate, qualities = _aggregate(status=status, promotable=promotable)
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        if status is AggregateStatus.PARTIAL:
            assert candidates[0].status is expected
        else:
            assert all(row.status is expected for row in candidates)

    @pytest.mark.parametrize("boundary", ["company", "fingerprint", "current"])
    def test_unresolved_missing_fingerprint_and_historical_are_blocked(self, boundary: str) -> None:
        aggregate, qualities = _aggregate()
        if boundary == "company":
            aggregate = replace(aggregate, company_id=None)
        elif boundary == "fingerprint":
            aggregate = replace(aggregate, input_fingerprint="")
        else:
            aggregate = replace(aggregate, is_current=False)
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        assert all(row.status is PromotionStatus.BLOCKED for row in candidates)

    def test_unknown_origin_is_excluded_from_china_denominator(self) -> None:
        aggregate, qualities = _aggregate()
        candidate = next(
            row
            for row in PromotionEligibilityPolicy().preview(aggregate, qualities)
            if row.signal_kind == "china_dependency"
        )
        assert candidate.normalized_value_json["china_ratio"] == pytest.approx(2 / 3)
        assert candidate.normalized_value_json["known_origin_shipment_count"] == 3
        assert candidate.normalized_value_json["unknown_origin_shipment_count"] == 1

    def test_no_known_origin_skips_china_and_never_creates_cargo_value(self) -> None:
        aggregate, qualities = _aggregate()
        aggregate = replace(
            aggregate,
            known_origin_shipment_count=0,
            china_origin_shipment_count=0,
            unknown_origin_shipment_count=4,
        )
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        china = next(row for row in candidates if row.signal_kind == "china_dependency")
        assert china.status is PromotionStatus.SKIPPED
        assert china.normalized_value_json["china_ratio"] is None
        assert "cargo_value_potential" not in {row.signal_kind for row in candidates}

    def test_partial_promotes_only_dimension_with_sufficient_evidence(self) -> None:
        aggregate, qualities = _aggregate(status=AggregateStatus.PARTIAL)
        aggregate = replace(
            aggregate,
            known_origin_shipment_count=0,
            china_origin_shipment_count=0,
            unknown_origin_shipment_count=4,
            unique_supplier_count=1,
            unique_carrier_count=1,
            unique_destination_port_count=1,
            total_container_count=0,
            active_month_count=1,
        )
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        assert [
            row.signal_kind for row in candidates if row.status is PromotionStatus.CANDIDATE
        ] == ["import_activity"]

    def test_single_historical_shipment_does_not_prove_import_activity(self) -> None:
        aggregate, qualities = _aggregate(qualities=(_quality(uuid4()),))
        aggregate = replace(
            aggregate,
            trusted_shipment_count=1,
            verified_shipment_count=1,
            shipment_count_90d=0,
            shipment_count_365d=1,
            shipment_count_730d=1,
        )
        candidate = PromotionEligibilityPolicy().preview(aggregate, qualities)[0]
        assert candidate.signal_kind == "import_activity"
        assert candidate.status is PromotionStatus.SKIPPED

    def test_blocker_and_untraceable_quality_block_every_dimension(self) -> None:
        aggregate, qualities = _aggregate()
        aggregate = replace(
            aggregate,
            blocking_reasons=("future_arrival_date",),
            inclusions=(replace(aggregate.inclusions[0], quality_assessment_id=uuid4()),),
        )
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        assert all(row.status is PromotionStatus.BLOCKED for row in candidates)
        assert all("quality_assessment_untraceable" in row.rejection_reasons for row in candidates)

    def test_historical_quality_assessment_blocks_every_dimension(self) -> None:
        quality = replace(_quality(uuid4()), is_current=False)
        aggregate, qualities = _aggregate(qualities=(quality,))
        candidates = PromotionEligibilityPolicy().preview(aggregate, qualities)
        assert all(row.status is PromotionStatus.BLOCKED for row in candidates)
        assert all("quality_assessment_not_current" in row.rejection_reasons for row in candidates)

    def test_forward_reverse_inclusion_order_has_same_candidate_fingerprints(self) -> None:
        aggregate, qualities = _aggregate()
        reverse = replace(aggregate, inclusions=tuple(reversed(aggregate.inclusions)))
        policy = PromotionEligibilityPolicy()
        assert [row.input_fingerprint for row in policy.preview(aggregate, qualities)] == [
            row.input_fingerprint for row in policy.preview(reverse, tuple(reversed(qualities)))
        ]


class TestFakeRepositoryLifecycle:
    async def test_idempotent_and_superseded_lifecycle(self) -> None:
        aggregate, qualities = _aggregate()
        candidates = tuple(
            replace(row, status=PromotionStatus.PROMOTED)
            if row.status is PromotionStatus.CANDIDATE
            else row
            for row in PromotionEligibilityPolicy().preview(aggregate, qualities)
        )
        repository = FakeImportEvidencePromotionRepository(qualities)
        first, created = await repository.apply_candidates(candidates)
        replay, replay_created = await repository.apply_candidates(candidates)
        assert created is True and replay_created is False
        assert [row.id for row in replay] == [row.id for row in first]
        assert len(await repository.list_active_signals(COMPANY_ID)) == 3

        changed = tuple(
            replace(
                row,
                aggregate_id=uuid4(),
                input_fingerprint=f"changed-{row.signal_kind}",
                signal_detail=f"changed {row.signal_kind}",
            )
            for row in candidates
        )
        second, second_created = await repository.apply_candidates(changed)
        assert second_created is True
        assert len(await repository.list_current_promotions(COMPANY_ID)) == 3
        assert len(await repository.list_promotion_history(company_id=COMPANY_ID)) == 6
        history = await repository.list_promotion_history(company_id=COMPANY_ID)
        old_ids = {row.id for row in first}
        assert all(row.status is PromotionStatus.SUPERSEDED for row in history if row.id in old_ids)
        assert all(row.is_current for row in second)


class TestEvidenceMergePolicy:
    def test_manual_wins_same_kind_and_dimension_is_emitted_once(self) -> None:
        aggregate, qualities = _aggregate()
        candidate = PromotionEligibilityPolicy().preview(aggregate, qualities)[0]
        signal = _projected(candidate)
        source = SourceReference(source="manual", reference="urn:manual:1", retrieved_at=NOW)
        merged = ScoringEvidenceMergePolicy().merge(
            company_signals=("import_activity: human confirmed import activity",),
            company_sources=(source,),
            import_projection=ImportEvidenceScoringProjection(signals=(signal,)),
        )
        assert merged.signals == ("import_activity: human confirmed import activity",)
        assert len([row for row in merged.signals if row.startswith("import_activity:")]) == 1
        assert any("manual_or_existing" in reason for reason in merged.selection_reasons)

    def test_verified_import_evidence_wins_same_kind_research_once(self) -> None:
        aggregate, qualities = _aggregate()
        candidate = PromotionEligibilityPolicy().preview(aggregate, qualities)[0]
        signal = _projected(candidate)
        research = "import_activity: website statement"
        merged = ScoringEvidenceMergePolicy().merge(
            company_signals=(research,),
            company_sources=(),
            import_projection=ImportEvidenceScoringProjection(
                signals=(signal,),
                research_signals=(research,),
            ),
        )
        assert merged.signals == (signal.rendered_signal,)
        assert any("selected import_evidence" in reason for reason in merged.selection_reasons)


def _projected(candidate: SignalPromotionCandidate) -> ImportEvidenceCompanySignal:
    return ImportEvidenceCompanySignal(
        promotion_id=uuid4(),
        aggregate_id=candidate.aggregate_id,
        company_id=candidate.company_id,
        signal_kind=candidate.signal_kind,
        signal_detail=candidate.signal_detail,
        normalized_value_json=candidate.normalized_value_json,
        provenance_json={},
        quality_status=QualityStatus.VERIFIED,
        quality_score=90.0,
        created_at=NOW,
    )
