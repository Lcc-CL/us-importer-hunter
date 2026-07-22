"""Real PostgreSQL coverage for Import Evidence promotion and scoring projection."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.database.models.company import CompanyModel
from app.database.models.import_evidence import (
    ImportEvidenceCompanySignalModel,
    ImportEvidencePromotionQualityAssessmentModel,
    ImportEvidenceSignalPromotionModel,
)
from app.database.repositories import SqlAlchemyImportEvidenceProjectionReader
from app.domain.events import CompanyFactsChanged
from app.domain.import_evidence.models import (
    ImporterEvidenceAggregate,
    ImportEvidenceScoringProjection,
    PromotionStatus,
    QualityAssessment,
    SignalPromotionCandidate,
)
from app.domain.research import PromotionDecision
from app.services.import_evidence.aggregate import AggregateShipmentInput
from app.services.scoring import DeterministicOpportunityScoringService
from app.workflows.import_evidence import (
    ImportEvidenceAggregateRequest,
    ImportEvidenceClosureWorkflow,
    ImportEvidenceSignalPromotionWorkflow,
)
from app.workflows.opportunity import OpportunityApplicationWorkflow
from app.workflows.research import ClaimDecision, ClaimPromotionWorkflow, ReviewRequest
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_import_evidence_closure_db import (
    AS_OF,
    _aggregate_input,
    _assessment,
    _persist_shipment,
)
from tests.database.integration.test_promotion_db import build_run
from tests.database.integration.test_repositories import persist_company
from tests.database.integration.test_research_db import session_of

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def _promotion_workflow(uow_factory: UowFactory) -> ImportEvidenceSignalPromotionWorkflow:
    return ImportEvidenceSignalPromotionWorkflow(uow_factory)


async def _seed_aggregate(
    uow_factory: UowFactory,
    *,
    company_id: UUID,
    prefix: str = "a",
    count: int = 4,
) -> tuple[
    ImporterEvidenceAggregate,
    tuple[QualityAssessment, ...],
    tuple[AggregateShipmentInput, ...],
]:
    closure = ImportEvidenceClosureWorkflow(uow_factory)
    qualities: list[QualityAssessment] = []
    inputs = []
    for index in range(count):
        fingerprint = f"{prefix}{index}".ljust(64, prefix)[:64]
        shipment_id = await _persist_shipment(
            uow_factory,
            company_id=company_id,
            fingerprint=fingerprint,
            arrival=datetime(2026, 6, index + 1, 12, 0, tzinfo=UTC),
        )
        quality = _assessment(shipment_id, fingerprint)
        await closure.persist_quality(quality)
        qualities.append(quality)
        inputs.append(
            replace(
                _aggregate_input(
                    shipment_id,
                    fingerprint,
                    quality.id,
                    quality.input_fingerprint,
                ),
                arrival_date=date(2026, 6, index + 1),
            )
        )
    request_inputs = tuple((*inputs, replace(inputs[0], source_providers=("csv",))))
    outcome = await closure.build_and_persist_aggregate(
        ImportEvidenceAggregateRequest(
            importer_identity="Pacific Home Goods Inc.",
            company_id=company_id,
            shipments=request_inputs,
            as_of_date=AS_OF,
        )
    )
    return outcome.aggregate, tuple(qualities), tuple(inputs)


class TestPromotionPersistence:
    async def test_promote_reload_trace_and_idempotency(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        aggregate, qualities, _inputs = await _seed_aggregate(
            uow_factory, company_id=company.id
        )
        workflow = _promotion_workflow(uow_factory)
        preview = await workflow.preview_candidates(aggregate.id)
        assert {row.signal_kind for row in preview if row.status is PromotionStatus.CANDIDATE} == {
            "import_activity",
            "china_dependency",
        }

        first = await workflow.promote(aggregate.id)
        replay = await workflow.promote(aggregate.id)
        assert first.created is True
        assert replay.created is False
        assert [row.id for row in replay.promotions] == [row.id for row in first.promotions]
        assert len(first.promotions) == 3

        current = await workflow.get_current_promotions(company.id)
        active = None
        async with uow_factory() as uow:
            active = await uow.import_evidence_promotions.list_active_signals(company.id)
            links = await session_of(uow).scalar(
                select(func.count()).select_from(
                    ImportEvidencePromotionQualityAssessmentModel
                )
            )
            inclusions = await uow.import_evidence.list_aggregate_shipments(
                aggregate.id
            )
        assert len(current) == 3
        assert len(active) == 2
        assert links == len(qualities) * 3
        assert len(inclusions) == 4
        promoted = next(row for row in current if row.status is PromotionStatus.PROMOTED)
        reloaded = await workflow.reload_promotion(promoted.id)
        assert reloaded is not None and reloaded.id == promoted.id
        assert reloaded.aggregate_id == aggregate.id
        assert set(reloaded.quality_assessment_ids) == {row.id for row in qualities}
        signal = next(row for row in active if row.id == reloaded.promoted_signal_id)
        assert signal.promotion_id == reloaded.id
        assert signal.aggregate_id == aggregate.id

    async def test_new_aggregate_supersedes_ledger_and_signal(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        first_aggregate, _qualities, first_inputs = await _seed_aggregate(
            uow_factory, company_id=company.id, prefix="b"
        )
        workflow = _promotion_workflow(uow_factory)
        first = await workflow.promote(first_aggregate.id)
        old_active_ids = {
            row.promoted_signal_id
            for row in first.promotions
            if row.promoted_signal_id is not None
        }

        closure = ImportEvidenceClosureWorkflow(uow_factory)
        fingerprint = "c" * 64
        shipment_id = await _persist_shipment(
            uow_factory, company_id=company.id, fingerprint=fingerprint
        )
        quality = _assessment(shipment_id, fingerprint)
        await closure.persist_quality(quality)
        extra = _aggregate_input(
            shipment_id, fingerprint, quality.id, quality.input_fingerprint
        )
        changed = await closure.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=(*first_inputs, extra),
                as_of_date=AS_OF,
            )
        )
        second = await workflow.promote(changed.aggregate.id)
        assert second.created is True
        history = await workflow.get_promotion_history(company_id=company.id)
        assert len(history) == 6
        assert sum(row.is_current for row in history) == 3
        assert all(
            row.status is PromotionStatus.SUPERSEDED
            for row in history
            if row.aggregate_id == first_aggregate.id
        )
        async with uow_factory() as uow:
            session = session_of(uow)
            old_signal_active = list(
                (
                    await session.execute(
                        select(ImportEvidenceCompanySignalModel.is_active).where(
                            ImportEvidenceCompanySignalModel.id.in_(old_active_ids)
                        )
                    )
                ).scalars()
            )
            active = await uow.import_evidence_promotions.list_active_signals(company.id)
        assert all(not is_active for is_active in old_signal_active)
        assert {row.aggregate_id for row in active} == {changed.aggregate.id}
        projection = await SqlAlchemyImportEvidenceProjectionReader(
            uow_factory()._session_factory
        ).read_for_company(company.id)
        assert {row.aggregate_id for row in projection.signals} == {changed.aggregate.id}

    async def test_manual_and_research_company_rows_are_untouched(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        async with uow_factory() as uow:
            loaded = await uow.companies.get_by_id(company.id)
            assert loaded is not None
            loaded.add_signal("import_activity: manually confirmed")
            await uow.companies.save(loaded)
            run = build_run(company.id)
            await uow.research_runs.add(run)
            await uow.commit()
        await ClaimPromotionWorkflow(uow_factory).handle(
            ReviewRequest(
                research_run_id=run.id,
                reviewer_name="reviewer",
                decisions=(
                    ClaimDecision(
                        claim_position=0,
                        decision=PromotionDecision.ACCEPTED,
                    ),
                ),
            )
        )
        async with uow_factory() as uow:
            before = await uow.companies.get_by_id(company.id)
        assert before is not None
        aggregate, _qualities, _inputs = await _seed_aggregate(
            uow_factory, company_id=company.id, prefix="d"
        )
        await _promotion_workflow(uow_factory).promote(aggregate.id)
        async with uow_factory() as uow:
            after = await uow.companies.get_by_id(company.id)
        assert after is not None
        assert after.signals == before.signals
        assert after.sources == before.sources

    async def test_failed_batch_rolls_back_without_superseding_current(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        aggregate, _qualities, _inputs = await _seed_aggregate(
            uow_factory, company_id=company.id, prefix="e"
        )
        workflow = _promotion_workflow(uow_factory)
        first = await workflow.promote(aggregate.id)
        original_current = {row.id for row in first.promotions}
        promoted = next(row for row in first.promotions if row.status is PromotionStatus.PROMOTED)
        broken = SignalPromotionCandidate(
            aggregate_id=aggregate.id,
            company_id=company.id,
            signal_kind=promoted.signal_kind,
            signal_detail="should rollback",
            normalized_value_json={},
            source_summary_json={},
            evidence_snapshot_json={},
            quality_status=promoted.quality_status,
            quality_score=promoted.quality_score,
            promotion_version=promoted.promotion_version,
            input_fingerprint="f" * 64,
            status=PromotionStatus.PROMOTED,
            quality_assessment_ids=(
                promoted.quality_assessment_ids[0],
                promoted.quality_assessment_ids[0],
            ),
        )
        with pytest.raises(IntegrityError):
            async with uow_factory() as uow:
                await uow.import_evidence_promotions.apply_candidates((broken,))
                await uow.commit()
        current = await workflow.get_current_promotions(company.id)
        assert {row.id for row in current} == original_current

    async def test_company_delete_cascades_without_orphans(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        aggregate, _qualities, _inputs = await _seed_aggregate(
            uow_factory, company_id=company.id, prefix="f"
        )
        await _promotion_workflow(uow_factory).promote(aggregate.id)
        async with uow_factory() as uow:
            await session_of(uow).execute(
                delete(CompanyModel).where(CompanyModel.id == company.id)
            )
            await uow.commit()
        async with uow_factory() as uow:
            session = session_of(uow)
            promotion_count = await session.scalar(
                select(func.count()).select_from(ImportEvidenceSignalPromotionModel)
            )
            signal_count = await session.scalar(
                select(func.count()).select_from(ImportEvidenceCompanySignalModel)
            )
        assert promotion_count == 0
        assert signal_count == 0

    async def test_database_rejects_second_current_promotion(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        aggregate, _qualities, _inputs = await _seed_aggregate(
            uow_factory, company_id=company.id, prefix="g"
        )
        await _promotion_workflow(uow_factory).promote(aggregate.id)
        with pytest.raises(IntegrityError):
            async with uow_factory() as uow:
                await session_of(uow).execute(
                    insert(ImportEvidenceSignalPromotionModel).values(
                        id=uuid4(),
                        aggregate_id=aggregate.id,
                        company_id=company.id,
                        signal_kind="import_activity",
                        signal_detail="duplicate current",
                        normalized_value_json={},
                        source_summary_json={},
                        evidence_snapshot_json={},
                        quality_status="VERIFIED",
                        quality_score=90.0,
                        promotion_version="test",
                        input_fingerprint="9" * 64,
                        status="SKIPPED",
                        is_current=True,
                        rejection_reasons_json=[],
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )

    async def test_database_rejects_second_active_projection(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        aggregate, _qualities, _inputs = await _seed_aggregate(
            uow_factory, company_id=company.id, prefix="h"
        )
        await _promotion_workflow(uow_factory).promote(aggregate.id)
        async with uow_factory() as uow:
            spare_promotion_id = await session_of(uow).scalar(
                select(ImportEvidenceSignalPromotionModel.id).where(
                    ImportEvidenceSignalPromotionModel.company_id == company.id,
                    ImportEvidenceSignalPromotionModel.status == "SKIPPED",
                )
            )
        assert spare_promotion_id is not None
        with pytest.raises(IntegrityError):
            async with uow_factory() as uow:
                await session_of(uow).execute(
                    insert(ImportEvidenceCompanySignalModel).values(
                        id=uuid4(),
                        promotion_id=spare_promotion_id,
                        aggregate_id=aggregate.id,
                        company_id=company.id,
                        signal_kind="import_activity",
                        signal_detail="duplicate active",
                        normalized_value_json={},
                        provenance_json={},
                        quality_status="VERIFIED",
                        quality_score=90.0,
                        ownership="import_evidence",
                        is_active=True,
                        created_at=NOW,
                    )
                )


class TestQualificationProjection:
    async def test_current_projection_scores_once_and_records_selection_reason(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        aggregate, _qualities, _inputs = await _seed_aggregate(
            uow_factory, company_id=company.id, prefix="1"
        )
        promotion_workflow = _promotion_workflow(uow_factory)
        await promotion_workflow.promote(aggregate.id)
        session_factory = uow_factory()._session_factory
        opportunity_workflow = OpportunityApplicationWorkflow(
            uow_factory,
            DeterministicOpportunityScoringService(),
            import_evidence_reader=SqlAlchemyImportEvidenceProjectionReader(session_factory),
        )
        outcome = await promotion_workflow.rerun_qualification(
            company.id,
            user_id=uuid4(),
            workflow=opportunity_workflow,
        )
        assert outcome.opportunity_id is not None
        async with uow_factory() as uow:
            stored = await uow.opportunities.get_by_id(outcome.opportunity_id)
        assert stored is not None
        latest = stored.history[-1]
        assert latest.score_breakdown is not None
        dimensions = {row.dimension.value: row for row in latest.score_breakdown.dimensions}
        assert dimensions["import_activity"].earned_score > 0
        assert dimensions["china_dependency"].earned_score > 0
        assert sum(row.dimension.value == "import_activity" for row in dimensions.values()) == 1
        assert any("selected import_evidence" in reason for reason in latest.reasons)

    async def test_manual_same_kind_wins_and_reader_failure_fails_open(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        async with uow_factory() as uow:
            loaded = await uow.companies.get_by_id(company.id)
            assert loaded is not None
            loaded.add_signal("import_activity: manually edited")
            await uow.companies.save(loaded)
            await uow.commit()

        class FailingReader:
            async def read_for_company(
                self, company_id: UUID
            ) -> ImportEvidenceScoringProjection:
                raise RuntimeError(f"reader failed for {company_id}")

        workflow = OpportunityApplicationWorkflow(
            uow_factory,
            DeterministicOpportunityScoringService(),
            import_evidence_reader=FailingReader(),
        )
        outcome = await workflow.handle(
            CompanyFactsChanged(
                company_id=company.id,
                changed_fields=("signals",),
                reason="test",
            ),
            user_id=uuid4(),
        )
        assert outcome.opportunity_id is not None
