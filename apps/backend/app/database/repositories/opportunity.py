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

    async def get_for_company_and_user(
        self, company_id: UUID, user_id: UUID
    ) -> Opportunity | None:
        """Open opportunity first; otherwise the most recent one."""
        result = await self._session.execute(
            select(OpportunityModel)
            .where(
                OpportunityModel.company_id == company_id,
                OpportunityModel.user_id == user_id,
            )
            .order_by(OpportunityModel.created_at.desc())
        )
        models = list(result.scalars())
        if not models:
            return None
        closed = {"disqualified", "won", "lost"}
        open_models = [m for m in models if m.stage not in closed]
        return OpportunityMapper.to_domain(open_models[0] if open_models else models[0])
