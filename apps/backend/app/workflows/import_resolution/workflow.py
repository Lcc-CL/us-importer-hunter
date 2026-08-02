"""Application workflows for D5b1 import entity resolution."""

import dataclasses
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.bulk_import import ImportSession, ImportSessionStatus, RawImportRow
from app.domain.company import Company
from app.domain.contact import (
    Contact,
    ContactChannel,
    ContactChannelType,
    Department,
    JobTitle,
    PersonName,
    SeniorityLevel,
)
from app.domain.exceptions import DomainError, InvalidStateTransition
from app.domain.import_resolution import (
    CompanyContact,
    CompanyExternalIdentity,
    CompanyResolutionCandidate,
    CompanyResolutionProfile,
    ContactIdentityCandidate,
    ImportDecisionView,
    ImportEntityDecision,
    ImportEntityDecisionKind,
    ImportEntityReviewStatus,
    ImportEntityType,
    ImportProcessingJob,
    ImportResolution,
    ImportResolutionStatus,
    ImportReviewAction,
    ImportRoleCategory,
)
from app.domain.repositories import ImportResolutionUnitOfWork
from app.domain.values import CompanyName, SourceReference, WebsiteUrl
from app.services.import_resolution import (
    DeterministicEntityMatcher,
    ProjectedImportRow,
    RawImportProjector,
)
from app.shared.exceptions import ApplicationConflictError, ResourceNotFoundError

ImportResolutionUowFactory = Callable[[], ImportResolutionUnitOfWork]
Heartbeat = Callable[[], Awaitable[None]]
RESOLUTION_BATCH_SIZE = 250


@dataclass(frozen=True)
class ImportResolutionSubmission:
    resolution: ImportResolution
    job: ImportProcessingJob
    reused: bool


@dataclass(frozen=True)
class ImportDecisionPage:
    session_id: UUID
    page: int
    limit: int
    total: int
    decisions: tuple[ImportDecisionView, ...]


@dataclass
class _ResolutionIndex:
    companies: dict[UUID, CompanyResolutionCandidate]
    profiles: dict[UUID, CompanyResolutionProfile]
    external_identities: dict[tuple[str, str], CompanyExternalIdentity]
    contacts: dict[UUID, ContactIdentityCandidate]
    email_index: dict[str, UUID]
    linkedin_index: dict[str, UUID]
    company_contacts: dict[tuple[UUID, UUID], CompanyContact]
    dirty_profile_ids: set[UUID]
    dirty_identity_keys: set[tuple[str, str]]
    dirty_company_contact_keys: set[tuple[UUID, UUID]]

    def clear_pending(self) -> None:
        self.dirty_profile_ids.clear()
        self.dirty_identity_keys.clear()
        self.dirty_company_contact_keys.clear()


class ImportResolutionSubmissionWorkflow:
    def __init__(self, uow_factory: ImportResolutionUowFactory, *, max_attempts: int = 3) -> None:
        self._uow_factory = uow_factory
        self._max_attempts = max_attempts

    async def submit(self, session_id: UUID) -> ImportResolutionSubmission:
        async with self._uow_factory() as uow:
            session = await uow.bulk_import.get_session(session_id)
            if session is None:
                raise ResourceNotFoundError(f"import session not found: {session_id}")
            if session.status not in {
                ImportSessionStatus.COMPLETED,
                ImportSessionStatus.PARTIAL_FAILED,
            }:
                raise ApplicationConflictError(
                    f"import session in {session.status.value} cannot be resolved"
                )
            resolution = await uow.import_resolution.get_resolution(session_id)
            existing_job = await uow.import_processing_jobs.get_latest_for_session(session_id)
            if resolution is not None and resolution.status in {
                ImportResolutionStatus.PENDING,
                ImportResolutionStatus.RUNNING,
                ImportResolutionStatus.COMPLETED,
                ImportResolutionStatus.PARTIAL_FAILED,
            }:
                if existing_job is None:
                    raise RuntimeError("import resolution exists without a processing job")
                return ImportResolutionSubmission(resolution, existing_job, True)

            if resolution is None:
                resolution = ImportResolution.create(
                    import_session_id=session_id,
                    total_rows=session.accepted_rows,
                    invalid_rows=session.invalid_rows,
                )
                await uow.import_resolution.add_resolution(resolution)
            else:
                resolution.status = ImportResolutionStatus.PENDING
                resolution.completed_at = None
                resolution.error_summary = None
                await uow.import_resolution.save_resolution(resolution)
            job = ImportProcessingJob.create(
                import_session_id=session_id,
                max_attempts=self._max_attempts,
            )
            await uow.import_processing_jobs.add(job)
            await uow.commit()
            return ImportResolutionSubmission(resolution, job, False)


class ImportEntityResolutionWorkflow:
    def __init__(
        self,
        uow_factory: ImportResolutionUowFactory,
        *,
        projector: RawImportProjector | None = None,
        matcher: DeterministicEntityMatcher | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._projector = projector or RawImportProjector()
        self._matcher = matcher or DeterministicEntityMatcher()

    async def execute(
        self,
        session_id: UUID,
        *,
        heartbeat: Heartbeat | None = None,
    ) -> ImportResolution:
        session, mapping = await self._load_session(session_id)
        index, processed_row_ids = await self._load_index(session_id)
        after_row_number = 0
        while True:
            async with self._uow_factory() as uow:
                resolution = await uow.import_resolution.get_resolution_for_update(session_id)
                if resolution is None:
                    raise ResourceNotFoundError(f"import resolution not found: {session_id}")
                if resolution.status in {
                    ImportResolutionStatus.COMPLETED,
                    ImportResolutionStatus.PARTIAL_FAILED,
                }:
                    return resolution
                resolution.start()
                rows = await uow.bulk_import.list_accepted_rows_after(
                    session_id=session_id,
                    after_row_number=after_row_number,
                    limit=RESOLUTION_BATCH_SIZE,
                )
                if not rows:
                    resolution.complete()
                    await uow.import_resolution.save_resolution(resolution)
                    await uow.commit()
                    return resolution
                after_row_number = rows[-1].row_number
                for row in rows:
                    if row.id in processed_row_ids:
                        continue
                    await self._resolve_row(
                        uow=uow,
                        session_id=session_id,
                        source=session.source,
                        mapping=mapping,
                        row=row,
                        resolution=resolution,
                        index=index,
                    )
                    processed_row_ids.add(row.id)
                await self._flush_index_changes(uow, index)
                await uow.import_resolution.save_resolution(resolution)
                await uow.commit()
                index.clear_pending()
            if heartbeat is not None:
                await heartbeat()

    async def _resolve_row(
        self,
        *,
        uow: ImportResolutionUnitOfWork,
        session_id: UUID,
        source: str,
        mapping: Mapping[str, str],
        row: RawImportRow,
        resolution: ImportResolution,
        index: _ResolutionIndex,
    ) -> None:
        projected = self._projector.project(row.raw_payload, mapping=mapping)
        company_match = self._matcher.match_company(
            projected,
            source=source,
            external_identities={
                key: identity.company_id for key, identity in index.external_identities.items()
            },
            companies=index.companies,
        )
        company_id: UUID | None = company_match.candidate_entity_id
        if company_match.decision is ImportEntityDecisionKind.AUTO_CREATE:
            try:
                company_id = await self._create_company(
                    uow=uow,
                    source=source,
                    row=row,
                    projected=projected,
                    index=index,
                )
            except (DomainError, ValueError):
                company_match = dataclasses.replace(
                    company_match,
                    decision=ImportEntityDecisionKind.REJECTED,
                    candidate_entity_id=None,
                    confidence=0.0,
                    reason_codes=(*company_match.reason_codes, "company_value_invalid"),
                )
                company_id = None
        elif company_match.decision is ImportEntityDecisionKind.AUTO_MERGE:
            assert company_id is not None
            await self._touch_company(
                uow=uow,
                company_id=company_id,
                source=source,
                row=row,
                projected=projected,
                index=index,
            )
        company_decision = ImportEntityDecision.create(
            import_session_id=session_id,
            raw_import_row_id=row.id,
            entity_type=ImportEntityType.COMPANY,
            candidate_entity_id=company_id,
            decision=company_match.decision,
            confidence=company_match.confidence,
            reason_codes=company_match.reason_codes,
        )
        resolved_company_id = (
            company_id
            if company_match.decision
            in {
                ImportEntityDecisionKind.AUTO_CREATE,
                ImportEntityDecisionKind.AUTO_MERGE,
            }
            else None
        )

        contact_decision: ImportEntityDecision | None = None
        contact_id: UUID | None = None
        if projected.has_contact_data:
            contact_match = self._matcher.match_contact(
                projected,
                company_id=resolved_company_id,
                contacts=index.contacts,
                email_index=index.email_index,
                linkedin_index=index.linkedin_index,
            )
            contact_id = contact_match.candidate_entity_id
            if contact_match.decision is ImportEntityDecisionKind.AUTO_CREATE:
                try:
                    contact_id = await self._create_contact(
                        uow=uow,
                        company_id=resolved_company_id,
                        source=source,
                        row=row,
                        projected=projected,
                        index=index,
                    )
                except (DomainError, ValueError):
                    contact_match = dataclasses.replace(
                        contact_match,
                        decision=ImportEntityDecisionKind.REJECTED,
                        candidate_entity_id=None,
                        confidence=0.0,
                        reason_codes=(*contact_match.reason_codes, "contact_value_invalid"),
                    )
                    contact_id = None
            contact_decision = ImportEntityDecision.create(
                import_session_id=session_id,
                raw_import_row_id=row.id,
                entity_type=ImportEntityType.CONTACT,
                candidate_entity_id=contact_id,
                decision=contact_match.decision,
                confidence=contact_match.confidence,
                reason_codes=contact_match.reason_codes,
            )
        resolved_contact_id = (
            contact_id
            if contact_decision is not None
            and contact_decision.decision
            in {
                ImportEntityDecisionKind.AUTO_CREATE,
                ImportEntityDecisionKind.AUTO_MERGE,
            }
            else None
        )

        link_created = False
        if resolved_company_id is not None and resolved_contact_id is not None:
            link_created = await self._link_contact(
                uow=uow,
                company_id=resolved_company_id,
                contact_id=resolved_contact_id,
                row=row,
                projected=projected,
                index=index,
            )
        decisions = (company_decision,) + ((contact_decision,) if contact_decision else ())
        await uow.import_resolution.add_decisions(decisions)
        failed = company_decision.decision is ImportEntityDecisionKind.REJECTED or (
            contact_decision is not None
            and contact_decision.decision is ImportEntityDecisionKind.REJECTED
        )
        resolution.record_row(
            company_decision=company_decision.decision,
            contact_decision=contact_decision.decision if contact_decision else None,
            company_contact_created=link_created,
            failed=failed,
        )

    async def _load_session(self, session_id: UUID) -> tuple[ImportSession, dict[str, str]]:
        async with self._uow_factory() as uow:
            session = await uow.bulk_import.get_session(session_id)
            if session is None:
                raise ResourceNotFoundError(f"import session not found: {session_id}")
            raw_mapping = session.mapping_json.get("logical_fields", {})
            mapping = (
                {str(key): str(value) for key, value in raw_mapping.items()}
                if isinstance(raw_mapping, dict)
                else {}
            )
            return session, mapping

    async def _load_index(self, session_id: UUID) -> tuple[_ResolutionIndex, set[UUID]]:
        async with self._uow_factory() as uow:
            company_candidates = await uow.import_resolution.list_company_candidates()
            profiles = await uow.import_resolution.list_company_profiles()
            identities = await uow.import_resolution.list_external_identities()
            contact_candidates = await uow.import_resolution.list_contact_candidates()
            links = await uow.import_resolution.list_company_contacts()
            processed = await uow.import_resolution.list_processed_row_ids(session_id)
        contacts = {candidate.contact_id: candidate for candidate in contact_candidates}
        return (
            _ResolutionIndex(
                companies={candidate.company_id: candidate for candidate in company_candidates},
                profiles={profile.company_id: profile for profile in profiles},
                external_identities={
                    (identity.source, identity.external_id): identity for identity in identities
                },
                contacts=contacts,
                email_index={
                    email: candidate.contact_id
                    for candidate in contact_candidates
                    for email in candidate.emails
                },
                linkedin_index={
                    url: candidate.contact_id
                    for candidate in contact_candidates
                    for url in candidate.linkedin_urls
                },
                company_contacts={(link.company_id, link.contact_id): link for link in links},
                dirty_profile_ids=set(),
                dirty_identity_keys=set(),
                dirty_company_contact_keys=set(),
            ),
            processed,
        )

    async def _create_company(
        self,
        *,
        uow: ImportResolutionUnitOfWork,
        source: str,
        row: RawImportRow,
        projected: ProjectedImportRow,
        index: _ResolutionIndex,
    ) -> UUID:
        if projected.company_name is None or projected.normalized_company_name is None:
            raise DomainError("company name is required")
        website = _website(projected.website)
        company = Company.create(CompanyName(projected.company_name), website)
        company.add_source(_source_reference(source, row))
        await uow.companies.add(company)
        profile = CompanyResolutionProfile(
            company_id=company.id,
            normalized_name=projected.normalized_company_name,
            normalized_domain=projected.normalized_domain,
            normalized_address=projected.normalized_address,
            company_type=projected.company_type,
            normalized_phone=projected.normalized_company_phone,
            first_seen_at=row.created_at,
            last_seen_at=row.created_at,
            source_import_row_id=row.id,
            created_at=row.created_at,
            updated_at=row.created_at,
        )
        await uow.import_resolution.add_company_profile(profile)
        index.profiles[company.id] = profile
        index.companies[company.id] = _company_candidate(company, profile)
        await self._record_external_identity(
            uow=uow,
            company_id=company.id,
            source=source,
            external_id=projected.external_company_id,
            seen_at=row.created_at,
            index=index,
        )
        return company.id

    async def _touch_company(
        self,
        *,
        uow: ImportResolutionUnitOfWork,
        company_id: UUID,
        source: str,
        row: RawImportRow,
        projected: ProjectedImportRow,
        index: _ResolutionIndex,
    ) -> None:
        candidate = index.companies[company_id]
        profile = index.profiles.get(company_id)
        if profile is None:
            profile = CompanyResolutionProfile(
                company_id=company_id,
                normalized_name=(
                    projected.normalized_company_name or candidate.normalized_name
                ),
                normalized_domain=projected.normalized_domain or candidate.normalized_domain,
                normalized_address=projected.normalized_address,
                company_type=projected.company_type,
                normalized_phone=projected.normalized_company_phone,
                first_seen_at=row.created_at,
                last_seen_at=row.created_at,
                source_import_row_id=row.id,
                created_at=row.created_at,
                updated_at=row.created_at,
            )
            await uow.import_resolution.add_company_profile(profile)
        else:
            profile = profile.seen_again(
                normalized_name=projected.normalized_company_name or profile.normalized_name,
                normalized_domain=projected.normalized_domain,
                normalized_address=projected.normalized_address,
                company_type=projected.company_type,
                normalized_phone=projected.normalized_company_phone,
                seen_at=row.created_at,
            )
            index.dirty_profile_ids.add(company_id)
        index.profiles[company_id] = profile
        index.companies[company_id] = CompanyResolutionCandidate(
            company_id=company_id,
            canonical_name=candidate.canonical_name,
            normalized_name=profile.normalized_name,
            normalized_domain=profile.normalized_domain,
            normalized_address=profile.normalized_address,
            company_type=profile.company_type,
            normalized_phone=profile.normalized_phone,
        )
        await self._record_external_identity(
            uow=uow,
            company_id=company_id,
            source=source,
            external_id=projected.external_company_id,
            seen_at=row.created_at,
            index=index,
        )

    async def _record_external_identity(
        self,
        *,
        uow: ImportResolutionUnitOfWork,
        company_id: UUID,
        source: str,
        external_id: str | None,
        seen_at: datetime,
        index: _ResolutionIndex,
    ) -> None:
        if not external_id:
            return
        key = (source, external_id)
        existing = index.external_identities.get(key)
        if existing is None:
            identity = CompanyExternalIdentity.create(
                company_id=company_id,
                source=source,
                external_id=external_id,
                seen_at=seen_at,
            )
            await uow.import_resolution.add_external_identity(identity)
        else:
            identity = existing.seen_again(seen_at)
            index.dirty_identity_keys.add(key)
        index.external_identities[key] = identity

    async def _create_contact(
        self,
        *,
        uow: ImportResolutionUnitOfWork,
        company_id: UUID | None,
        source: str,
        row: RawImportRow,
        projected: ProjectedImportRow,
        index: _ResolutionIndex,
    ) -> UUID:
        if projected.contact_name is None:
            raise DomainError("contact name is required")
        name = PersonName(projected.contact_name)
        title = JobTitle(projected.contact_title) if projected.contact_title else None
        contact = (
            Contact.create_for_company(company_id, name, title)
            if company_id is not None
            else Contact.create_unassigned(name, title)
        )
        source_reference = _source_reference(source, row)
        contact.add_source(source_reference)
        department, seniority = _legacy_role(projected.role_category, projected.seniority)
        if department is not Department.UNKNOWN or seniority is not SeniorityLevel.UNKNOWN:
            contact.classify_role(department, seniority)
        if projected.contact_email:
            contact.add_channel(
                ContactChannel(
                    channel_type=ContactChannelType.EMAIL,
                    normalized_value=projected.contact_email,
                    display_value=projected.contact_email,
                    source_reference=source_reference,
                )
            )
        if projected.normalized_linkedin and projected.contact_linkedin:
            contact.add_channel(
                ContactChannel(
                    channel_type=ContactChannelType.LINKEDIN,
                    normalized_value=projected.normalized_linkedin,
                    display_value=projected.contact_linkedin,
                    source_reference=source_reference,
                )
            )
        if projected.normalized_contact_phone and projected.contact_phone:
            contact.add_channel(
                ContactChannel(
                    channel_type=ContactChannelType.PHONE,
                    normalized_value=projected.normalized_contact_phone,
                    display_value=projected.contact_phone,
                    source_reference=source_reference,
                )
            )
        try:
            contact.activate()
        except InvalidStateTransition:
            pass
        await uow.contacts.add(contact)
        candidate = ContactIdentityCandidate(
            contact_id=contact.id,
            display_name=contact.name.value,
            normalized_name=contact.name.normalized,
            normalized_title=contact.title.normalized if contact.title else None,
            emails=(projected.contact_email,) if projected.contact_email else (),
            linkedin_urls=(projected.normalized_linkedin,) if projected.normalized_linkedin else (),
            company_ids=(company_id,) if company_id is not None else (),
        )
        index.contacts[contact.id] = candidate
        if projected.contact_email:
            index.email_index[projected.contact_email] = contact.id
        if projected.normalized_linkedin:
            index.linkedin_index[projected.normalized_linkedin] = contact.id
        return contact.id

    async def _link_contact(
        self,
        *,
        uow: ImportResolutionUnitOfWork,
        company_id: UUID,
        contact_id: UUID,
        row: RawImportRow,
        projected: ProjectedImportRow,
        index: _ResolutionIndex,
    ) -> bool:
        key = (company_id, contact_id)
        role_category = (
            ImportRoleCategory.GENERAL_DEPARTMENT
            if projected.is_department_contact
            and projected.role_category is ImportRoleCategory.UNKNOWN
            else projected.role_category
        )
        existing = index.company_contacts.get(key)
        if existing is None:
            link = CompanyContact.create(
                company_id=company_id,
                contact_id=contact_id,
                raw_title=projected.contact_title,
                role_category=role_category,
                seniority=projected.seniority,
                is_department_contact=projected.is_department_contact,
                source_import_row_id=row.id,
                seen_at=row.created_at,
            )
            await uow.import_resolution.add_company_contact(link)
            created = True
        else:
            link = existing.seen_again(
                raw_title=projected.contact_title,
                role_category=role_category,
                seniority=projected.seniority,
                is_department_contact=projected.is_department_contact,
                seen_at=row.created_at,
            )
            index.dirty_company_contact_keys.add(key)
            created = False
        index.company_contacts[key] = link
        candidate = index.contacts.get(contact_id)
        if candidate is not None and company_id not in candidate.company_ids:
            index.contacts[contact_id] = ContactIdentityCandidate(
                contact_id=candidate.contact_id,
                display_name=candidate.display_name,
                normalized_name=candidate.normalized_name,
                normalized_title=candidate.normalized_title,
                emails=candidate.emails,
                linkedin_urls=candidate.linkedin_urls,
                company_ids=(*candidate.company_ids, company_id),
            )
        return created

    @staticmethod
    async def _flush_index_changes(
        uow: ImportResolutionUnitOfWork,
        index: _ResolutionIndex,
    ) -> None:
        if (
            index.dirty_profile_ids
            or index.dirty_identity_keys
            or index.dirty_company_contact_keys
        ):
            await uow.flush()
        await uow.import_resolution.update_company_profiles(
            tuple(index.profiles[company_id] for company_id in index.dirty_profile_ids)
        )
        await uow.import_resolution.update_external_identities(
            tuple(index.external_identities[key] for key in index.dirty_identity_keys)
        )
        await uow.import_resolution.update_company_contacts(
            tuple(index.company_contacts[key] for key in index.dirty_company_contact_keys)
        )


class ImportResolutionQueryWorkflow:
    def __init__(self, uow_factory: ImportResolutionUowFactory) -> None:
        self._uow_factory = uow_factory

    async def get(self, session_id: UUID) -> tuple[ImportResolution, ImportProcessingJob | None]:
        async with self._uow_factory() as uow:
            resolution = await uow.import_resolution.get_resolution(session_id)
            if resolution is None:
                raise ResourceNotFoundError(f"import resolution not found: {session_id}")
            job = await uow.import_processing_jobs.get_latest_for_session(session_id)
            return resolution, job

    async def list_decisions(
        self,
        *,
        session_id: UUID,
        entity_type: ImportEntityType | None,
        review_status: ImportEntityReviewStatus | None,
        min_confidence: float | None,
        max_confidence: float | None,
        page: int,
        limit: int,
    ) -> ImportDecisionPage:
        async with self._uow_factory() as uow:
            if await uow.import_resolution.get_resolution(session_id) is None:
                raise ResourceNotFoundError(f"import resolution not found: {session_id}")
            decisions, total = await uow.import_resolution.list_decisions(
                session_id=session_id,
                entity_type=entity_type,
                review_status=review_status,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                offset=(page - 1) * limit,
                limit=limit,
            )
            return ImportDecisionPage(
                session_id=session_id,
                page=page,
                limit=limit,
                total=total,
                decisions=tuple(decisions),
            )


class ImportEntityReviewWorkflow:
    def __init__(self, uow_factory: ImportResolutionUowFactory) -> None:
        self._uow_factory = uow_factory
        self._projector = RawImportProjector()

    async def review(
        self,
        decision_id: UUID,
        *,
        action: ImportReviewAction,
        reviewed_by: str,
    ) -> ImportEntityDecision:
        async with self._uow_factory() as uow:
            decision = await uow.import_resolution.get_decision_for_update(decision_id)
            if decision is None:
                raise ResourceNotFoundError(f"import entity decision not found: {decision_id}")
            if decision.review_status is ImportEntityReviewStatus.REVIEWED:
                expected = {
                    ImportReviewAction.MERGE: ImportEntityDecisionKind.MANUAL_MERGE,
                    ImportReviewAction.KEEP_SEPARATE: ImportEntityDecisionKind.KEEP_SEPARATE,
                    ImportReviewAction.REJECT: ImportEntityDecisionKind.REJECTED,
                }[action]
                if decision.decision is expected:
                    return decision
                raise ApplicationConflictError("entity decision was reviewed differently")
            row = await uow.bulk_import.get_row(decision.raw_import_row_id)
            session = await uow.bulk_import.get_session(decision.import_session_id)
            resolution = await uow.import_resolution.get_resolution_for_update(
                decision.import_session_id
            )
            if row is None or session is None or resolution is None:
                raise RuntimeError("entity review audit chain is incomplete")
            raw_mapping = session.mapping_json.get("logical_fields", {})
            mapping = (
                {str(key): str(value) for key, value in raw_mapping.items()}
                if isinstance(raw_mapping, dict)
                else {}
            )
            projected = self._projector.project(row.raw_payload, mapping=mapping)
            candidate_id = decision.candidate_entity_id
            if action is ImportReviewAction.KEEP_SEPARATE:
                if decision.entity_type is ImportEntityType.COMPANY:
                    candidate_id = await self._create_separate_company(
                        uow, session.source, row, projected
                    )
                else:
                    company_id = await self._resolved_company_id(uow, decision, row.id)
                    candidate_id = await self._create_separate_contact(
                        uow, company_id, session.source, row, projected
                    )
            elif action is ImportReviewAction.MERGE:
                if candidate_id is None:
                    raise ApplicationConflictError("merge review has no candidate entity")
                if decision.entity_type is ImportEntityType.COMPANY:
                    await self._merge_company(
                        uow, candidate_id, session.source, row, projected
                    )
                else:
                    await self._merge_contact(
                        uow, candidate_id, session.source, row, projected
                    )
            reviewed = decision.review(
                action=action,
                candidate_entity_id=(None if action is ImportReviewAction.REJECT else candidate_id),
                reviewed_by=reviewed_by,
            )
            await uow.import_resolution.save_decision(reviewed)
            link_created = await self._link_after_review(
                uow=uow,
                decision=reviewed,
                row=row,
                projected=projected,
            )
            resolution.record_review(
                entity_type=decision.entity_type,
                action=action,
                company_contact_created=link_created,
            )
            await uow.import_resolution.save_resolution(resolution)
            await uow.commit()
            return reviewed

    async def _create_separate_company(
        self,
        uow: ImportResolutionUnitOfWork,
        source: str,
        row: RawImportRow,
        projected: ProjectedImportRow,
    ) -> UUID:
        if projected.company_name is None or projected.normalized_company_name is None:
            raise ApplicationConflictError("reviewed row has no valid company name")
        company = Company.create(CompanyName(projected.company_name), _website(projected.website))
        company.add_source(_source_reference(source, row))
        await uow.companies.add(company)
        profile = CompanyResolutionProfile(
            company_id=company.id,
            normalized_name=projected.normalized_company_name,
            normalized_domain=projected.normalized_domain,
            normalized_address=projected.normalized_address,
            company_type=projected.company_type,
            normalized_phone=projected.normalized_company_phone,
            first_seen_at=row.created_at,
            last_seen_at=row.created_at,
            source_import_row_id=row.id,
            created_at=row.created_at,
            updated_at=row.created_at,
        )
        await uow.import_resolution.add_company_profile(profile)
        if projected.external_company_id:
            await uow.import_resolution.add_external_identity(
                CompanyExternalIdentity.create(
                    company_id=company.id,
                    source=source,
                    external_id=projected.external_company_id,
                    seen_at=row.created_at,
                )
            )
        return company.id

    async def _merge_company(
        self,
        uow: ImportResolutionUnitOfWork,
        company_id: UUID,
        source: str,
        row: RawImportRow,
        projected: ProjectedImportRow,
    ) -> None:
        company = await uow.companies.get_by_id(company_id)
        if company is None:
            raise ApplicationConflictError("company merge candidate no longer exists")
        company.add_source(_source_reference(source, row))
        await uow.companies.save(company)
        profile = await uow.import_resolution.get_company_profile(company_id)
        if profile is None:
            normalized_name = projected.normalized_company_name or company.name.normalized
            profile = CompanyResolutionProfile(
                company_id=company_id,
                normalized_name=normalized_name,
                normalized_domain=(
                    projected.normalized_domain
                    or (company.website.host if company.website is not None else None)
                ),
                normalized_address=projected.normalized_address,
                company_type=projected.company_type,
                normalized_phone=projected.normalized_company_phone,
                first_seen_at=row.created_at,
                last_seen_at=row.created_at,
                source_import_row_id=row.id,
                created_at=row.created_at,
                updated_at=row.created_at,
            )
            await uow.import_resolution.add_company_profile(profile)
        else:
            await uow.import_resolution.save_company_profile(
                profile.seen_again(
                    normalized_name=(
                        projected.normalized_company_name or profile.normalized_name
                    ),
                    normalized_domain=projected.normalized_domain,
                    normalized_address=projected.normalized_address,
                    company_type=projected.company_type,
                    normalized_phone=projected.normalized_company_phone,
                    seen_at=row.created_at,
                )
            )
        if not projected.external_company_id:
            return
        identities = await uow.import_resolution.list_external_identities()
        existing = next(
            (
                identity
                for identity in identities
                if identity.source == source.strip().lower()
                and identity.external_id == projected.external_company_id
            ),
            None,
        )
        if existing is not None and existing.company_id != company_id:
            raise ApplicationConflictError(
                "external company identity already belongs to another company"
            )
        if existing is None:
            await uow.import_resolution.add_external_identity(
                CompanyExternalIdentity.create(
                    company_id=company_id,
                    source=source,
                    external_id=projected.external_company_id,
                    seen_at=row.created_at,
                )
            )
        else:
            await uow.import_resolution.save_external_identity(
                existing.seen_again(row.created_at)
            )

    async def _create_separate_contact(
        self,
        uow: ImportResolutionUnitOfWork,
        company_id: UUID | None,
        source: str,
        row: RawImportRow,
        projected: ProjectedImportRow,
    ) -> UUID:
        if projected.contact_name is None:
            raise ApplicationConflictError("reviewed row has no valid contact name")
        title = JobTitle(projected.contact_title) if projected.contact_title else None
        contact = (
            Contact.create_for_company(company_id, PersonName(projected.contact_name), title)
            if company_id is not None
            else Contact.create_unassigned(PersonName(projected.contact_name), title)
        )
        source_reference = _source_reference(source, row)
        contact.add_source(source_reference)
        if projected.contact_email:
            contact.add_channel(
                ContactChannel(
                    channel_type=ContactChannelType.EMAIL,
                    normalized_value=projected.contact_email,
                    display_value=projected.contact_email,
                    source_reference=source_reference,
                )
            )
        if projected.normalized_linkedin and projected.contact_linkedin:
            contact.add_channel(
                ContactChannel(
                    channel_type=ContactChannelType.LINKEDIN,
                    normalized_value=projected.normalized_linkedin,
                    display_value=projected.contact_linkedin,
                    source_reference=source_reference,
                )
            )
        if projected.normalized_contact_phone and projected.contact_phone:
            contact.add_channel(
                ContactChannel(
                    channel_type=ContactChannelType.PHONE,
                    normalized_value=projected.normalized_contact_phone,
                    display_value=projected.contact_phone,
                    source_reference=source_reference,
                )
            )
        department, seniority = _legacy_role(
            projected.role_category, projected.seniority
        )
        if department is not Department.UNKNOWN or seniority is not SeniorityLevel.UNKNOWN:
            contact.classify_role(department, seniority)
        try:
            contact.activate()
        except InvalidStateTransition:
            pass
        await uow.contacts.add(contact)
        return contact.id

    async def _merge_contact(
        self,
        uow: ImportResolutionUnitOfWork,
        contact_id: UUID,
        source: str,
        row: RawImportRow,
        projected: ProjectedImportRow,
    ) -> None:
        contact = await uow.contacts.get_by_id(contact_id)
        if contact is None:
            raise ApplicationConflictError("contact merge candidate no longer exists")
        source_reference = _source_reference(source, row)
        contact.add_source(source_reference)
        existing_channels = {
            (channel.channel_type, channel.normalized_value)
            for channel in contact.channels
        }
        projected_channels = (
            (
                ContactChannelType.EMAIL,
                projected.contact_email,
                projected.contact_email,
            ),
            (
                ContactChannelType.LINKEDIN,
                projected.normalized_linkedin,
                projected.contact_linkedin,
            ),
            (
                ContactChannelType.PHONE,
                projected.normalized_contact_phone,
                projected.contact_phone,
            ),
        )
        for channel_type, normalized_value, display_value in projected_channels:
            if (
                normalized_value
                and display_value
                and (channel_type, normalized_value) not in existing_channels
            ):
                contact.add_channel(
                    ContactChannel(
                        channel_type=channel_type,
                        normalized_value=normalized_value,
                        display_value=display_value,
                        source_reference=source_reference,
                    )
                )
        await uow.contacts.save(contact)

    async def _resolved_company_id(
        self,
        uow: ImportResolutionUnitOfWork,
        decision: ImportEntityDecision,
        row_id: UUID,
    ) -> UUID | None:
        company_decision = await uow.import_resolution.get_row_decision(
            session_id=decision.import_session_id,
            raw_import_row_id=row_id,
            entity_type=ImportEntityType.COMPANY,
        )
        return _resolved_entity_id(company_decision)

    async def _link_after_review(
        self,
        *,
        uow: ImportResolutionUnitOfWork,
        decision: ImportEntityDecision,
        row: RawImportRow,
        projected: ProjectedImportRow,
    ) -> bool:
        company_decision = (
            decision
            if decision.entity_type is ImportEntityType.COMPANY
            else await uow.import_resolution.get_row_decision(
                session_id=decision.import_session_id,
                raw_import_row_id=row.id,
                entity_type=ImportEntityType.COMPANY,
            )
        )
        contact_decision = (
            decision
            if decision.entity_type is ImportEntityType.CONTACT
            else await uow.import_resolution.get_row_decision(
                session_id=decision.import_session_id,
                raw_import_row_id=row.id,
                entity_type=ImportEntityType.CONTACT,
            )
        )
        company_id = _resolved_entity_id(company_decision)
        contact_id = _resolved_entity_id(contact_decision)
        if company_id is None or contact_id is None:
            return False
        existing_links = await uow.import_resolution.list_company_contacts()
        existing = next(
            (
                link
                for link in existing_links
                if link.company_id == company_id and link.contact_id == contact_id
            ),
            None,
        )
        role_category = (
            ImportRoleCategory.GENERAL_DEPARTMENT
            if projected.is_department_contact
            and projected.role_category is ImportRoleCategory.UNKNOWN
            else projected.role_category
        )
        if existing is not None:
            await uow.import_resolution.save_company_contact(
                existing.seen_again(
                    raw_title=projected.contact_title,
                    role_category=role_category,
                    seniority=projected.seniority,
                    is_department_contact=projected.is_department_contact,
                    seen_at=row.created_at,
                )
            )
            return False
        await uow.import_resolution.add_company_contact(
            CompanyContact.create(
                company_id=company_id,
                contact_id=contact_id,
                raw_title=projected.contact_title,
                role_category=role_category,
                seniority=projected.seniority,
                is_department_contact=projected.is_department_contact,
                source_import_row_id=row.id,
                seen_at=row.created_at,
            )
        )
        return True


def _resolved_entity_id(decision: ImportEntityDecision | None) -> UUID | None:
    if decision is None:
        return None
    if decision.decision in {
        ImportEntityDecisionKind.AUTO_CREATE,
        ImportEntityDecisionKind.AUTO_MERGE,
        ImportEntityDecisionKind.MANUAL_MERGE,
        ImportEntityDecisionKind.KEEP_SEPARATE,
    }:
        return decision.candidate_entity_id
    return None


def _source_reference(source: str, row: RawImportRow) -> SourceReference:
    return SourceReference(
        source=source,
        reference=f"import-session:{row.import_session_id}:row:{row.id}",
        retrieved_at=row.created_at,
    )


def _website(value: str | None) -> WebsiteUrl | None:
    if value is None:
        return None
    candidate = value if "://" in value else f"https://{value}"
    return WebsiteUrl(candidate)


def _company_candidate(
    company: Company, profile: CompanyResolutionProfile
) -> CompanyResolutionCandidate:
    return CompanyResolutionCandidate(
        company_id=company.id,
        canonical_name=company.name.value,
        normalized_name=profile.normalized_name,
        normalized_domain=profile.normalized_domain,
        normalized_address=profile.normalized_address,
        company_type=profile.company_type,
        normalized_phone=profile.normalized_phone,
    )


def _legacy_role(
    category: ImportRoleCategory, seniority: str
) -> tuple[Department, SeniorityLevel]:
    department = {
        ImportRoleCategory.OWNER_FOUNDER: Department.EXECUTIVE,
        ImportRoleCategory.EXECUTIVE: Department.EXECUTIVE,
        ImportRoleCategory.PROCUREMENT: Department.PROCUREMENT,
        ImportRoleCategory.SUPPLY_CHAIN: Department.SUPPLY_CHAIN,
        ImportRoleCategory.LOGISTICS: Department.LOGISTICS,
        ImportRoleCategory.OPERATIONS: Department.OPERATIONS,
        ImportRoleCategory.IMPORT_EXPORT: Department.LOGISTICS,
        ImportRoleCategory.WAREHOUSE: Department.OPERATIONS,
        ImportRoleCategory.SALES: Department.SALES_MARKETING,
        ImportRoleCategory.GENERAL_DEPARTMENT: Department.OTHER,
        ImportRoleCategory.IRRELEVANT: Department.OTHER,
        ImportRoleCategory.UNKNOWN: Department.UNKNOWN,
    }[category]
    seniority_level = {
        "c_level": SeniorityLevel.C_LEVEL,
        "vp": SeniorityLevel.VP,
        "director": SeniorityLevel.DIRECTOR,
        "head": SeniorityLevel.HEAD,
        "manager": SeniorityLevel.MANAGER,
        "specialist": SeniorityLevel.SPECIALIST,
        "unknown": SeniorityLevel.UNKNOWN,
    }[seniority]
    return department, seniority_level
