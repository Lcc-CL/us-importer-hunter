"""SQLAlchemy repository for D2a prospect batches."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import ProspectBatchMapper
from app.database.models.prospect_batch import ProspectBatchCompanyModel, ProspectBatchModel
from app.domain.prospect_batch import ProspectBatch, ProspectBatchCompanyStatus


class SqlAlchemyProspectBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, batch_id: UUID) -> ProspectBatch | None:
        model = await self._session.get(ProspectBatchModel, batch_id)
        return ProspectBatchMapper.to_domain(model) if model else None

    async def get_by_id_for_update(self, batch_id: UUID) -> ProspectBatch | None:
        model = await self._session.scalar(
            select(ProspectBatchModel)
            .where(ProspectBatchModel.id == batch_id)
            .with_for_update()
        )
        return ProspectBatchMapper.to_domain(model) if model else None

    async def add(self, batch: ProspectBatch) -> None:
        self._session.add(ProspectBatchMapper.to_model(batch))

    async def save(self, batch: ProspectBatch) -> None:
        await self._session.merge(ProspectBatchMapper.to_model(batch))

    async def find_for_routing_selection(
        self,
        *,
        routing_run_id: UUID,
        routing_selection_hash: str,
    ) -> ProspectBatch | None:
        model = await self._session.scalar(
            select(ProspectBatchModel).where(
                ProspectBatchModel.routing_run_id == routing_run_id,
                ProspectBatchModel.routing_selection_hash == routing_selection_hash,
            )
        )
        return ProspectBatchMapper.to_domain(model) if model else None

    async def has_completed_pipeline(
        self,
        *,
        discovery_task_id: UUID,
        company_id: UUID,
        pipeline_version: str,
        exclude_batch_id: UUID | None = None,
    ) -> bool:
        query = (
            select(ProspectBatchCompanyModel.company_id)
            .join(
                ProspectBatchModel,
                ProspectBatchModel.id == ProspectBatchCompanyModel.batch_id,
            )
            .where(
                ProspectBatchModel.discovery_task_id == discovery_task_id,
                ProspectBatchCompanyModel.company_id == company_id,
                ProspectBatchCompanyModel.pipeline_version == pipeline_version,
                ProspectBatchCompanyModel.status == ProspectBatchCompanyStatus.COMPLETED.value,
            )
            .limit(1)
        )
        if exclude_batch_id is not None:
            query = query.where(ProspectBatchCompanyModel.batch_id != exclude_batch_id)
        return (await self._session.scalar(query)) is not None
