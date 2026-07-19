"""ResearchRun repository (SQLAlchemy implementation of the domain protocol)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import ResearchRunMapper
from app.database.models.research import ResearchRunModel
from app.domain.research import ResearchRun


class SqlAlchemyResearchRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, research_id: UUID) -> ResearchRun | None:
        model = await self._session.get(ResearchRunModel, research_id)
        return ResearchRunMapper.to_domain(model) if model else None

    async def add(self, run: ResearchRun) -> None:
        self._session.add(ResearchRunMapper.to_model(run))

    async def save(self, run: ResearchRun) -> None:
        await self._session.merge(ResearchRunMapper.to_model(run))

    async def list_for_website(self, website: str, *, limit: int = 10) -> list[ResearchRun]:
        result = await self._session.execute(
            select(ResearchRunModel)
            .where(ResearchRunModel.website == website)
            .order_by(ResearchRunModel.started_at.desc())
            .limit(limit)
        )
        return [ResearchRunMapper.to_domain(model) for model in result.scalars().all()]
