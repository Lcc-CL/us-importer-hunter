"""Opportunity repository (SQLAlchemy implementation of the domain protocol)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import OpportunityMapper
from app.database.models.opportunity import OpportunityModel
from app.domain.opportunity import Opportunity


class SqlAlchemyOpportunityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, opportunity_id: UUID) -> Opportunity | None:
        model = await self._session.get(OpportunityModel, opportunity_id)
        return OpportunityMapper.to_domain(model) if model else None

    async def add(self, opportunity: Opportunity) -> None:
        self._session.add(OpportunityMapper.to_model(opportunity))

    async def save(self, opportunity: Opportunity) -> None:
        await self._session.merge(OpportunityMapper.to_model(opportunity))

    async def list_for_company_and_user(
        self, company_id: UUID, user_id: UUID
    ) -> list[Opportunity]:
        result = await self._session.execute(
            select(OpportunityModel)
            .where(
                OpportunityModel.company_id == company_id,
                OpportunityModel.user_id == user_id,
            )
            .order_by(OpportunityModel.created_at)
        )
        return [OpportunityMapper.to_domain(model) for model in result.scalars()]
