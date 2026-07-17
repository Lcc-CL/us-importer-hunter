"""Contact repository (SQLAlchemy implementation of the domain protocol)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.contact import ContactMapper, FitAssessmentMapper
from app.database.models.contact import (
    ContactChannelModel,
    ContactFitAssessmentModel,
    ContactModel,
)
from app.domain.contact import Contact, DecisionMakerFitAssessment


class SqlAlchemyContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, contact_id: UUID) -> Contact | None:
        model = await self._session.get(ContactModel, contact_id)
        return ContactMapper.to_domain(model) if model else None

    async def add(self, contact: Contact) -> None:
        self._session.add(ContactMapper.to_model(contact))

    async def save(self, contact: Contact) -> None:
        await self._session.merge(ContactMapper.to_model(contact))

    async def list_for_company(self, company_id: UUID) -> list[Contact]:
        result = await self._session.execute(
            select(ContactModel)
            .where(ContactModel.company_id == company_id)
            .order_by(ContactModel.created_at)
        )
        return [ContactMapper.to_domain(model) for model in result.scalars()]

    async def find_by_email(self, company_id: UUID, normalized_email: str) -> Contact | None:
        return await self._find_by_channel(company_id, "email", normalized_email)

    async def find_by_linkedin_url(
        self, company_id: UUID, normalized_url: str
    ) -> Contact | None:
        return await self._find_by_channel(company_id, "linkedin", normalized_url)

    async def record_fit_assessment(self, assessment: DecisionMakerFitAssessment) -> None:
        self._session.add(FitAssessmentMapper.to_model(assessment))

    async def list_fit_assessments_for_company(
        self, company_id: UUID
    ) -> list[DecisionMakerFitAssessment]:
        result = await self._session.execute(
            select(ContactFitAssessmentModel)
            .where(ContactFitAssessmentModel.company_id == company_id)
            .order_by(ContactFitAssessmentModel.assessed_at.desc())
        )
        return [FitAssessmentMapper.to_domain(model) for model in result.scalars()]

    async def _find_by_channel(
        self, company_id: UUID, channel_type: str, normalized_value: str
    ) -> Contact | None:
        result = await self._session.execute(
            select(ContactModel)
            .join(ContactChannelModel, ContactChannelModel.contact_id == ContactModel.id)
            .where(
                ContactModel.company_id == company_id,
                ContactChannelModel.channel_type == channel_type,
                ContactChannelModel.normalized_value == normalized_value,
                ContactChannelModel.verification_status != "invalid",
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return ContactMapper.to_domain(model) if model else None
