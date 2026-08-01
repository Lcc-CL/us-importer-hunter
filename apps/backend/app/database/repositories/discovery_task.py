"""SQLAlchemy repository for persisted discovery tasks."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import DiscoveryTaskMapper
from app.database.models.discovery_task import DiscoveryTaskModel
from app.domain.discovery import DiscoveryTask


class SqlAlchemyDiscoveryTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, task_id: UUID) -> DiscoveryTask | None:
        model = await self._session.get(DiscoveryTaskModel, task_id)
        return DiscoveryTaskMapper.to_domain(model) if model else None

    async def add(self, task: DiscoveryTask) -> None:
        self._session.add(DiscoveryTaskMapper.to_model(task))

    async def save(self, task: DiscoveryTask) -> None:
        await self._session.merge(DiscoveryTaskMapper.to_model(task))
