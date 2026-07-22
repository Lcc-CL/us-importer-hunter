"""SQLAlchemy persistence for versioned import-evidence records."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.import_evidence import (
    ImporterEvidenceAggregateMapper,
    ImportEvidenceQualityMapper,
)
from app.database.models.import_evidence import (
    ImporterEntityMatchModel,
    ImporterEvidenceAggregateModel,
    ImporterEvidenceAggregateShipmentModel,
    ImportEvidenceJobModel,
    ImportEvidenceQualityAssessmentModel,
    ImportEvidenceRawRecordModel,
    NormalizedShipmentModel,
)
from app.domain.import_evidence.models import (
    ImporterEvidenceAggregate,
    QualityAssessment,
    ShipmentInclusion,
)
from app.domain.import_evidence.values import (
    ImporterEntityMatch,
    NormalizedShipment,
    RawImportRecord,
)
from app.services.import_evidence.entity_resolver import normalize_company_name


class SqlAlchemyImportEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_quality_assessment(
        self, assessment: QualityAssessment
    ) -> tuple[QualityAssessment, bool]:
        if assessment.normalized_shipment_id is None:
            raise ValueError("quality assessment requires normalized_shipment_id")
        existing_result = await self._session.execute(
            select(ImportEvidenceQualityAssessmentModel).where(
                ImportEvidenceQualityAssessmentModel.normalized_shipment_id
                == assessment.normalized_shipment_id,
                ImportEvidenceQualityAssessmentModel.input_fingerprint
                == assessment.input_fingerprint,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if not existing.is_current:
                await self._supersede_current_quality(assessment.normalized_shipment_id)
                existing.is_current = True
                existing.superseded_at = None
            return ImportEvidenceQualityMapper.to_domain(existing), False

        await self._supersede_current_quality(assessment.normalized_shipment_id)
        self._session.add(ImportEvidenceQualityMapper.to_model(assessment))
        return assessment, True

    async def _supersede_current_quality(self, normalized_shipment_id: UUID) -> None:
        await self._session.execute(
            update(ImportEvidenceQualityAssessmentModel)
            .where(
                ImportEvidenceQualityAssessmentModel.normalized_shipment_id
                == normalized_shipment_id,
                ImportEvidenceQualityAssessmentModel.is_current.is_(True),
            )
            .values(is_current=False, superseded_at=datetime.now(UTC))
        )

    async def get_current_quality_assessment(
        self, normalized_shipment_id: UUID
    ) -> QualityAssessment | None:
        result = await self._session.execute(
            select(ImportEvidenceQualityAssessmentModel).where(
                ImportEvidenceQualityAssessmentModel.normalized_shipment_id
                == normalized_shipment_id,
                ImportEvidenceQualityAssessmentModel.is_current.is_(True),
            )
        )
        model = result.scalar_one_or_none()
        return ImportEvidenceQualityMapper.to_domain(model) if model else None

    async def list_quality_assessment_history(
        self, normalized_shipment_id: UUID
    ) -> list[QualityAssessment]:
        result = await self._session.execute(
            select(ImportEvidenceQualityAssessmentModel)
            .where(
                ImportEvidenceQualityAssessmentModel.normalized_shipment_id
                == normalized_shipment_id
            )
            .order_by(ImportEvidenceQualityAssessmentModel.assessed_at.desc())
        )
        return [ImportEvidenceQualityMapper.to_domain(model) for model in result.scalars()]

    async def save_aggregate(
        self, aggregate: ImporterEvidenceAggregate
    ) -> tuple[ImporterEvidenceAggregate, bool]:
        existing_result = await self._session.execute(
            select(ImporterEvidenceAggregateModel).where(
                ImporterEvidenceAggregateModel.importer_identity == aggregate.importer_identity,
                ImporterEvidenceAggregateModel.window_days == aggregate.window_days,
                ImporterEvidenceAggregateModel.as_of_date == aggregate.as_of_date,
                ImporterEvidenceAggregateModel.input_fingerprint == aggregate.input_fingerprint,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if not existing.is_current:
                await self._supersede_current_aggregate(
                    aggregate.importer_identity, aggregate.window_days
                )
                existing.is_current = True
                existing.superseded_at = None
            return await self._to_aggregate(existing), False

        await self._supersede_current_aggregate(aggregate.importer_identity, aggregate.window_days)
        self._session.add(ImporterEvidenceAggregateMapper.to_model(aggregate))
        for inclusion in aggregate.inclusions:
            self._session.add(
                ImporterEvidenceAggregateMapper.inclusion_to_model(aggregate.id, inclusion)
            )
        return aggregate, True

    async def _supersede_current_aggregate(self, importer_identity: str, window_days: int) -> None:
        await self._session.execute(
            update(ImporterEvidenceAggregateModel)
            .where(
                ImporterEvidenceAggregateModel.importer_identity == importer_identity,
                ImporterEvidenceAggregateModel.window_days == window_days,
                ImporterEvidenceAggregateModel.is_current.is_(True),
            )
            .values(is_current=False, superseded_at=datetime.now(UTC))
        )

    async def get_aggregate_by_id(self, aggregate_id: UUID) -> ImporterEvidenceAggregate | None:
        model = await self._session.get(ImporterEvidenceAggregateModel, aggregate_id)
        return await self._to_aggregate(model) if model else None

    async def get_current_aggregate(
        self, importer_identity: str, window_days: int
    ) -> ImporterEvidenceAggregate | None:
        result = await self._session.execute(
            select(ImporterEvidenceAggregateModel).where(
                ImporterEvidenceAggregateModel.importer_identity == importer_identity,
                ImporterEvidenceAggregateModel.window_days == window_days,
                ImporterEvidenceAggregateModel.is_current.is_(True),
            )
        )
        model = result.scalar_one_or_none()
        return await self._to_aggregate(model) if model else None

    async def list_aggregate_history(
        self, importer_identity: str, window_days: int
    ) -> list[ImporterEvidenceAggregate]:
        result = await self._session.execute(
            select(ImporterEvidenceAggregateModel)
            .where(
                ImporterEvidenceAggregateModel.importer_identity == importer_identity,
                ImporterEvidenceAggregateModel.window_days == window_days,
            )
            .order_by(ImporterEvidenceAggregateModel.created_at.desc())
        )
        return [await self._to_aggregate(model) for model in result.scalars()]

    async def list_aggregate_shipments(self, aggregate_id: UUID) -> list[ShipmentInclusion]:
        rows = await self._inclusion_models(aggregate_id)
        return [ImporterEvidenceAggregateMapper.inclusion_to_domain(row) for row in rows]

    async def create_upload_job(
        self, company_id: UUID, provider_name: str, request_id: UUID
    ) -> UUID:
        job_id = uuid4()
        self._session.add(
            ImportEvidenceJobModel(
                id=job_id,
                company_id=company_id,
                provider_name=provider_name,
                status="running",
                request_id=request_id,
                total_raw=0,
                total_normalized=0,
                total_deduped=0,
                total_matched=0,
                total_promoted=0,
                error_message=None,
                created_at=datetime.now(UTC),
                completed_at=None,
            )
        )
        return job_id

    async def save_upload_record(self, job_id: UUID, record: RawImportRecord) -> UUID:
        result = await self._session.execute(
            select(ImportEvidenceRawRecordModel).where(
                ImportEvidenceRawRecordModel.provider == record.provider,
                ImportEvidenceRawRecordModel.provider_record_id == record.provider_record_id,
                ImportEvidenceRawRecordModel.raw_payload_hash == record.raw_payload_hash,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing.id
        record_id = uuid4()
        self._session.add(
            ImportEvidenceRawRecordModel(
                id=record_id,
                job_id=job_id,
                provider=record.provider,
                provider_record_id=record.provider_record_id,
                request_id=record.request_id,
                raw_payload_json=record.raw_payload_json,
                raw_payload_hash=record.raw_payload_hash,
                fetched_at=record.fetched_at,
                provider_updated_at=record.provider_updated_at,
                schema_version=record.schema_version,
                fixture=record.fixture,
                synthetic=record.synthetic,
            )
        )
        return record_id

    async def save_normalized_shipment(
        self, job_id: UUID, shipment: NormalizedShipment, raw_record_id: UUID
    ) -> tuple[UUID, bool]:
        result = await self._session.execute(
            select(NormalizedShipmentModel).where(
                NormalizedShipmentModel.shipment_fingerprint == shipment.shipment_fingerprint
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            raw_ids = list(existing.raw_record_ids_json or ())
            if str(raw_record_id) not in raw_ids:
                raw_ids.append(str(raw_record_id))
                existing.raw_record_ids_json = raw_ids
            return existing.id, False

        self._session.add(
            NormalizedShipmentModel(
                id=shipment.id,
                job_id=job_id,
                importer_name=shipment.importer_name,
                importer_address=shipment.importer_address,
                normalized_importer=normalize_company_name(shipment.importer_name),
                shipper_name=shipment.shipper_name,
                shipper_country=shipment.shipper_country,
                country_of_origin=shipment.country_of_origin,
                arrival_date=shipment.arrival_date,
                port_of_lading=shipment.port_of_lading,
                port_of_discharge=shipment.port_of_discharge,
                master_bol=shipment.master_bol,
                house_bol=shipment.house_bol,
                carrier_scac=shipment.carrier_scac,
                vessel=shipment.vessel,
                voyage=shipment.voyage,
                container_numbers_json=list(shipment.container_numbers),
                weight_kg=shipment.weight_kg,
                teu=shipment.teu,
                hs_codes_json=list(shipment.hs_codes),
                goods_description_raw=shipment.goods_description_raw,
                goods_description_normalized=shipment.goods_description_normalized,
                value_amount=shipment.value_amount,
                value_type=shipment.value_type.value,
                provider=shipment.provider,
                provider_record_id=shipment.provider_record_id,
                shipment_fingerprint=shipment.shipment_fingerprint,
                fingerprint_version=shipment.fingerprint_version,
                dedupe_status=shipment.dedupe_status,
                dedupe_method=shipment.dedupe_method,
                dedupe_reasons=list(shipment.dedupe_reasons),
                container_count=shipment.container_count,
                raw_weight=shipment.raw_weight,
                raw_weight_unit=shipment.raw_weight_unit,
                normalized_weight=shipment.normalized_weight,
                normalized_weight_unit=shipment.normalized_weight_unit,
                weight_scope=shipment.weight_scope,
                raw_quantity=shipment.raw_quantity,
                normalized_quantity=shipment.normalized_quantity,
                parent_shipment_id=shipment.parent_shipment_id,
                normalization_version=shipment.normalization_version,
                created_at=datetime.now(UTC),
                raw_record_ids_json=[str(raw_record_id)],
            )
        )
        return shipment.id, True

    async def save_entity_match(self, shipment_id: UUID, match: ImporterEntityMatch) -> None:
        result = await self._session.execute(
            select(ImporterEntityMatchModel.id).where(
                ImporterEntityMatchModel.shipment_id == shipment_id,
                ImporterEntityMatchModel.company_id == match.company_id,
                ImporterEntityMatchModel.review_status == match.review_status.value,
            )
        )
        if result.scalar_one_or_none() is not None:
            return
        self._session.add(
            ImporterEntityMatchModel(
                id=match.id,
                shipment_id=shipment_id,
                company_id=match.company_id,
                normalized_name=match.normalized_name,
                match_method=match.match_method.value,
                match_score=match.match_score,
                match_reasons_json=list(match.match_reasons),
                candidate_company_ids_json=[str(value) for value in match.candidate_company_ids],
                review_status=match.review_status.value,
                reviewed_by=match.reviewed_by,
                reviewed_at=match.reviewed_at,
                created_at=datetime.now(UTC),
            )
        )

    async def finish_upload_job(
        self,
        job_id: UUID,
        *,
        status: str,
        total_raw: int,
        total_normalized: int,
        total_deduped: int,
        total_matched: int,
        total_promoted: int,
        error_message: str | None = None,
    ) -> None:
        job = await self._session.get(ImportEvidenceJobModel, job_id)
        if job is None:
            raise ValueError(f"import evidence job not found: {job_id}")
        job.status = status
        job.total_raw = total_raw
        job.total_normalized = total_normalized
        job.total_deduped = total_deduped
        job.total_matched = total_matched
        job.total_promoted = total_promoted
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)

    async def get_latest_upload_job(
        self, company_id: UUID
    ) -> tuple[UUID, str, int, int, int, int, int] | None:
        result = await self._session.execute(
            select(ImportEvidenceJobModel)
            .where(ImportEvidenceJobModel.company_id == company_id)
            .order_by(ImportEvidenceJobModel.created_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        return (
            job.id,
            job.status,
            job.total_raw,
            job.total_normalized,
            job.total_deduped,
            job.total_matched,
            job.total_promoted,
        )

    async def get_current_aggregate_for_company(
        self, company_id: UUID
    ) -> ImporterEvidenceAggregate | None:
        result = await self._session.execute(
            select(ImporterEvidenceAggregateModel)
            .where(
                ImporterEvidenceAggregateModel.company_id == company_id,
                ImporterEvidenceAggregateModel.is_current.is_(True),
            )
            .order_by(ImporterEvidenceAggregateModel.created_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return await self._to_aggregate(model) if model else None

    async def _to_aggregate(
        self, model: ImporterEvidenceAggregateModel
    ) -> ImporterEvidenceAggregate:
        rows = await self._inclusion_models(model.id)
        return ImporterEvidenceAggregateMapper.to_domain(model, rows)

    async def _inclusion_models(
        self, aggregate_id: UUID
    ) -> list[ImporterEvidenceAggregateShipmentModel]:
        result = await self._session.execute(
            select(ImporterEvidenceAggregateShipmentModel)
            .where(ImporterEvidenceAggregateShipmentModel.aggregate_id == aggregate_id)
            .order_by(ImporterEvidenceAggregateShipmentModel.shipment_fingerprint)
        )
        return list(result.scalars())
