"""Read-only query service for Import Evidence promotion state."""

from collections.abc import Callable
from uuid import UUID

from app.domain.import_evidence.models import ImportEvidenceSignalPromotion
from app.domain.repositories import ImportEvidenceUnitOfWork


class ImportEvidencePromotionQueryService:
    def __init__(self, uow_factory: Callable[[], ImportEvidenceUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def current(self, company_id: UUID) -> tuple[ImportEvidenceSignalPromotion, ...]:
        async with self._uow_factory() as uow:
            return tuple(await uow.import_evidence_promotions.list_current_promotions(company_id))

    async def history(
        self, *, company_id: UUID | None = None, aggregate_id: UUID | None = None
    ) -> tuple[ImportEvidenceSignalPromotion, ...]:
        async with self._uow_factory() as uow:
            return tuple(
                await uow.import_evidence_promotions.list_promotion_history(
                    company_id=company_id, aggregate_id=aggregate_id
                )
            )

    async def reload(self, promotion_id: UUID) -> ImportEvidenceSignalPromotion | None:
        async with self._uow_factory() as uow:
            return await uow.import_evidence_promotions.get_promotion_by_id(promotion_id)
