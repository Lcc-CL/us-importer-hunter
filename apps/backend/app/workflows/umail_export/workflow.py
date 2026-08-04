"""Deterministic B-prospect selection, suppression, preview, and CSV rendering."""

import codecs
import csv
import hashlib
import io
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.domain.exceptions import DuplicateOperation
from app.domain.prospect_routing import (
    ProspectRouteReviewStatus,
    ProspectRoutingRunStatus,
    ProspectTier,
)
from app.domain.repositories import UmailExportUnitOfWork
from app.domain.umail_export import (
    UMAIL_EXPORT_MAPPING_VERSION,
    SuppressionEntry,
    UmailExportBatch,
    UmailExportCompanyCandidate,
    UmailExportContactCandidate,
    UmailExportEmailCandidate,
    UmailExportPhoneCandidate,
    UmailExportRow,
    UmailExportRowStatus,
)
from app.domain.umail_export.models import normalize_suppression_company
from app.shared.exceptions import (
    ApplicationConflictError,
    InvalidInputError,
    ResourceNotFoundError,
)

UmailUowFactory = Callable[[], UmailExportUnitOfWork]
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CSV_COLUMNS = (
    "email",
    "first_name",
    "last_name",
    "company",
    "job_title",
    "role",
    "website",
    "phone",
    "country",
    "prospect_score",
    "route_reasons",
    "campaign",
    "export_batch_id",
    "export_row_id",
)
ROLE_PRIORITY = {
    "procurement": 0,
    "supply_chain": 1,
    "logistics": 2,
    "operations": 3,
    "import_export": 4,
    "executive": 5,
    "owner_founder": 6,
    "warehouse": 7,
    "general_department": 8,
    "unknown": 9,
    "sales": 10,
    "irrelevant": 11,
}
SENIORITY_PRIORITY = {
    "c_level": 0,
    "owner": 0,
    "founder": 0,
    "vp": 1,
    "director": 2,
    "head": 3,
    "manager": 4,
    "specialist": 5,
    "unknown": 6,
}
VERIFICATION_PRIORITY = {
    "manually_verified": 0,
    "source_verified": 1,
    "unverified": 2,
    "invalid": 3,
}


@dataclass(frozen=True)
class SuppressionEntryPage:
    page: int
    limit: int
    total: int
    entries: tuple[SuppressionEntry, ...]


@dataclass(frozen=True)
class UmailExportSubmission:
    batch: UmailExportBatch
    rows: tuple[UmailExportRow, ...]
    reused: bool


@dataclass(frozen=True)
class UmailExportDownload:
    batch: UmailExportBatch
    content: bytes
    filename: str


class SuppressionWorkflow:
    def __init__(self, uow_factory: UmailUowFactory) -> None:
        self._uow_factory = uow_factory

    async def create(
        self,
        *,
        email: str | None,
        domain: str | None,
        company: str | None,
        reason: str,
        source: str,
        created_by: str,
    ) -> SuppressionEntry:
        entry = SuppressionEntry.create(
            email=email,
            domain=domain,
            company=company,
            reason=reason,
            source=source,
            created_by=created_by,
        )
        async with self._uow_factory() as uow:
            await uow.umail_exports.add_suppression(entry)
            await uow.commit()
        return entry

    async def list(
        self, *, active: bool | None, page: int, limit: int
    ) -> SuppressionEntryPage:
        async with self._uow_factory() as uow:
            entries, total = await uow.umail_exports.list_suppressions(
                active=active,
                offset=(page - 1) * limit,
                limit=limit,
            )
        return SuppressionEntryPage(
            page=page,
            limit=limit,
            total=total,
            entries=tuple(entries),
        )

    async def deactivate(self, entry_id: UUID, *, deactivated_by: str) -> SuppressionEntry:
        async with self._uow_factory() as uow:
            entry = await uow.umail_exports.get_suppression_for_update(entry_id)
            if entry is None:
                raise ResourceNotFoundError(f"suppression entry not found: {entry_id}")
            deactivated = entry.deactivate(deactivated_by=deactivated_by)
            await uow.umail_exports.save_suppression(deactivated)
            await uow.commit()
            return deactivated


class UmailExportWorkflow:
    def __init__(self, uow_factory: UmailUowFactory) -> None:
        self._uow_factory = uow_factory

    async def prepare(
        self,
        *,
        routing_run_id: UUID,
        company_ids: tuple[UUID, ...],
        campaign: str,
    ) -> UmailExportSubmission:
        clean_campaign = campaign.strip()
        if not clean_campaign:
            raise InvalidInputError(
                code="UMAIL_CAMPAIGN_REQUIRED",
                message="campaign is required",
            )
        unique_ids = tuple(dict.fromkeys(company_ids))
        if not unique_ids:
            raise InvalidInputError(
                code="UMAIL_COMPANIES_REQUIRED",
                message="at least one company is required",
            )
        if len(unique_ids) != len(company_ids):
            raise InvalidInputError(
                code="UMAIL_COMPANIES_DUPLICATED",
                message="company_ids must not contain duplicates",
            )
        if len(unique_ids) > 500:
            raise InvalidInputError(
                code="UMAIL_COMPANY_LIMIT_EXCEEDED",
                message="an export batch can contain at most 500 companies",
            )
        async with self._uow_factory() as uow:
            run = await uow.prospect_routing.get_run(routing_run_id)
            if run is None:
                raise ResourceNotFoundError(
                    f"prospect routing run not found: {routing_run_id}"
                )
            if run.status not in {
                ProspectRoutingRunStatus.COMPLETED,
                ProspectRoutingRunStatus.PARTIAL_COMPLETED,
            }:
                raise ApplicationConflictError(
                    "Umail export requires a completed routing run"
                )
            candidates = await uow.umail_exports.load_b_candidates(
                routing_run_id=routing_run_id,
                execution_generation=run.execution_generation,
                company_ids=unique_ids,
            )
            suppressions = await uow.umail_exports.list_active_suppressions()
            if len(candidates) != len(unique_ids):
                raise InvalidInputError(
                    code="UMAIL_COMPANY_OUTSIDE_RUN",
                    message="all company_ids must belong to the current routing generation",
                )
            invalid_routes = [
                candidate.company_id
                for candidate in candidates
                if candidate.effective_tier is not ProspectTier.B
                or candidate.review_status
                not in {
                    ProspectRouteReviewStatus.CONFIRMED,
                    ProspectRouteReviewStatus.OVERRIDDEN,
                }
            ]
            if invalid_routes:
                raise ApplicationConflictError(
                    "only confirmed or overridden effective-tier B routes may be exported"
                )
            selection_hash = _selection_hash(
                routing_run_id=routing_run_id,
                execution_generation=run.execution_generation,
                campaign=clean_campaign,
                candidates=candidates,
                suppressions=tuple(suppressions),
            )
            existing = await uow.umail_exports.find_batch_by_selection_hash(
                selection_hash
            )
            if existing is not None:
                existing_rows = await uow.umail_exports.list_rows(existing.id)
                return UmailExportSubmission(
                    batch=existing,
                    rows=tuple(existing_rows),
                    reused=True,
                )

        batch_id = uuid4()
        rows = _build_rows(
            batch_id=batch_id,
            candidates=candidates,
            suppressions=tuple(suppressions),
        )
        content = render_umail_csv(rows, campaign=clean_campaign)
        batch = UmailExportBatch.prepare(
            id=batch_id,
            routing_run_id=routing_run_id,
            execution_generation=run.execution_generation,
            campaign=clean_campaign,
            mapping_version=UMAIL_EXPORT_MAPPING_VERSION,
            selection_hash=selection_hash,
            rows=rows,
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        try:
            async with self._uow_factory() as uow:
                await uow.umail_exports.add_batch(batch, rows)
                await uow.commit()
        except DuplicateOperation:
            async with self._uow_factory() as uow:
                existing = await uow.umail_exports.find_batch_by_selection_hash(
                    selection_hash
                )
                if existing is None:
                    raise
                existing_rows = await uow.umail_exports.list_rows(existing.id)
                return UmailExportSubmission(
                    batch=existing,
                    rows=tuple(existing_rows),
                    reused=True,
                )
        return UmailExportSubmission(batch=batch, rows=rows, reused=False)

    async def get(self, batch_id: UUID) -> UmailExportSubmission:
        async with self._uow_factory() as uow:
            batch = await uow.umail_exports.get_batch(batch_id)
            if batch is None:
                raise ResourceNotFoundError(f"Umail export batch not found: {batch_id}")
            rows = await uow.umail_exports.list_rows(batch_id)
            return UmailExportSubmission(batch=batch, rows=tuple(rows), reused=True)

    async def download(self, batch_id: UUID) -> UmailExportDownload:
        async with self._uow_factory() as uow:
            batch = await uow.umail_exports.get_batch_for_update(batch_id)
            if batch is None:
                raise ResourceNotFoundError(f"Umail export batch not found: {batch_id}")
            rows = tuple(await uow.umail_exports.list_rows(batch_id))
            content = render_umail_csv(rows, campaign=batch.campaign)
            content_hash = hashlib.sha256(content).hexdigest()
            if content_hash != batch.content_sha256:
                raise ApplicationConflictError(
                    "persisted export rows no longer match the audited CSV hash"
                )
            batch.mark_downloaded()
            await uow.umail_exports.save_batch(batch)
            await uow.commit()
            return UmailExportDownload(
                batch=batch,
                content=content,
                filename=f"umail-export-{batch.id}.csv",
            )


def render_umail_csv(rows: tuple[UmailExportRow, ...], *, campaign: str) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        if row.status is not UmailExportRowStatus.READY:
            continue
        writer.writerow(
            (
                _formula_safe(row.email or ""),
                _formula_safe(row.first_name or ""),
                _formula_safe(row.last_name or ""),
                _formula_safe(row.company_name),
                _formula_safe(row.contact_title or ""),
                _formula_safe(row.contact_role or ""),
                _formula_safe(row.company_website or ""),
                _formula_safe(row.phone or ""),
                _formula_safe(row.country or ""),
                f"{row.pre_score:.2f}",
                _formula_safe(_stable_route_reasons(row.route_reasons)),
                _formula_safe(campaign),
                str(row.batch_id),
                str(row.id),
            )
        )
    return codecs.BOM_UTF8 + buffer.getvalue().encode("utf-8")


def _build_rows(
    *,
    batch_id: UUID,
    candidates: tuple[UmailExportCompanyCandidate, ...],
    suppressions: tuple[SuppressionEntry, ...],
) -> tuple[UmailExportRow, ...]:
    email_suppressions = {entry.email: entry for entry in suppressions if entry.email}
    domain_suppressions = {entry.domain: entry for entry in suppressions if entry.domain}
    company_suppressions = {
        entry.company: entry for entry in suppressions if entry.company
    }
    seen_emails: set[str] = set()
    rows: list[UmailExportRow] = []
    position = 0
    for company in candidates:
        company_suppression = company_suppressions.get(
            normalize_suppression_company(company.company_name)
        )
        contacts = _select_contacts(company.contacts)
        if not contacts:
            position += 1
            status = (
                UmailExportRowStatus.SUPPRESSED
                if company_suppression
                else UmailExportRowStatus.INVALID
            )
            exclusion_reason = (
                f"suppressed_company:{company_suppression.id}"
                if company_suppression
                else "no_contact"
            )
            rows.append(
                _new_row(
                    batch_id=batch_id,
                    position=position,
                    company=company,
                    contact=None,
                    email=None,
                    status=status,
                    reason=exclusion_reason,
                )
            )
            continue
        for contact in contacts:
            position += 1
            email_candidate = _select_email(contact.emails)
            email = email_candidate.normalized_value if email_candidate else None
            status = UmailExportRowStatus.READY
            reason: str | None = None
            if company_suppression is not None:
                status = UmailExportRowStatus.SUPPRESSED
                reason = f"suppressed_company:{company_suppression.id}"
            elif email_candidate is None:
                status = UmailExportRowStatus.INVALID
                reason = "no_email"
            elif (
                email_candidate.verification_status == "invalid"
                or not _valid_email(email_candidate.normalized_value)
            ):
                status = UmailExportRowStatus.INVALID
                reason = "invalid_email"
            else:
                domain = email_candidate.normalized_value.rsplit("@", 1)[1]
                suppression = email_suppressions.get(email_candidate.normalized_value)
                if suppression is not None:
                    status = UmailExportRowStatus.SUPPRESSED
                    reason = f"suppressed_email:{suppression.id}"
                else:
                    suppression = domain_suppressions.get(domain)
                    if suppression is not None:
                        status = UmailExportRowStatus.SUPPRESSED
                        reason = f"suppressed_domain:{suppression.id}"
                    elif email_candidate.normalized_value in seen_emails:
                        status = UmailExportRowStatus.DUPLICATE
                        reason = "duplicate_email"
                    else:
                        seen_emails.add(email_candidate.normalized_value)
            rows.append(
                _new_row(
                    batch_id=batch_id,
                    position=position,
                    company=company,
                    contact=contact,
                    email=email,
                    status=status,
                    reason=reason,
                )
            )
    return tuple(rows)


def _new_row(
    *,
    batch_id: UUID,
    position: int,
    company: UmailExportCompanyCandidate,
    contact: UmailExportContactCandidate | None,
    email: str | None,
    status: UmailExportRowStatus,
    reason: str | None,
) -> UmailExportRow:
    first_name, last_name = _split_contact_name(contact.name if contact else None)
    phone = _select_phone(contact.phones) if contact else None
    return UmailExportRow.create(
        batch_id=batch_id,
        position=position,
        company_id=company.company_id,
        contact_id=contact.contact_id if contact else None,
        company_name=company.company_name,
        company_website=company.company_website,
        contact_name=contact.name if contact else None,
        first_name=first_name,
        last_name=last_name,
        contact_title=contact.title if contact else None,
        contact_role=contact.role_category if contact else None,
        contact_seniority=contact.seniority if contact else None,
        is_department_contact=contact.is_department_contact if contact else False,
        email=email,
        phone=phone,
        country=company.country,
        route_review_status=company.review_status,
        pre_score=company.pre_score,
        route_reasons=company.route_reasons,
        status=status,
        exclusion_reason=reason,
    )


def _select_contacts(
    contacts: tuple[UmailExportContactCandidate, ...],
) -> tuple[UmailExportContactCandidate, ...]:
    ordered = sorted(
        contacts,
        key=lambda contact: (
            contact.is_department_contact,
            ROLE_PRIORITY.get(contact.role_category, 99),
            SENIORITY_PRIORITY.get(contact.seniority, 99),
            contact.name.casefold(),
            str(contact.contact_id),
        ),
    )
    return tuple(ordered[:2])


def _select_email(
    emails: tuple[UmailExportEmailCandidate, ...],
) -> UmailExportEmailCandidate | None:
    if not emails:
        return None
    return min(
        emails,
        key=lambda email: (
            VERIFICATION_PRIORITY.get(email.verification_status, 99),
            email.normalized_value,
        ),
    )


def _select_phone(phones: tuple[UmailExportPhoneCandidate, ...]) -> str | None:
    if not phones:
        return None
    selected = min(
        phones,
        key=lambda phone: (
            VERIFICATION_PRIORITY.get(phone.verification_status, 99),
            phone.normalized_value,
        ),
    )
    return selected.display_value.strip() or selected.normalized_value


def _split_contact_name(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    parts = value.strip().split(maxsplit=1)
    if not parts:
        return None, None
    return parts[0], parts[1] if len(parts) == 2 else None


def _stable_route_reasons(reasons: tuple[str, ...]) -> str:
    return json.dumps(list(reasons), ensure_ascii=False, separators=(",", ":"))


def _selection_hash(
    *,
    routing_run_id: UUID,
    execution_generation: int,
    campaign: str,
    candidates: tuple[UmailExportCompanyCandidate, ...],
    suppressions: tuple[SuppressionEntry, ...],
) -> str:
    payload = {
        "routing_run_id": str(routing_run_id),
        "execution_generation": execution_generation,
        "campaign": campaign,
        "mapping_version": UMAIL_EXPORT_MAPPING_VERSION,
        "companies": [
            {
                "company_id": str(company.company_id),
                "company_name": company.company_name,
                "website": company.company_website,
                "country": company.country,
                "pre_score": company.pre_score,
                "route_reasons": company.route_reasons,
                "tier": company.effective_tier.value if company.effective_tier else None,
                "review": company.review_status.value,
                "contacts": [
                    {
                        "contact_id": str(contact.contact_id),
                        "name": contact.name,
                        "title": contact.title,
                        "role": contact.role_category,
                        "seniority": contact.seniority,
                        "department": contact.is_department_contact,
                        "emails": [
                            {
                                "value": email.normalized_value,
                                "verification": email.verification_status,
                            }
                            for email in contact.emails
                        ],
                        "phones": [
                            {
                                "value": phone.normalized_value,
                                "display": phone.display_value,
                                "verification": phone.verification_status,
                            }
                            for phone in contact.phones
                        ],
                    }
                    for contact in company.contacts
                ],
            }
            for company in candidates
        ],
        "suppressions": [
            {
                "id": str(entry.id),
                "email": entry.email,
                "domain": entry.domain,
                "company": entry.company,
            }
            for entry in suppressions
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_email(value: str) -> bool:
    return len(value) <= 320 and EMAIL_PATTERN.fullmatch(value) is not None


def _formula_safe(value: str) -> str:
    if not value:
        return value
    stripped = value.lstrip()
    if stripped and stripped[0] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value
