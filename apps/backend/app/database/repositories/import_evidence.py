"""SQLAlchemy persistence for versioned import-evidence records."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.import_evidence import (
    ImporterEvidenceAggregateMapper,
    ImportEvidenceQualityMapper,
)
from app.database.models.import_evidence import (
    ImporterEvidenceAggregateModel,
    ImporterEvidenceAggregateShipmentModel,
    ImportEvidenceQualityAssessmentModel,
)
from app.domain.import_evidence.models import (
    ImporterEvidenceAggregate,
    QualityAssessment,
    ShipmentInclusion,
)


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
