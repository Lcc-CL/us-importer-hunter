"""Application orchestration for Stage 4A.4.2 persistence closure."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

from app.domain.import_evidence.models import QualityAssessment
from app.domain.repositories import ImportEvidenceUnitOfWork
from app.services.import_evidence.aggregate import (
    AGGREGATE_RULE_VERSION,
    AggregateShipmentInput,
    compute_aggregate,
)
from app.services.import_evidence.persistence import (
    AggregatePersistenceResult,
    ImportEvidencePersistenceService,
    QualityPersistenceResult,
)


@dataclass(frozen=True)
class ImportEvidenceAggregateRequest:
    importer_identity: str
    shipments: tuple[AggregateShipmentInput, ...]
    company_id: UUID | None = None
    as_of_date: date | None = None
    window_days: int = 365
    previous_window_days: int = 365
    rule_version: str = AGGREGATE_RULE_VERSION

    def __post_init__(self) -> None:
        if not self.importer_identity.strip():
            raise ValueError("importer_identity is required for stable persistence")


class ImportEvidenceClosureWorkflow:
    def __init__(self, uow_factory: Callable[[], ImportEvidenceUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def persist_quality(self, assessment: QualityAssessment) -> QualityPersistenceResult:
        async with self._uow_factory() as uow:
            service = ImportEvidencePersistenceService(uow.import_evidence)
            outcome = await service.save_quality_assessment(assessment)
            await uow.commit()
            return outcome

    async def build_and_persist_aggregate(
        self, request: ImportEvidenceAggregateRequest
    ) -> AggregatePersistenceResult:
        async with self._uow_factory() as uow:
            current_inputs: list[AggregateShipmentInput] = []
            for shipment in request.shipments:
                current_quality = await uow.import_evidence.get_current_quality_assessment(
                    shipment.normalized_shipment_id
                )
                if current_quality is None:
                    raise ValueError("aggregate requires a persisted current quality assessment")
                current_inputs.append(
                    replace(
                        shipment,
                        quality_assessment_id=current_quality.id,
                        quality_fingerprint=current_quality.input_fingerprint,
                        quality_status=current_quality.quality_status.value,
                        quality_hard_blockers=current_quality.hard_blockers,
                    )
                )
            aggregate = compute_aggregate(
                company_id=request.company_id,
                importer_identity=request.importer_identity,
                shipments=current_inputs,
                as_of_date=request.as_of_date,
                window_days=request.window_days,
                previous_window_days=request.previous_window_days,
                rule_version=request.rule_version,
            )
            service = ImportEvidencePersistenceService(uow.import_evidence)
            outcome = await service.save_aggregate(aggregate)
            await uow.commit()
            return outcome
