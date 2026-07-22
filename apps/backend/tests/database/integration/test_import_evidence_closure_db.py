"""Real PostgreSQL coverage for Stage 4A.4.2 persistence closure."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.database.mappers.import_evidence import (
    ImporterEvidenceAggregateMapper,
    ImportEvidenceQualityMapper,
)
from app.database.models.company import CompanyModel
from app.database.models.import_evidence import (
    ImporterEvidenceAggregateModel,
    ImporterEvidenceAggregateShipmentModel,
    ImportEvidenceJobModel,
    NormalizedShipmentModel,
)
from app.domain.import_evidence.models import QualityAssessment
from app.services.import_evidence.aggregate import AggregateShipmentInput
from app.services.import_evidence.persistence import ImportEvidenceQueryService
from app.services.import_evidence.quality import EvidenceQualityScorer
from app.workflows.import_evidence import (
    ImportEvidenceAggregateRequest,
    ImportEvidenceClosureWorkflow,
)
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_repositories import persist_company
from tests.database.integration.test_research_db import session_of

FIXED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 7, 21)


async def _persist_shipment(
    uow_factory: UowFactory,
    *,
    company_id: UUID,
    fingerprint: str,
    arrival: datetime = FIXED_AT,
    provider: str = "fake",
) -> UUID:
    job_id = uuid4()
    shipment_id = uuid4()
    async with uow_factory() as uow:
        session = session_of(uow)
        session.add(
            ImportEvidenceJobModel(
                id=job_id,
                company_id=company_id,
                provider_name=provider,
                status="completed",
                request_id=uuid4(),
                total_raw=1,
                total_normalized=1,
                total_deduped=1,
                total_matched=1,
                total_promoted=0,
                created_at=FIXED_AT,
                completed_at=FIXED_AT,
            )
        )
        session.add(
            NormalizedShipmentModel(
                id=shipment_id,
                job_id=job_id,
                importer_name="Pacific Home Goods Inc.",
                importer_address="1 Harbor Way, Long Beach, CA",
                normalized_importer="pacific home goods",
                shipper_name="Shenzhen Furniture Co.",
                shipper_country="CN",
                country_of_origin="CN",
                arrival_date=arrival,
                port_of_lading="YANTIAN",
                port_of_discharge="LONG BEACH",
                master_bol="MASTER-1",
                house_bol=f"HOUSE-{fingerprint[:6]}",
                carrier_scac="MAEU",
                vessel="TEST VESSEL",
                voyage="001E",
                container_numbers_json=["TCLU1234567"],
                weight_kg=1000.0,
                teu=1.0,
                hs_codes_json=["9403.50"],
                goods_description_raw="Furniture",
                goods_description_normalized="furniture",
                value_amount=None,
                value_type="unknown",
                provider=provider,
                provider_record_id=f"record-{fingerprint[:8]}",
                shipment_fingerprint=fingerprint,
                fingerprint_version="shipment-fp-v2",
                dedupe_status="ok",
                dedupe_method="fingerprint",
                dedupe_reasons=[],
                container_count=1,
                raw_weight=1000.0,
                raw_weight_unit="kg",
                normalized_weight=1000.0,
                normalized_weight_unit="kg",
                weight_scope="house",
                raw_quantity=None,
                normalized_quantity=None,
                parent_shipment_id=None,
                normalization_version="v1",
                created_at=FIXED_AT,
                raw_record_ids_json=[],
            )
        )
        await uow.commit()
    return shipment_id


def _assessment(
    shipment_id: UUID, fingerprint: str, *, two_sources: bool = False
) -> QualityAssessment:
    providers = ("fake", "csv") if two_sources else ("fake",)
    return EvidenceQualityScorer().assess(
        normalized_shipment_id=shipment_id,
        shipment_fingerprint=fingerprint,
        provider_names=providers,
        entity_match_status="auto_match",
        has_house_bol=True,
        has_importer=True,
        has_arrival_date=True,
        has_carrier_scac=True,
        has_containers=True,
        cross_source_agreement=1.0,
        arrival_date_value=AS_OF,
        now=AS_OF,
        assessed_at=FIXED_AT,
    )


def _aggregate_input(
    shipment_id: UUID,
    fingerprint: str,
    quality_id: UUID,
    quality_fingerprint: str,
) -> AggregateShipmentInput:
    return AggregateShipmentInput(
        normalized_shipment_id=shipment_id,
        shipment_fingerprint=fingerprint,
        quality_assessment_id=quality_id,
        quality_fingerprint=quality_fingerprint,
        quality_status="USABLE",
        entity_match_status="auto_match",
        importer_identity="Pacific Home Goods Inc.",
        arrival_date=AS_OF,
        origin="CN",
        supplier="Shenzhen Furniture Co.",
        containers=("TCLU1234567", "TCLU1234567"),
        weight_kg=1000.0,
        carrier="MAEU",
        port="LONG BEACH",
        source_provider_count=1,
        source_providers=("fake",),
    )


class TestQualityPersistence:
    async def test_reload_idempotency_and_version_replacement(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        shipment_fp = "1" * 64
        shipment_id = await _persist_shipment(
            uow_factory, company_id=company.id, fingerprint=shipment_fp
        )
        workflow = ImportEvidenceClosureWorkflow(uow_factory)
        first = _assessment(shipment_id, shipment_fp)

        created = await workflow.persist_quality(first)
        replay = await workflow.persist_quality(first)
        assert created.created is True
        assert replay.created is False

        async with uow_factory() as uow:
            query = ImportEvidenceQueryService(uow.import_evidence)
            loaded = await query.current_quality(shipment_id)
            history = await query.quality_history(shipment_id)
        assert loaded is not None
        assert loaded.id == first.id
        assert loaded.input_fingerprint == first.input_fingerprint
        assert len(history) == 1

        changed = _assessment(shipment_id, shipment_fp, two_sources=True)
        replaced = await workflow.persist_quality(changed)
        assert replaced.created is True
        async with uow_factory() as uow:
            query = ImportEvidenceQueryService(uow.import_evidence)
            current = await query.current_quality(shipment_id)
            history = await query.quality_history(shipment_id)
        assert current is not None and current.id == changed.id
        assert len(history) == 2
        historical = next(row for row in history if row.id == first.id)
        assert historical.is_current is False
        assert historical.superseded_at is not None

        reactivated = await workflow.persist_quality(first)
        assert reactivated.created is False
        async with uow_factory() as uow:
            query = ImportEvidenceQueryService(uow.import_evidence)
            current = await query.current_quality(shipment_id)
            history = await query.quality_history(shipment_id)
        assert current is not None and current.id == first.id
        assert len(history) == 2

    async def test_database_allows_only_one_current_assessment(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        shipment_id = await _persist_shipment(
            uow_factory, company_id=company.id, fingerprint="2" * 64
        )
        first = _assessment(shipment_id, "2" * 64)
        await ImportEvidenceClosureWorkflow(uow_factory).persist_quality(first)
        async with uow_factory() as uow:
            session = session_of(uow)
            duplicate_current = replace(
                first,
                id=uuid4(),
                input_fingerprint="9" * 64,
            )
            session.add(ImportEvidenceQualityMapper.to_model(duplicate_current))
            with pytest.raises(IntegrityError):
                await session.flush()


class TestAggregatePersistence:
    async def test_reload_inclusion_idempotency_and_history(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        workflow = ImportEvidenceClosureWorkflow(uow_factory)
        first_fp = "3" * 64
        first_id = await _persist_shipment(uow_factory, company_id=company.id, fingerprint=first_fp)
        first_quality = _assessment(first_id, first_fp)
        await workflow.persist_quality(first_quality)
        first_input = _aggregate_input(
            first_id, first_fp, first_quality.id, first_quality.input_fingerprint
        )
        request = ImportEvidenceAggregateRequest(
            importer_identity="Pacific Home Goods Inc.",
            company_id=company.id,
            shipments=(
                first_input,
                replace(first_input, source_providers=("csv",)),
            ),
            as_of_date=AS_OF,
        )

        created = await workflow.build_and_persist_aggregate(request)
        replay = await workflow.build_and_persist_aggregate(request)
        assert created.created is True
        assert replay.created is False
        assert replay.aggregate.id == created.aggregate.id

        async with uow_factory() as uow:
            query = ImportEvidenceQueryService(uow.import_evidence)
            loaded = await query.aggregate_by_id(created.aggregate.id)
            inclusions = await query.aggregate_shipments(created.aggregate.id)
        assert loaded is not None
        assert loaded.id == created.aggregate.id
        assert loaded.promotable is True
        assert len(inclusions) == 1
        assert inclusions[0].quality_assessment_id == first_quality.id
        assert inclusions[0].source_provider_count == 2

        second_fp = "4" * 64
        second_id = await _persist_shipment(
            uow_factory, company_id=company.id, fingerprint=second_fp
        )
        second_quality = _assessment(second_id, second_fp)
        await workflow.persist_quality(second_quality)
        second_input = _aggregate_input(
            second_id, second_fp, second_quality.id, second_quality.input_fingerprint
        )
        changed = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=(first_input, second_input),
                as_of_date=AS_OF,
            )
        )
        assert changed.created is True
        assert changed.aggregate.input_fingerprint != created.aggregate.input_fingerprint

        async with uow_factory() as uow:
            query = ImportEvidenceQueryService(uow.import_evidence)
            current = await query.current_aggregate("PACIFIC HOME GOODS, INC.", 365)
            history = await query.aggregate_history("PACIFIC HOME GOODS, INC.", 365)
        assert current is not None and current.id == changed.aggregate.id
        assert len(history) == 2
        historical = next(row for row in history if row.id == created.aggregate.id)
        assert historical.is_current is False
        assert historical.superseded_at is not None
        assert len(historical.inclusions) == 1

        changed_quality = _assessment(first_id, first_fp, two_sources=True)
        await workflow.persist_quality(changed_quality)
        quality_changed_input = replace(
            first_input,
            quality_assessment_id=changed_quality.id,
            quality_fingerprint=changed_quality.input_fingerprint,
        )
        quality_changed = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=(quality_changed_input, second_input),
                as_of_date=AS_OF,
            )
        )
        assert quality_changed.created is True
        async with uow_factory() as uow:
            history = await uow.import_evidence.list_aggregate_history(
                "pacific home goods inc", 365
            )
        assert len(history) == 3
        assert sum(1 for row in history if row.is_current) == 1

        hydrated_replay = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=(first_input, second_input),
                as_of_date=AS_OF,
            )
        )
        assert hydrated_replay.created is False
        assert hydrated_replay.aggregate.id == quality_changed.aggregate.id

    async def test_company_delete_cascades_aggregate_without_orphans(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        shipment_fp = "5" * 64
        shipment_id = await _persist_shipment(
            uow_factory, company_id=company.id, fingerprint=shipment_fp
        )
        quality = _assessment(shipment_id, shipment_fp)
        workflow = ImportEvidenceClosureWorkflow(uow_factory)
        await workflow.persist_quality(quality)
        aggregate = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=(
                    _aggregate_input(
                        shipment_id,
                        shipment_fp,
                        quality.id,
                        quality.input_fingerprint,
                    ),
                ),
                as_of_date=AS_OF,
            )
        )
        async with uow_factory() as uow:
            session = session_of(uow)
            await session.execute(delete(CompanyModel).where(CompanyModel.id == company.id))
            await uow.commit()
        async with uow_factory() as uow:
            session = session_of(uow)
            aggregate_count = await session.scalar(
                select(func.count()).select_from(ImporterEvidenceAggregateModel)
            )
            inclusion_count = await session.scalar(
                select(func.count()).select_from(ImporterEvidenceAggregateShipmentModel)
            )
            loaded = await uow.import_evidence.get_aggregate_by_id(aggregate.aggregate.id)
        assert aggregate_count == 0
        assert inclusion_count == 0
        assert loaded is None

    async def test_database_allows_only_one_current_aggregate(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        shipment_id = await _persist_shipment(
            uow_factory, company_id=company.id, fingerprint="6" * 64
        )
        quality = _assessment(shipment_id, "6" * 64)
        workflow = ImportEvidenceClosureWorkflow(uow_factory)
        await workflow.persist_quality(quality)
        saved = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=(
                    _aggregate_input(shipment_id, "6" * 64, quality.id, quality.input_fingerprint),
                ),
                as_of_date=AS_OF,
            )
        )
        async with uow_factory() as uow:
            duplicate = replace(
                saved.aggregate,
                id=uuid4(),
                input_fingerprint="7" * 64,
            )
            session_of(uow).add(ImporterEvidenceAggregateMapper.to_model(duplicate))
            with pytest.raises(IntegrityError):
                await session_of(uow).flush()

    async def test_temporal_container_and_order_boundaries_survive_reload(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        workflow = ImportEvidenceClosureWorkflow(uow_factory)
        current_start = AS_OF - timedelta(days=364)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=364)
        business_dates = (
            AS_OF,
            AS_OF - timedelta(days=89),
            current_start,
            previous_end,
            previous_start,
            previous_start - timedelta(days=1),
        )
        inputs: list[AggregateShipmentInput] = []
        for index, business_date in enumerate(business_dates):
            fingerprint = f"{index + 1:x}" * 64
            shipment_id = await _persist_shipment(
                uow_factory,
                company_id=company.id,
                fingerprint=fingerprint,
                arrival=datetime.combine(business_date, time(23, 30), tzinfo=UTC),
            )
            quality = _assessment(shipment_id, fingerprint)
            await workflow.persist_quality(quality)
            inputs.append(
                replace(
                    _aggregate_input(
                        shipment_id,
                        fingerprint,
                        quality.id,
                        quality.input_fingerprint,
                    ),
                    arrival_date=business_date,
                    containers=("TCLU-1234567", "TCLU1234567"),
                )
            )

        forward = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=tuple(inputs),
                as_of_date=AS_OF,
            )
        )
        reverse = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=tuple(reversed(inputs)),
                as_of_date=AS_OF,
            )
        )
        assert reverse.created is False
        assert reverse.aggregate.id == forward.aggregate.id
        async with uow_factory() as uow:
            loaded = await uow.import_evidence.get_aggregate_by_id(forward.aggregate.id)
        assert loaded is not None
        assert loaded.shipment_count_90d == 2
        assert loaded.shipment_count_365d == 3
        assert loaded.shipment_count_previous_365d == 2
        assert loaded.shipment_count_730d == 5
        assert loaded.total_container_count == 6

    async def test_entity_boundaries_are_persisted_without_promotion_eligibility(
        self, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        workflow = ImportEvidenceClosureWorkflow(uow_factory)
        inputs: list[AggregateShipmentInput] = []
        for index in range(3):
            fingerprint = f"{index + 10:x}" * 64
            shipment_id = await _persist_shipment(
                uow_factory,
                company_id=company.id,
                fingerprint=fingerprint,
            )
            quality = _assessment(shipment_id, fingerprint)
            await workflow.persist_quality(quality)
            inputs.append(
                _aggregate_input(
                    shipment_id,
                    fingerprint,
                    quality.id,
                    quality.input_fingerprint,
                )
            )

        unresolved = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=None,
                shipments=(inputs[0],),
                as_of_date=AS_OF,
            )
        )
        assert unresolved.aggregate.promotable is False

        blocked = await workflow.build_and_persist_aggregate(
            ImportEvidenceAggregateRequest(
                importer_identity="Pacific Home Goods Inc.",
                company_id=company.id,
                shipments=(
                    replace(inputs[1], entity_match_status="rejected"),
                    replace(inputs[2], entity_match_status="separate"),
                ),
                as_of_date=AS_OF,
            )
        )
        assert blocked.aggregate.promotable is False
        assert blocked.aggregate.status.value == "BLOCKED"
        assert blocked.aggregate.trusted_shipment_count == 0
