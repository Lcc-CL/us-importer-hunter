"""PostgreSQL persistence and batched source loading for Umail exports."""

from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.umail_export import UmailExportMapper
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactChannelModel, ContactModel
from app.database.models.import_resolution import CompanyContactModel
from app.database.models.prospect_routing import ProspectRouteModel
from app.database.models.umail_export import (
    SuppressionEntryModel,
    UmailExportBatchModel,
    UmailExportRowModel,
)
from app.domain.prospect_routing import ProspectRouteReviewStatus, ProspectTier
from app.domain.umail_export import (
    SuppressionEntry,
    UmailExportBatch,
    UmailExportCompanyCandidate,
    UmailExportContactCandidate,
    UmailExportEmailCandidate,
    UmailExportPhoneCandidate,
    UmailExportRow,
)


@dataclass
class _ContactAccumulator:
    contact_id: UUID
    name: str
    title: str | None
    role_category: str
    seniority: str
    is_department_contact: bool
    emails: list[UmailExportEmailCandidate] = field(default_factory=list)
    phones: list[UmailExportPhoneCandidate] = field(default_factory=list)


class SqlAlchemyUmailExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_suppression(self, entry_id: UUID) -> SuppressionEntry | None:
        model = await self._session.get(SuppressionEntryModel, entry_id)
        return UmailExportMapper.suppression_to_domain(model) if model else None

    async def get_suppression_for_update(
        self, entry_id: UUID
    ) -> SuppressionEntry | None:
        model = await self._session.scalar(
            select(SuppressionEntryModel)
            .where(SuppressionEntryModel.id == entry_id)
            .with_for_update()
        )
        return UmailExportMapper.suppression_to_domain(model) if model else None

    async def add_suppression(self, entry: SuppressionEntry) -> None:
        self._session.add(UmailExportMapper.suppression_to_model(entry))

    async def save_suppression(self, entry: SuppressionEntry) -> None:
        await self._session.merge(UmailExportMapper.suppression_to_model(entry))

    async def list_suppressions(
        self, *, active: bool | None, offset: int, limit: int
    ) -> tuple[list[SuppressionEntry], int]:
        filters = [] if active is None else [SuppressionEntryModel.active == active]
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(SuppressionEntryModel).where(*filters)
            )
            or 0
        )
        models = list(
            await self._session.scalars(
                select(SuppressionEntryModel)
                .where(*filters)
                .order_by(SuppressionEntryModel.created_at.desc(), SuppressionEntryModel.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return [UmailExportMapper.suppression_to_domain(model) for model in models], total

    async def list_active_suppressions(self) -> list[SuppressionEntry]:
        models = list(
            await self._session.scalars(
                select(SuppressionEntryModel)
                .where(SuppressionEntryModel.active.is_(True))
                .order_by(SuppressionEntryModel.created_at, SuppressionEntryModel.id)
            )
        )
        return [UmailExportMapper.suppression_to_domain(model) for model in models]

    async def find_batch_by_selection_hash(
        self, selection_hash: str
    ) -> UmailExportBatch | None:
        model = await self._session.scalar(
            select(UmailExportBatchModel).where(
                UmailExportBatchModel.selection_hash == selection_hash
            )
        )
        return UmailExportMapper.batch_to_domain(model) if model else None

    async def get_batch(self, batch_id: UUID) -> UmailExportBatch | None:
        model = await self._session.get(UmailExportBatchModel, batch_id)
        return UmailExportMapper.batch_to_domain(model) if model else None

    async def get_batch_for_update(self, batch_id: UUID) -> UmailExportBatch | None:
        model = await self._session.scalar(
            select(UmailExportBatchModel)
            .where(UmailExportBatchModel.id == batch_id)
            .with_for_update()
        )
        return UmailExportMapper.batch_to_domain(model) if model else None

    async def add_batch(
        self, batch: UmailExportBatch, rows: tuple[UmailExportRow, ...]
    ) -> None:
        self._session.add(UmailExportMapper.batch_to_model(batch))
        self._session.add_all([UmailExportMapper.row_to_model(row) for row in rows])

    async def save_batch(self, batch: UmailExportBatch) -> None:
        await self._session.merge(UmailExportMapper.batch_to_model(batch))

    async def list_rows(self, batch_id: UUID) -> list[UmailExportRow]:
        models = list(
            await self._session.scalars(
                select(UmailExportRowModel)
                .where(UmailExportRowModel.batch_id == batch_id)
                .order_by(UmailExportRowModel.position)
            )
        )
        return [UmailExportMapper.row_to_domain(model) for model in models]

    async def load_b_candidates(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        company_ids: tuple[UUID, ...],
    ) -> tuple[UmailExportCompanyCandidate, ...]:
        if not company_ids:
            return ()
        route_rows = list(
            (
                await self._session.execute(
                    select(ProspectRouteModel, CompanyModel)
                    .join(CompanyModel, CompanyModel.id == ProspectRouteModel.company_id)
                    .where(
                        ProspectRouteModel.routing_run_id == routing_run_id,
                        ProspectRouteModel.execution_generation == execution_generation,
                        ProspectRouteModel.company_id.in_(company_ids),
                    )
                    .order_by(func.lower(CompanyModel.name), CompanyModel.id)
                )
            ).tuples()
        )
        contact_rows = list(
            (
                await self._session.execute(
                    select(
                        CompanyContactModel.company_id,
                        ContactModel.id,
                        ContactModel.name,
                        ContactModel.title_raw,
                        CompanyContactModel.raw_title,
                        CompanyContactModel.role_category,
                        CompanyContactModel.seniority,
                        CompanyContactModel.is_department_contact,
                        ContactChannelModel.channel_type,
                        ContactChannelModel.normalized_value,
                        ContactChannelModel.display_value,
                        ContactChannelModel.verification_status,
                    )
                    .join(ContactModel, ContactModel.id == CompanyContactModel.contact_id)
                    .outerjoin(
                        ContactChannelModel,
                        and_(
                            ContactChannelModel.contact_id == ContactModel.id,
                            ContactChannelModel.channel_type.in_(("email", "phone")),
                        ),
                    )
                    .where(
                        CompanyContactModel.company_id.in_(company_ids),
                        CompanyContactModel.status == "active",
                        ContactModel.status.not_in(("invalid", "inactive")),
                    )
                    .order_by(
                        CompanyContactModel.company_id,
                        CompanyContactModel.is_department_contact,
                        ContactModel.normalized_name,
                        ContactModel.id,
                        ContactChannelModel.channel_type,
                        ContactChannelModel.normalized_value,
                    )
                )
            ).tuples()
        )
        contacts: dict[UUID, dict[UUID, _ContactAccumulator]] = defaultdict(dict)
        for (
            company_id,
            contact_id,
            name,
            title_raw,
            link_title,
            role_category,
            seniority,
            is_department_contact,
            channel_type,
            normalized_email,
            display_email,
            verification_status,
        ) in contact_rows:
            company_contacts = contacts[company_id]
            accumulator = company_contacts.get(contact_id)
            if accumulator is None:
                accumulator = _ContactAccumulator(
                    contact_id=contact_id,
                    name=name,
                    title=title_raw or link_title,
                    role_category=role_category,
                    seniority=seniority,
                    is_department_contact=is_department_contact,
                )
                company_contacts[contact_id] = accumulator
            if normalized_email is not None and channel_type == "email":
                accumulator.emails.append(
                    UmailExportEmailCandidate(
                        normalized_value=normalized_email,
                        display_value=display_email,
                        verification_status=verification_status,
                    )
                )
            elif normalized_email is not None and channel_type == "phone":
                accumulator.phones.append(
                    UmailExportPhoneCandidate(
                        normalized_value=normalized_email,
                        display_value=display_email,
                        verification_status=verification_status,
                    )
                )

        candidates: list[UmailExportCompanyCandidate] = []
        for route, company in route_rows:
            company_contacts = contacts.get(company.id, {})
            candidate_contacts = tuple(
                UmailExportContactCandidate(
                    contact_id=value.contact_id,
                    name=value.name,
                    title=value.title,
                    role_category=value.role_category,
                    seniority=value.seniority,
                    is_department_contact=value.is_department_contact,
                    emails=tuple(value.emails),
                    phones=tuple(value.phones),
                )
                for value in company_contacts.values()
            )
            candidates.append(
                UmailExportCompanyCandidate(
                    company_id=company.id,
                    company_name=company.name,
                    company_website=company.website,
                    country=None,
                    pre_score=route.pre_score,
                    route_reasons=tuple(route.reason_codes),
                    effective_tier=(
                        ProspectTier(route.effective_tier) if route.effective_tier else None
                    ),
                    review_status=ProspectRouteReviewStatus(route.review_status),
                    contacts=candidate_contacts,
                )
            )
        return tuple(candidates)
