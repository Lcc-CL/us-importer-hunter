"""Task repository (SQLAlchemy implementation of the domain protocol)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import TaskMapper
from app.database.models.task import TaskModel
from app.domain.task import Task, TaskStatus
from app.domain.values import IdempotencyKey

_ACTIVE_STATUSES = (TaskStatus.CREATED.value, TaskStatus.RUNNING.value)


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, task_id: UUID) -> Task | None:
        model = await self._session.get(TaskModel, task_id)
        return TaskMapper.to_domain(model) if model else None

    async def add(self, task: Task) -> None:
        self._session.add(TaskMapper.to_model(task))

    async def save(self, task: Task) -> None:
        await self._session.merge(TaskMapper.to_model(task))

    async def active_keys(self) -> set[IdempotencyKey]:
        result = await self._session.execute(
            select(TaskModel.idempotency_key).where(TaskModel.status.in_(_ACTIVE_STATUSES))
        )
        return {IdempotencyKey(value) for value in result.scalars()}
