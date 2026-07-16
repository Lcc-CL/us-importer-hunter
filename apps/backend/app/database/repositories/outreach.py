"""Outreach repository (SQLAlchemy implementation of the domain protocol)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import OutreachMapper
from app.database.models.outreach import OutreachModel
from app.domain.outreach import Outreach


class SqlAlchemyOutreachRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, outreach_id: UUID) -> Outreach | None:
        model = await self._session.get(OutreachModel, outreach_id)
        return OutreachMapper.to_domain(model) if model else None

    async def add(self, outreach: Outreach) -> None:
        self._session.add(OutreachMapper.to_model(outreach))

    async def save(self, outreach: Outreach) -> None:
        await self._session.merge(OutreachMapper.to_model(outreach))

    async def list_for_opportunity(self, opportunity_id: UUID) -> list[Outreach]:
        result = await self._session.execute(
            select(OutreachModel)
            .where(OutreachModel.opportunity_id == opportunity_id)
            .order_by(OutreachModel.created_at)
        )
        return [OutreachMapper.to_domain(model) for model in result.scalars()]
