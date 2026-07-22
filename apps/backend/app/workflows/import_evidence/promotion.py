"""Application orchestration for deterministic Import Evidence promotion."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from uuid import UUID

from app.domain.events import CompanyFactsChanged
from app.domain.import_evidence.models import (
    ImporterEvidenceAggregate,
    ImportEvidenceSignalPromotion,
    InclusionStatus,
    PromotionStatus,
    QualityAssessment,
    SignalPromotionCandidate,
)
from app.domain.repositories import ImportEvidenceUnitOfWork
from app.services.import_evidence.promotion import PromotionEligibilityPolicy
from app.services.import_evidence.promotion_query import (
    ImportEvidencePromotionQueryService,
)
from app.workflows.opportunity.workflow import (
    OpportunityApplicationWorkflow,
    OpportunityProcessingOutcome,
)


@dataclass(frozen=True)
class PromotionBatchOutcome:
    aggregate_id: UUID
    candidates: tuple[SignalPromotionCandidate, ...]
    promotions: tuple[ImportEvidenceSignalPromotion, ...]
    created: bool


class ImportEvidenceSignalPromotionWorkflow:
    def __init__(
        self,
        uow_factory: Callable[[], ImportEvidenceUnitOfWork],
        policy: PromotionEligibilityPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy or PromotionEligibilityPolicy()
        self._queries = ImportEvidencePromotionQueryService(uow_factory)

    async def preview_candidates(self, aggregate_id: UUID) -> tuple[SignalPromotionCandidate, ...]:
        async with self._uow_factory() as uow:
            aggregate = await uow.import_evidence.get_aggregate_by_id(aggregate_id)
            if aggregate is None:
                raise ValueError(f"aggregate not found: {aggregate_id}")
            return self._policy.preview(aggregate, await self._qualities(uow, aggregate))

    async def promote(self, aggregate_id: UUID) -> PromotionBatchOutcome:
        async with self._uow_factory() as uow:
            aggregate = await uow.import_evidence.get_aggregate_by_id(aggregate_id)
            if aggregate is None:
                raise ValueError(f"aggregate not found: {aggregate_id}")
            candidates = self._policy.preview(aggregate, await self._qualities(uow, aggregate))
            if aggregate.company_id is None or not aggregate.is_current:
                return PromotionBatchOutcome(aggregate.id, candidates, (), False)
            decisions = tuple(
                replace(candidate, status=PromotionStatus.PROMOTED)
                if candidate.status is PromotionStatus.CANDIDATE
                else candidate
                for candidate in candidates
            )
            promotions, created = await uow.import_evidence_promotions.apply_candidates(decisions)
            await uow.commit()
            return PromotionBatchOutcome(aggregate.id, candidates, tuple(promotions), created)

    async def get_current_promotions(
        self, company_id: UUID
    ) -> tuple[ImportEvidenceSignalPromotion, ...]:
        return await self._queries.current(company_id)

    async def get_promotion_history(
        self, *, company_id: UUID | None = None, aggregate_id: UUID | None = None
    ) -> tuple[ImportEvidenceSignalPromotion, ...]:
        return await self._queries.history(company_id=company_id, aggregate_id=aggregate_id)

    async def reload_promotion(self, promotion_id: UUID) -> ImportEvidenceSignalPromotion | None:
        return await self._queries.reload(promotion_id)

    @staticmethod
    async def rerun_qualification(
        company_id: UUID,
        *,
        user_id: UUID,
        workflow: OpportunityApplicationWorkflow,
    ) -> OpportunityProcessingOutcome:
        return await workflow.handle(
            CompanyFactsChanged(
                company_id=company_id,
                changed_fields=("import_evidence_signals",),
                reason="current Import Evidence signal projection changed",
            ),
            user_id=user_id,
        )

    @staticmethod
    async def _qualities(
        uow: ImportEvidenceUnitOfWork,
        aggregate: ImporterEvidenceAggregate,
    ) -> list[QualityAssessment]:
        quality_ids = tuple(
            sorted(
                {
                    inclusion.quality_assessment_id
                    for inclusion in aggregate.inclusions
                    if inclusion.quality_assessment_id is not None
                    and inclusion.inclusion_status
                    in (InclusionStatus.TRUSTED, InclusionStatus.UNDATED)
                },
                key=str,
            )
        )
        return await uow.import_evidence_promotions.get_quality_assessments(quality_ids)
