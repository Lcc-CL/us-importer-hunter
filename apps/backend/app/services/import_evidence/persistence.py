"""Application services for import-evidence persistence and queries."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.import_evidence.models import (
    ImporterEvidenceAggregate,
    QualityAssessment,
    ShipmentInclusion,
)
from app.domain.repositories import ImportEvidenceRepository
from app.services.import_evidence.aggregate import normalize_importer_identity


@dataclass(frozen=True)
class QualityPersistenceResult:
    assessment: QualityAssessment
    created: bool


@dataclass(frozen=True)
class AggregatePersistenceResult:
    aggregate: ImporterEvidenceAggregate
    created: bool


class ImportEvidencePersistenceService:
    def __init__(self, repository: ImportEvidenceRepository) -> None:
        self._repository = repository

    async def save_quality_assessment(
        self, assessment: QualityAssessment
    ) -> QualityPersistenceResult:
        saved, created = await self._repository.save_quality_assessment(assessment)
        return QualityPersistenceResult(assessment=saved, created=created)

    async def save_aggregate(
        self, aggregate: ImporterEvidenceAggregate
    ) -> AggregatePersistenceResult:
        saved, created = await self._repository.save_aggregate(aggregate)
        return AggregatePersistenceResult(aggregate=saved, created=created)


class ImportEvidenceQueryService:
    def __init__(self, repository: ImportEvidenceRepository) -> None:
        self._repository = repository

    async def current_quality(self, normalized_shipment_id: UUID) -> QualityAssessment | None:
        return await self._repository.get_current_quality_assessment(normalized_shipment_id)

    async def quality_history(self, normalized_shipment_id: UUID) -> list[QualityAssessment]:
        return await self._repository.list_quality_assessment_history(normalized_shipment_id)

    async def aggregate_by_id(self, aggregate_id: UUID) -> ImporterEvidenceAggregate | None:
        return await self._repository.get_aggregate_by_id(aggregate_id)

    async def current_aggregate(
        self, importer_identity: str, window_days: int = 365
    ) -> ImporterEvidenceAggregate | None:
        return await self._repository.get_current_aggregate(
            normalize_importer_identity(importer_identity), window_days
        )

    async def aggregate_history(
        self, importer_identity: str, window_days: int = 365
    ) -> list[ImporterEvidenceAggregate]:
        return await self._repository.list_aggregate_history(
            normalize_importer_identity(importer_identity), window_days
        )

    async def aggregate_shipments(self, aggregate_id: UUID) -> list[ShipmentInclusion]:
        return await self._repository.list_aggregate_shipments(aggregate_id)
