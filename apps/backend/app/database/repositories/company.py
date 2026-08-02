"""Company repository (SQLAlchemy implementation of the domain protocol)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import CompanyMapper
from app.database.models.company import CompanyModel
from app.domain.company import Company
from app.domain.values import CompanyName


class SqlAlchemyCompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: UUID) -> Company | None:
        model = await self._session.get(CompanyModel, company_id)
        return CompanyMapper.to_domain(model) if model else None

    async def add(self, company: Company) -> None:
        self._session.add(CompanyMapper.to_model(company))

    async def save(self, company: Company) -> None:
        await self._session.merge(CompanyMapper.to_model(company))

    async def exists(self, company_id: UUID) -> bool:
        result = await self._session.execute(
            select(CompanyModel.id).where(CompanyModel.id == company_id)
        )
        return result.scalar_one_or_none() is not None

    async def find_by_normalized_name(self, name: CompanyName) -> Company | None:
        result = await self._session.execute(
            select(CompanyModel)
            .where(CompanyModel.normalized_name == name.normalized)
            .order_by(CompanyModel.created_at)
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return CompanyMapper.to_domain(model) if model else None

    async def find_by_website_host(self, host: str) -> Company | None:
        normalized_host = host.lower().removeprefix("www.")
        result = await self._session.execute(
            select(CompanyModel)
            .where(
                CompanyModel.website_host.in_(
                    (normalized_host, f"www.{normalized_host}")
                )
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return CompanyMapper.to_domain(model) if model else None
