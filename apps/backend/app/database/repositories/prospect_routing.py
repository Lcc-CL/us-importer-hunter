"""PostgreSQL persistence and batched source loading for prospect routing."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.prospect_routing import ProspectRoutingMapper
from app.database.models.bulk_import import RawImportRowModel
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactChannelModel, ContactModel
from app.database.models.import_resolution import (
    CompanyContactModel,
    CompanyResolutionProfileModel,
    ImportEntityDecisionModel,
)
from app.database.models.prospect_routing import ProspectRouteModel, ProspectRoutingRunModel
from app.domain.import_resolution import ImportEntityDecisionKind, ImportEntityType
from app.domain.prospect_routing import (
    ProspectRoute,
    ProspectRouteReviewStatus,
    ProspectRoutingRun,
    ProspectTier,
    RoutingContactSnapshot,
    RoutingSourceCompany,
    RoutingSourceRow,
)


class SqlAlchemyProspectRoutingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_run(self, routing_run_id: UUID) -> ProspectRoutingRun | None:
        model = await self._session.get(ProspectRoutingRunModel, routing_run_id)
        return ProspectRoutingMapper.run_to_domain(model) if model else None

    async def get_run_for_update(self, routing_run_id: UUID) -> ProspectRoutingRun | None:
        model = await self._session.scalar(
            select(ProspectRoutingRunModel)
            .where(ProspectRoutingRunModel.id == routing_run_id)
            .with_for_update()
        )
        return ProspectRoutingMapper.run_to_domain(model) if model else None

    async def find_run_by_configuration(
        self,
        *,
        import_session_id: UUID,
        rules_version: str,
        configuration_hash: str,
    ) -> ProspectRoutingRun | None:
        model = await self._session.scalar(
            select(ProspectRoutingRunModel).where(
                ProspectRoutingRunModel.import_session_id == import_session_id,
                ProspectRoutingRunModel.rules_version == rules_version,
                ProspectRoutingRunModel.configuration_hash == configuration_hash,
            )
        )
        return ProspectRoutingMapper.run_to_domain(model) if model else None

    async def add_run(self, run: ProspectRoutingRun) -> None:
        self._session.add(ProspectRoutingMapper.run_to_model(run))

    async def save_run(self, run: ProspectRoutingRun) -> None:
        await self._session.merge(ProspectRoutingMapper.run_to_model(run))

    async def add_routes(self, routes: tuple[ProspectRoute, ...]) -> None:
        self._session.add_all(
            [ProspectRoutingMapper.route_to_model(route) for route in routes]
        )

    async def list_available_generations(self, routing_run_id: UUID) -> tuple[int, ...]:
        values = await self._session.scalars(
            select(ProspectRouteModel.execution_generation)
            .where(ProspectRouteModel.routing_run_id == routing_run_id)
            .distinct()
            .order_by(ProspectRouteModel.execution_generation)
        )
        return tuple(values)

    async def get_route(self, route_id: UUID) -> ProspectRoute | None:
        model = await self._session.get(ProspectRouteModel, route_id)
        return ProspectRoutingMapper.route_to_domain(model) if model else None

    async def get_route_for_update(self, route_id: UUID) -> ProspectRoute | None:
        model = await self._session.scalar(
            select(ProspectRouteModel)
            .where(ProspectRouteModel.id == route_id)
            .with_for_update()
        )
        return ProspectRoutingMapper.route_to_domain(model) if model else None

    async def save_route(self, route: ProspectRoute) -> None:
        await self._session.merge(ProspectRoutingMapper.route_to_model(route))

    async def list_routes(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        tier: ProspectTier | None,
        review_status: ProspectRouteReviewStatus | None,
        minimum_score: float | None,
        maximum_score: float | None,
        has_contact: bool | None,
        role_category: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ProspectRoute], int]:
        filters = [
            ProspectRouteModel.routing_run_id == routing_run_id,
            ProspectRouteModel.execution_generation == execution_generation,
        ]
        if tier is not None:
            filters.append(ProspectRouteModel.effective_tier == tier.value)
        if review_status is not None:
            filters.append(ProspectRouteModel.review_status == review_status.value)
        if minimum_score is not None:
            filters.append(ProspectRouteModel.pre_score >= minimum_score)
        if maximum_score is not None:
            filters.append(ProspectRouteModel.pre_score <= maximum_score)
        if has_contact is not None:
            filters.append(ProspectRouteModel.has_usable_contact == has_contact)
        if role_category is not None:
            filters.append(ProspectRouteModel.preferred_role_category == role_category)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(ProspectRouteModel).where(*filters)
            )
            or 0
        )
        models = list(
            await self._session.scalars(
                select(ProspectRouteModel)
                .where(*filters)
                .order_by(
                    ProspectRouteModel.pre_score.desc(),
                    ProspectRouteModel.company_name,
                )
                .offset(offset)
                .limit(limit)
            )
        )
        return [ProspectRoutingMapper.route_to_domain(model) for model in models], total

    async def list_routes_for_companies(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        company_ids: tuple[UUID, ...],
    ) -> list[ProspectRoute]:
        if not company_ids:
            return []
        models = list(
            await self._session.scalars(
                select(ProspectRouteModel).where(
                    ProspectRouteModel.routing_run_id == routing_run_id,
                    ProspectRouteModel.execution_generation == execution_generation,
                    ProspectRouteModel.company_id.in_(company_ids),
                )
            )
        )
        return [ProspectRoutingMapper.route_to_domain(model) for model in models]

    async def list_source_companies(
        self,
        import_session_id: UUID,
    ) -> tuple[RoutingSourceCompany, ...]:
        decision_rows = list(
            (
                await self._session.execute(
                    select(
                        ImportEntityDecisionModel.candidate_entity_id,
                        ImportEntityDecisionModel.review_status,
                        ImportEntityDecisionModel.id,
                        RawImportRowModel.id,
                        RawImportRowModel.row_number,
                        RawImportRowModel.raw_payload,
                        RawImportRowModel.created_at,
                    )
                    .join(
                        RawImportRowModel,
                        RawImportRowModel.id
                        == ImportEntityDecisionModel.raw_import_row_id,
                    )
                    .where(
                        ImportEntityDecisionModel.import_session_id
                        == import_session_id,
                        ImportEntityDecisionModel.entity_type
                        == ImportEntityType.COMPANY.value,
                        ImportEntityDecisionModel.candidate_entity_id.is_not(None),
                        ImportEntityDecisionModel.decision
                        != ImportEntityDecisionKind.REJECTED.value,
                    )
                    .order_by(RawImportRowModel.row_number)
                )
            ).tuples()
        )
        rows_by_company: dict[UUID, list[RoutingSourceRow]] = defaultdict(list)
        unresolved_company_ids: set[UUID] = set()
        seen_rows: set[tuple[UUID, UUID]] = set()
        for (
            candidate_id,
            review_status,
            decision_id,
            row_id,
            row_number,
            raw_payload,
            created_at,
        ) in decision_rows:
            company_id = UUID(str(candidate_id))
            if review_status == "pending":
                unresolved_company_ids.add(company_id)
            row_key = (company_id, UUID(str(row_id)))
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            rows_by_company[company_id].append(
                RoutingSourceRow(
                    import_entity_decision_id=UUID(str(decision_id)),
                    raw_import_row_id=UUID(str(row_id)),
                    row_number=int(row_number),
                    raw_payload=dict(raw_payload),
                    created_at=created_at,
                )
            )
        company_ids = tuple(rows_by_company)
        if not company_ids:
            return ()

        company_rows = list(
            (
                await self._session.execute(
                    select(CompanyModel, CompanyResolutionProfileModel)
                    .outerjoin(
                        CompanyResolutionProfileModel,
                        CompanyResolutionProfileModel.company_id == CompanyModel.id,
                    )
                    .where(CompanyModel.id.in_(company_ids))
                )
            ).tuples()
        )
        contact_rows = list(
            (
                await self._session.execute(
                    select(
                        CompanyContactModel.company_id,
                        ContactModel.id,
                        CompanyContactModel.role_category,
                        CompanyContactModel.seniority,
                        CompanyContactModel.status,
                        CompanyContactModel.is_department_contact,
                        ContactModel.status,
                        func.bool_or(
                            ContactChannelModel.verification_status != "invalid"
                        ).label("has_usable_channel"),
                        func.bool_or(
                            and_(
                                ContactChannelModel.channel_type == "email",
                                ContactChannelModel.verification_status != "invalid",
                            )
                        ).label("has_usable_email"),
                    )
                    .join(ContactModel, ContactModel.id == CompanyContactModel.contact_id)
                    .outerjoin(
                        ContactChannelModel,
                        ContactChannelModel.contact_id == ContactModel.id,
                    )
                    .where(CompanyContactModel.company_id.in_(company_ids))
                    .group_by(
                        CompanyContactModel.company_id,
                        ContactModel.id,
                        CompanyContactModel.role_category,
                        CompanyContactModel.seniority,
                        CompanyContactModel.status,
                        CompanyContactModel.is_department_contact,
                        ContactModel.status,
                    )
                )
            ).tuples()
        )
        contacts_by_company: dict[UUID, list[RoutingContactSnapshot]] = defaultdict(list)
        for (
            company_id,
            contact_id,
            role_category,
            seniority,
            employment_status,
            is_department_contact,
            contact_status,
            has_usable_channel,
            has_usable_email,
        ) in contact_rows:
            active = employment_status == "active" and contact_status not in {
                "invalid",
                "inactive",
            }
            contacts_by_company[company_id].append(
                RoutingContactSnapshot(
                    contact_id=contact_id,
                    role_category=role_category,
                    seniority=seniority,
                    status="active" if active else "inactive",
                    has_usable_channel=active and bool(has_usable_channel),
                    has_usable_email=active and bool(has_usable_email),
                    is_department_contact=bool(is_department_contact),
                )
            )

        sources: list[RoutingSourceCompany] = []
        for company, profile in company_rows:
            sources.append(
                RoutingSourceCompany(
                    company_id=company.id,
                    company_name=company.name,
                    website=company.website,
                    profile_domain=(profile.normalized_domain if profile else None),
                    profile_address=(profile.normalized_address if profile else None),
                    profile_company_type=(profile.company_type if profile else None),
                    rows=tuple(rows_by_company[company.id]),
                    contacts=tuple(contacts_by_company[company.id]),
                    unresolved_company_conflict=company.id in unresolved_company_ids,
                )
            )
        return tuple(sorted(sources, key=lambda item: (item.company_name, str(item.company_id))))
