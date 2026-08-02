"""PostgreSQL persistence and queue operations for D5b1 entity resolution."""

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Table, bindparam, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.mappers.import_resolution import ImportResolutionMapper
from app.database.models.bulk_import import RawImportRowModel
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactModel
from app.database.models.import_resolution import (
    CompanyContactModel,
    CompanyExternalIdentityModel,
    CompanyResolutionProfileModel,
    ImportEntityDecisionModel,
    ImportProcessingJobModel,
    ImportResolutionModel,
)
from app.domain.import_resolution import (
    ACTIVE_IMPORT_JOB_STATUSES,
    CompanyContact,
    CompanyExternalIdentity,
    CompanyResolutionCandidate,
    CompanyResolutionProfile,
    ContactIdentityCandidate,
    ImportDecisionView,
    ImportEntityDecision,
    ImportEntityReviewStatus,
    ImportEntityType,
    ImportJobStatus,
    ImportProcessingJob,
    ImportResolution,
)


class SqlAlchemyImportResolutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_resolution(self, session_id: UUID) -> ImportResolution | None:
        model = await self._session.get(ImportResolutionModel, session_id)
        return ImportResolutionMapper.resolution_to_domain(model) if model else None

    async def get_resolution_for_update(self, session_id: UUID) -> ImportResolution | None:
        model = await self._session.scalar(
            select(ImportResolutionModel)
            .where(ImportResolutionModel.import_session_id == session_id)
            .with_for_update()
        )
        return ImportResolutionMapper.resolution_to_domain(model) if model else None

    async def add_resolution(self, resolution: ImportResolution) -> None:
        self._session.add(ImportResolutionMapper.resolution_to_model(resolution))

    async def save_resolution(self, resolution: ImportResolution) -> None:
        await self._session.merge(ImportResolutionMapper.resolution_to_model(resolution))

    async def list_processed_row_ids(self, session_id: UUID) -> set[UUID]:
        result = await self._session.scalars(
            select(ImportEntityDecisionModel.raw_import_row_id)
            .where(ImportEntityDecisionModel.import_session_id == session_id)
            .distinct()
        )
        return set(result)

    async def add_decisions(self, decisions: tuple[ImportEntityDecision, ...]) -> None:
        self._session.add_all(
            [ImportResolutionMapper.decision_to_model(decision) for decision in decisions]
        )

    async def get_decision(self, decision_id: UUID) -> ImportEntityDecision | None:
        model = await self._session.get(ImportEntityDecisionModel, decision_id)
        return ImportResolutionMapper.decision_to_domain(model) if model else None

    async def get_decision_for_update(self, decision_id: UUID) -> ImportEntityDecision | None:
        model = await self._session.scalar(
            select(ImportEntityDecisionModel)
            .where(ImportEntityDecisionModel.id == decision_id)
            .with_for_update()
        )
        return ImportResolutionMapper.decision_to_domain(model) if model else None

    async def get_row_decision(
        self,
        *,
        session_id: UUID,
        raw_import_row_id: UUID,
        entity_type: ImportEntityType,
    ) -> ImportEntityDecision | None:
        model = await self._session.scalar(
            select(ImportEntityDecisionModel).where(
                ImportEntityDecisionModel.import_session_id == session_id,
                ImportEntityDecisionModel.raw_import_row_id == raw_import_row_id,
                ImportEntityDecisionModel.entity_type == entity_type.value,
            )
        )
        return ImportResolutionMapper.decision_to_domain(model) if model else None

    async def save_decision(self, decision: ImportEntityDecision) -> None:
        await self._session.merge(ImportResolutionMapper.decision_to_model(decision))

    async def list_decisions(
        self,
        *,
        session_id: UUID,
        entity_type: ImportEntityType | None,
        review_status: ImportEntityReviewStatus | None,
        min_confidence: float | None,
        max_confidence: float | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ImportDecisionView], int]:
        filters = [ImportEntityDecisionModel.import_session_id == session_id]
        if entity_type is not None:
            filters.append(ImportEntityDecisionModel.entity_type == entity_type.value)
        if review_status is not None:
            filters.append(ImportEntityDecisionModel.review_status == review_status.value)
        if min_confidence is not None:
            filters.append(ImportEntityDecisionModel.confidence >= min_confidence)
        if max_confidence is not None:
            filters.append(ImportEntityDecisionModel.confidence <= max_confidence)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(ImportEntityDecisionModel).where(*filters)
            )
            or 0
        )
        models = list(
            await self._session.scalars(
                select(ImportEntityDecisionModel)
                .where(*filters)
                .order_by(
                    ImportEntityDecisionModel.review_status.desc(),
                    ImportEntityDecisionModel.created_at,
                )
                .offset(offset)
                .limit(limit)
            )
        )
        row_numbers: dict[UUID, int] = (
            dict(
                (
                    await self._session.execute(
                    select(
                        ImportEntityDecisionModel.raw_import_row_id,
                        RawImportRowModel.row_number,
                    )
                    .join(
                        RawImportRowModel,
                        RawImportRowModel.id == ImportEntityDecisionModel.raw_import_row_id,
                    )
                        .where(ImportEntityDecisionModel.id.in_([model.id for model in models]))
                    )
                ).tuples().all()
            )
            if models
            else {}
        )
        company_ids = {
            model.candidate_entity_id
            for model in models
            if model.entity_type == ImportEntityType.COMPANY.value
            and model.candidate_entity_id is not None
        }
        contact_ids = {
            model.candidate_entity_id
            for model in models
            if model.entity_type == ImportEntityType.CONTACT.value
            and model.candidate_entity_id is not None
        }
        company_labels: dict[UUID, str] = dict(
            (
                await self._session.execute(
                    select(CompanyModel.id, CompanyModel.name).where(
                        CompanyModel.id.in_(company_ids)
                    )
                )
                ).tuples().all()
        ) if company_ids else {}
        contact_labels: dict[UUID, str] = dict(
            (
                await self._session.execute(
                    select(ContactModel.id, ContactModel.name).where(
                        ContactModel.id.in_(contact_ids)
                    )
                )
            )
            .tuples().all()
        ) if contact_ids else {}
        views: list[ImportDecisionView] = []
        for model in models:
            candidate_label: str | None = None
            if model.candidate_entity_id is not None:
                candidate_label = (
                    company_labels.get(model.candidate_entity_id)
                    if model.entity_type == ImportEntityType.COMPANY.value
                    else contact_labels.get(model.candidate_entity_id)
                )
            row_number = int(row_numbers.get(model.raw_import_row_id, 0))
            views.append(
                ImportDecisionView(
                    decision=ImportResolutionMapper.decision_to_domain(model),
                    row_number=row_number,
                    source_label=f"Import row {row_number}",
                    candidate_label=candidate_label,
                )
            )
        return views, total

    async def list_company_candidates(self) -> list[CompanyResolutionCandidate]:
        rows = await self._session.execute(
            select(CompanyModel, CompanyResolutionProfileModel).outerjoin(
                CompanyResolutionProfileModel,
                CompanyResolutionProfileModel.company_id == CompanyModel.id,
            )
        )
        return [
            CompanyResolutionCandidate(
                company_id=company.id,
                canonical_name=company.name,
                normalized_name=(profile.normalized_name if profile else company.normalized_name),
                normalized_domain=(
                    profile.normalized_domain if profile else company.website_host
                ),
                normalized_address=profile.normalized_address if profile else None,
                company_type=profile.company_type if profile else None,
                normalized_phone=profile.normalized_phone if profile else None,
            )
            for company, profile in rows
        ]

    async def list_external_identities(self) -> list[CompanyExternalIdentity]:
        models = await self._session.scalars(select(CompanyExternalIdentityModel))
        return [ImportResolutionMapper.identity_to_domain(model) for model in models]

    async def add_external_identity(self, identity: CompanyExternalIdentity) -> None:
        self._session.add(ImportResolutionMapper.identity_to_model(identity))

    async def save_external_identity(self, identity: CompanyExternalIdentity) -> None:
        await self._session.merge(ImportResolutionMapper.identity_to_model(identity))

    async def update_external_identities(
        self, identities: tuple[CompanyExternalIdentity, ...]
    ) -> None:
        if not identities:
            return
        statement = (
            cast(Table, CompanyExternalIdentityModel.__table__).update()
            .where(CompanyExternalIdentityModel.id == bindparam("b_id"))
            .values(
                first_seen_at=bindparam("b_first_seen_at"),
                last_seen_at=bindparam("b_last_seen_at"),
                updated_at=bindparam("b_updated_at"),
            )
        )
        await self._session.execute(
            statement,
            [
                {
                    "b_id": identity.id,
                    "b_first_seen_at": identity.first_seen_at,
                    "b_last_seen_at": identity.last_seen_at,
                    "b_updated_at": identity.updated_at,
                }
                for identity in identities
            ],
        )

    async def get_company_profile(
        self, company_id: UUID
    ) -> CompanyResolutionProfile | None:
        model = await self._session.get(CompanyResolutionProfileModel, company_id)
        return ImportResolutionMapper.profile_to_domain(model) if model else None

    async def list_company_profiles(self) -> list[CompanyResolutionProfile]:
        models = await self._session.scalars(select(CompanyResolutionProfileModel))
        return [ImportResolutionMapper.profile_to_domain(model) for model in models]

    async def add_company_profile(self, profile: CompanyResolutionProfile) -> None:
        self._session.add(ImportResolutionMapper.profile_to_model(profile))

    async def save_company_profile(self, profile: CompanyResolutionProfile) -> None:
        await self._session.merge(ImportResolutionMapper.profile_to_model(profile))

    async def update_company_profiles(
        self, profiles: tuple[CompanyResolutionProfile, ...]
    ) -> None:
        if not profiles:
            return
        statement = (
            cast(Table, CompanyResolutionProfileModel.__table__).update()
            .where(CompanyResolutionProfileModel.company_id == bindparam("b_company_id"))
            .values(
                normalized_name=bindparam("b_normalized_name"),
                normalized_domain=bindparam("b_normalized_domain"),
                normalized_address=bindparam("b_normalized_address"),
                company_type=bindparam("b_company_type"),
                normalized_phone=bindparam("b_normalized_phone"),
                first_seen_at=bindparam("b_first_seen_at"),
                last_seen_at=bindparam("b_last_seen_at"),
                updated_at=bindparam("b_updated_at"),
            )
        )
        await self._session.execute(
            statement,
            [
                {
                    "b_company_id": profile.company_id,
                    "b_normalized_name": profile.normalized_name,
                    "b_normalized_domain": profile.normalized_domain,
                    "b_normalized_address": profile.normalized_address,
                    "b_company_type": profile.company_type,
                    "b_normalized_phone": profile.normalized_phone,
                    "b_first_seen_at": profile.first_seen_at,
                    "b_last_seen_at": profile.last_seen_at,
                    "b_updated_at": profile.updated_at,
                }
                for profile in profiles
            ],
        )

    async def list_contact_candidates(self) -> list[ContactIdentityCandidate]:
        models = list(
            await self._session.scalars(
                select(ContactModel).options(
                    selectinload(ContactModel.channels),
                    selectinload(ContactModel.sources),
                )
            )
        )
        link_rows = await self._session.execute(
            select(CompanyContactModel.contact_id, CompanyContactModel.company_id)
        )
        companies_by_contact: dict[UUID, set[UUID]] = {}
        for contact_id, company_id in link_rows:
            companies_by_contact.setdefault(contact_id, set()).add(company_id)
        candidates: list[ContactIdentityCandidate] = []
        for model in models:
            company_ids = companies_by_contact.setdefault(model.id, set())
            if model.company_id is not None:
                company_ids.add(model.company_id)
            candidates.append(
                ContactIdentityCandidate(
                    contact_id=model.id,
                    display_name=model.name,
                    normalized_name=model.normalized_name,
                    normalized_title=model.title_raw.lower() if model.title_raw else None,
                    emails=tuple(
                        channel.normalized_value
                        for channel in model.channels
                        if channel.channel_type == "email"
                        and channel.verification_status != "invalid"
                    ),
                    linkedin_urls=tuple(
                        channel.normalized_value
                        for channel in model.channels
                        if channel.channel_type == "linkedin"
                        and channel.verification_status != "invalid"
                    ),
                    company_ids=tuple(sorted(company_ids, key=str)),
                )
            )
        return candidates

    async def list_company_contacts(self) -> list[CompanyContact]:
        models = await self._session.scalars(select(CompanyContactModel))
        return [ImportResolutionMapper.company_contact_to_domain(model) for model in models]

    async def add_company_contact(self, link: CompanyContact) -> None:
        self._session.add(ImportResolutionMapper.company_contact_to_model(link))

    async def save_company_contact(self, link: CompanyContact) -> None:
        await self._session.merge(ImportResolutionMapper.company_contact_to_model(link))

    async def update_company_contacts(self, links: tuple[CompanyContact, ...]) -> None:
        if not links:
            return
        statement = (
            cast(Table, CompanyContactModel.__table__).update()
            .where(CompanyContactModel.id == bindparam("b_id"))
            .values(
                raw_title=bindparam("b_raw_title"),
                role_category=bindparam("b_role_category"),
                seniority=bindparam("b_seniority"),
                is_department_contact=bindparam("b_is_department_contact"),
                status=bindparam("b_status"),
                first_seen_at=bindparam("b_first_seen_at"),
                last_seen_at=bindparam("b_last_seen_at"),
                updated_at=bindparam("b_updated_at"),
            )
        )
        await self._session.execute(
            statement,
            [
                {
                    "b_id": link.id,
                    "b_raw_title": link.raw_title,
                    "b_role_category": link.role_category.value,
                    "b_seniority": link.seniority,
                    "b_is_department_contact": link.is_department_contact,
                    "b_status": link.status.value,
                    "b_first_seen_at": link.first_seen_at,
                    "b_last_seen_at": link.last_seen_at,
                    "b_updated_at": link.updated_at,
                }
                for link in links
            ],
        )


class SqlAlchemyImportProcessingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id_for_update(self, job_id: UUID) -> ImportProcessingJob | None:
        model = await self._session.scalar(
            select(ImportProcessingJobModel)
            .where(ImportProcessingJobModel.id == job_id)
            .with_for_update()
        )
        return ImportResolutionMapper.job_to_domain(model) if model else None

    async def get_latest_for_session(self, session_id: UUID) -> ImportProcessingJob | None:
        model = await self._session.scalar(
            select(ImportProcessingJobModel)
            .where(ImportProcessingJobModel.import_session_id == session_id)
            .order_by(ImportProcessingJobModel.created_at.desc())
            .limit(1)
        )
        return ImportResolutionMapper.job_to_domain(model) if model else None

    async def find_active_by_business_key(
        self, business_key: str
    ) -> ImportProcessingJob | None:
        model = await self._session.scalar(
            select(ImportProcessingJobModel).where(
                ImportProcessingJobModel.business_key == business_key,
                ImportProcessingJobModel.status.in_(
                    [status.value for status in ACTIVE_IMPORT_JOB_STATUSES]
                ),
            )
        )
        return ImportResolutionMapper.job_to_domain(model) if model else None

    async def add(self, job: ImportProcessingJob) -> None:
        self._session.add(ImportResolutionMapper.job_to_model(job))

    async def save(self, job: ImportProcessingJob) -> None:
        await self._session.merge(ImportResolutionMapper.job_to_model(job))

    async def claim_next(
        self,
        *,
        owner: str,
        now: datetime,
        lease_ttl: timedelta,
    ) -> ImportProcessingJob | None:
        model = await self._session.scalar(
            select(ImportProcessingJobModel)
            .where(
                ImportProcessingJobModel.status == ImportJobStatus.PENDING.value,
                ImportProcessingJobModel.available_at <= now,
            )
            .order_by(ImportProcessingJobModel.available_at, ImportProcessingJobModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if model is None:
            return None
        leased = ImportResolutionMapper.job_to_domain(model).lease(
            owner=owner, lease_ttl=lease_ttl, now=now
        )
        await self.save(leased)
        return leased

    async def get_stale_for_update(
        self, *, now: datetime, limit: int
    ) -> list[ImportProcessingJob]:
        models = list(
            await self._session.scalars(
                select(ImportProcessingJobModel)
                .where(
                    ImportProcessingJobModel.status.in_(
                        [ImportJobStatus.LEASED.value, ImportJobStatus.RUNNING.value]
                    ),
                    ImportProcessingJobModel.lease_expires_at < now,
                )
                .order_by(ImportProcessingJobModel.lease_expires_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        return [ImportResolutionMapper.job_to_domain(model) for model in models]
