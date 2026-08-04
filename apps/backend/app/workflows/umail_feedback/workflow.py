"""Parse, match, review, and apply offline Umail result CSV files."""

import dataclasses
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DuplicateOperation
from app.domain.repositories import UmailFeedbackUnitOfWork
from app.domain.umail_export import SuppressionEntry
from app.domain.umail_feedback import (
    ContactEngagementEvent,
    ContactEngagementEventType,
    FeedbackExportSnapshot,
    UmailResultImport,
    UmailResultImportStatus,
    UmailResultMatchStatus,
    UmailResultRow,
)
from app.services.umail_feedback import ParsedFeedbackCsv, UmailResultCsvIntake
from app.shared.exceptions import ApplicationConflictError, ResourceNotFoundError

UmailFeedbackUowFactory = Callable[[], UmailFeedbackUnitOfWork]
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MATCH_WINDOW = timedelta(days=180)
EMAIL_MATCH_CLOCK_SKEW = timedelta(days=1)
SUPPRESSION_REASONS = {
    ContactEngagementEventType.HARD_BOUNCED: "bounced",
    ContactEngagementEventType.UNSUBSCRIBED: "unsubscribed",
    ContactEngagementEventType.COMPLAINED: "complained",
}
EVENT_ALIASES = {
    "sent": ContactEngagementEventType.SENT,
    "send": ContactEngagementEventType.SENT,
    "delivered": ContactEngagementEventType.DELIVERED,
    "delivery": ContactEngagementEventType.DELIVERED,
    "hard_bounce": ContactEngagementEventType.HARD_BOUNCED,
    "hard_bounced": ContactEngagementEventType.HARD_BOUNCED,
    "soft_bounce": ContactEngagementEventType.SOFT_BOUNCED,
    "soft_bounced": ContactEngagementEventType.SOFT_BOUNCED,
    "bounce_unknown": ContactEngagementEventType.BOUNCE_UNKNOWN,
    "unknown_bounce": ContactEngagementEventType.BOUNCE_UNKNOWN,
    "unsubscribed": ContactEngagementEventType.UNSUBSCRIBED,
    "unsubscribe": ContactEngagementEventType.UNSUBSCRIBED,
    "opt_out": ContactEngagementEventType.UNSUBSCRIBED,
    "complained": ContactEngagementEventType.COMPLAINED,
    "complaint": ContactEngagementEventType.COMPLAINED,
    "spam_complaint": ContactEngagementEventType.COMPLAINED,
    "replied": ContactEngagementEventType.REPLIED,
    "reply": ContactEngagementEventType.REPLIED,
    "opened": ContactEngagementEventType.OPENED,
    "open": ContactEngagementEventType.OPENED,
    "clicked": ContactEngagementEventType.CLICKED,
    "click": ContactEngagementEventType.CLICKED,
}
HARD_BOUNCE_ALIASES = {"hard", "permanent", "hard_bounce", "hard_bounced"}
SOFT_BOUNCE_ALIASES = {"soft", "temporary", "transient", "soft_bounce", "soft_bounced"}


@dataclass(frozen=True)
class UmailResultSubmission:
    result_import: UmailResultImport
    reused: bool


@dataclass(frozen=True)
class UmailResultApplyOutcome:
    result_import: UmailResultImport
    reused: bool


@dataclass(frozen=True)
class UmailResultRowPage:
    page: int
    limit: int
    total: int
    rows: tuple[UmailResultRow, ...]


@dataclass(frozen=True)
class EngagementRateStatistics:
    total_events: int
    event_counts: dict[str, int]
    delivered_rate: float
    reply_rate: float
    hard_bounce_rate: float
    unsubscribe_rate: float
    complaint_rate: float


@dataclass(frozen=True)
class CompanyEngagementStatistics:
    company_id: UUID
    company_name: str
    event_counts: dict[str, int]


@dataclass(frozen=True)
class UmailFeedbackStatistics:
    result_import_id: UUID
    total_result_rows: int
    matched_rate: float
    rates: EngagementRateStatistics
    campaign_statistics: dict[str, dict[str, int]]
    route_statistics: dict[str, dict[str, int]]
    company_statistics: tuple[CompanyEngagementStatistics, ...]


@dataclass(frozen=True)
class _ParsedRow:
    row_number: int
    raw_payload: dict[str, Any]
    export_batch_id: UUID | None
    export_row_id: UUID | None
    normalized_email: str | None
    campaign: str | None
    event_type: ContactEngagementEventType | None
    occurred_at: datetime | None
    bounce_type: str | None
    message_id: str | None
    errors: tuple[str, ...]
    semantic_fingerprint: str


class UmailResultImportWorkflow:
    def __init__(
        self,
        uow_factory: UmailFeedbackUowFactory,
        *,
        csv_intake: UmailResultCsvIntake | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._csv_intake = csv_intake or UmailResultCsvIntake()

    async def upload(
        self,
        *,
        file: BinaryIO,
        source_filename: str,
        mapping: dict[str, str],
        created_by: str,
    ) -> UmailResultSubmission:
        parsed_file = self._csv_intake.parse(file, mapping=mapping)
        async with self._uow_factory() as uow:
            existing = await uow.umail_feedback.find_import_by_file_hash(
                parsed_file.file_sha256
            )
            if existing is not None:
                return UmailResultSubmission(result_import=existing, reused=True)

        result_import_id = uuid4()
        parsed_rows = _parse_rows(parsed_file)
        export_row_ids = tuple(
            dict.fromkeys(
                row.export_row_id for row in parsed_rows if row.export_row_id is not None
            )
        )
        emails = tuple(
            dict.fromkeys(
                row.normalized_email
                for row in parsed_rows
                if row.normalized_email is not None
            )
        )
        async with self._uow_factory() as uow:
            snapshots = await uow.umail_feedback.load_export_snapshots(
                export_row_ids=export_row_ids,
                emails=emails,
            )
            rows = _match_rows(
                result_import_id=result_import_id,
                parsed_rows=parsed_rows,
                snapshots=snapshots,
            )
            potential_events = _events_for_rows(rows, snapshots)
            existing_fingerprints = await uow.umail_feedback.existing_event_fingerprints(
                tuple(event.event_fingerprint for event in potential_events.values())
            )
            rows = _mark_event_duplicates(
                rows,
                potential_events=potential_events,
                existing_fingerprints=existing_fingerprints,
            )
            active_suppressions = await uow.umail_exports.list_active_suppressions()
            result_import = UmailResultImport.ready_for_review(
                source_filename=source_filename,
                file_sha256=parsed_file.file_sha256,
                mapping_snapshot_json=parsed_file.mapping_snapshot,
                rows=rows,
                projected_suppression_count=_projected_suppression_count(
                    rows,
                    snapshots=snapshots,
                    active_suppressions=active_suppressions,
                ),
                created_by=created_by,
            )
            try:
                await uow.umail_feedback.add_import(result_import, rows)
                await uow.commit()
            except DuplicateOperation:
                async with self._uow_factory() as retry_uow:
                    existing = await retry_uow.umail_feedback.find_import_by_file_hash(
                        parsed_file.file_sha256
                    )
                    if existing is None:
                        raise
                    return UmailResultSubmission(result_import=existing, reused=True)
        return UmailResultSubmission(result_import=result_import, reused=False)

    async def get(self, result_import_id: UUID) -> UmailResultImport:
        async with self._uow_factory() as uow:
            result_import = await uow.umail_feedback.get_import(result_import_id)
            if result_import is None:
                raise ResourceNotFoundError(
                    f"Umail result import not found: {result_import_id}"
                )
            return result_import

    async def list_rows(
        self,
        *,
        result_import_id: UUID,
        match_status: UmailResultMatchStatus | None,
        event_type: ContactEngagementEventType | None,
        campaign: str | None,
        suppression_impact: bool | None,
        page: int,
        limit: int,
    ) -> UmailResultRowPage:
        async with self._uow_factory() as uow:
            result_import = await uow.umail_feedback.get_import(result_import_id)
            if result_import is None:
                raise ResourceNotFoundError(
                    f"Umail result import not found: {result_import_id}"
                )
            rows, total = await uow.umail_feedback.list_rows(
                result_import_id=result_import_id,
                match_status=match_status,
                event_type=event_type.value if event_type else None,
                campaign=campaign.strip() if campaign and campaign.strip() else None,
                suppression_impact=suppression_impact,
                offset=(page - 1) * limit,
                limit=limit,
            )
        return UmailResultRowPage(
            page=page,
            limit=limit,
            total=total,
            rows=tuple(rows),
        )

    async def apply(self, result_import_id: UUID) -> UmailResultApplyOutcome:
        async with self._uow_factory() as uow:
            result_import = await uow.umail_feedback.get_import_for_update(
                result_import_id
            )
            if result_import is None:
                raise ResourceNotFoundError(
                    f"Umail result import not found: {result_import_id}"
                )
            if result_import.status in {
                UmailResultImportStatus.APPLIED,
                UmailResultImportStatus.PARTIAL_APPLIED,
            }:
                return UmailResultApplyOutcome(result_import=result_import, reused=True)
            if result_import.status is not UmailResultImportStatus.READY_FOR_REVIEW:
                raise ApplicationConflictError(
                    "Umail result import must be ready_for_review before apply"
                )
            rows = tuple(
                await uow.umail_feedback.list_rows_for_apply(result_import_id)
            )
            snapshots = await uow.umail_feedback.load_export_snapshots(
                export_row_ids=tuple(
                    row.matched_export_row_id
                    for row in rows
                    if row.matched_export_row_id is not None
                ),
                emails=(),
            )
            events_by_row = _events_for_rows(rows, snapshots)
            events = tuple(
                events_by_row[row.id]
                for row in rows
                if row.id in events_by_row
            )
            existing_fingerprints = await uow.umail_feedback.existing_event_fingerprints(
                tuple(event.event_fingerprint for event in events)
            )
            new_events = tuple(
                event
                for event in events
                if event.event_fingerprint not in existing_fingerprints
            )
            new_event_row_ids = {event.result_row_id for event in new_events}
            active_suppressions = await uow.umail_exports.list_active_suppressions()
            active_emails = {
                entry.email for entry in active_suppressions if entry.email is not None
            }
            snapshot_by_row = {snapshot.export_row_id: snapshot for snapshot in snapshots}
            suppressions: list[SuppressionEntry] = []
            for row in rows:
                if row.id not in new_event_row_ids:
                    continue
                if row.canonical_event_type not in SUPPRESSION_REASONS:
                    continue
                if row.matched_export_row_id is None:
                    continue
                snapshot = snapshot_by_row.get(row.matched_export_row_id)
                if snapshot is None or snapshot.email in active_emails:
                    continue
                suppressions.append(
                    SuppressionEntry.create(
                        email=snapshot.email,
                        domain=None,
                        company=None,
                        reason=SUPPRESSION_REASONS[row.canonical_event_type],
                        source="umail_feedback",
                        created_by=result_import.created_by,
                    )
                )
                active_emails.add(snapshot.email)
            await uow.umail_feedback.add_events(new_events)
            for suppression in suppressions:
                await uow.umail_exports.add_suppression(suppression)
            result_import.mark_applied(
                applied_event_count=len(new_events),
                suppression_created_count=len(suppressions),
            )
            await uow.umail_feedback.save_import(result_import)
            await uow.commit()
            return UmailResultApplyOutcome(result_import=result_import, reused=False)

    async def statistics(self, result_import_id: UUID) -> UmailFeedbackStatistics:
        async with self._uow_factory() as uow:
            result_import = await uow.umail_feedback.get_import(result_import_id)
            if result_import is None:
                raise ResourceNotFoundError(
                    f"Umail result import not found: {result_import_id}"
                )
            events = tuple(await uow.umail_feedback.list_events(result_import_id))
            snapshots = await uow.umail_feedback.load_export_snapshots(
                export_row_ids=tuple(dict.fromkeys(event.export_row_id for event in events)),
                emails=(),
            )
        snapshot_by_row = {snapshot.export_row_id: snapshot for snapshot in snapshots}
        event_counts = _empty_event_counts()
        campaign_counts: dict[str, dict[str, int]] = defaultdict(_empty_event_counts)
        route_counts: dict[str, dict[str, int]] = defaultdict(_empty_event_counts)
        company_counts: dict[UUID, dict[str, int]] = defaultdict(_empty_event_counts)
        company_names: dict[UUID, str] = {}
        for event in events:
            event_counts[event.event_type.value] += 1
            campaign_counts[event.campaign][event.event_type.value] += 1
            snapshot = snapshot_by_row.get(event.export_row_id)
            if snapshot is None:
                continue
            route_counts[snapshot.route.value][event.event_type.value] += 1
            company_counts[snapshot.company_id][event.event_type.value] += 1
            company_names[snapshot.company_id] = snapshot.company_name
        total_events = len(events)
        denominator = total_events or 1
        rates = EngagementRateStatistics(
            total_events=total_events,
            event_counts=event_counts,
            delivered_rate=event_counts[ContactEngagementEventType.DELIVERED.value]
            / denominator,
            reply_rate=event_counts[ContactEngagementEventType.REPLIED.value] / denominator,
            hard_bounce_rate=event_counts[
                ContactEngagementEventType.HARD_BOUNCED.value
            ]
            / denominator,
            unsubscribe_rate=event_counts[
                ContactEngagementEventType.UNSUBSCRIBED.value
            ]
            / denominator,
            complaint_rate=event_counts[ContactEngagementEventType.COMPLAINED.value]
            / denominator,
        )
        company_statistics = tuple(
            CompanyEngagementStatistics(
                company_id=company_id,
                company_name=company_names[company_id],
                event_counts=counts,
            )
            for company_id, counts in sorted(
                company_counts.items(),
                key=lambda item: (company_names[item[0]].casefold(), str(item[0])),
            )
        )
        return UmailFeedbackStatistics(
            result_import_id=result_import_id,
            total_result_rows=result_import.input_row_count,
            matched_rate=(
                result_import.matched_count / result_import.input_row_count
                if result_import.input_row_count
                else 0.0
            ),
            rates=rates,
            campaign_statistics=dict(campaign_counts),
            route_statistics=dict(route_counts),
            company_statistics=company_statistics,
        )


def _parse_rows(parsed_file: ParsedFeedbackCsv) -> tuple[_ParsedRow, ...]:
    rows: list[_ParsedRow] = []
    seen_semantic: set[str] = set()
    for row_number, raw_payload in enumerate(parsed_file.rows, start=2):
        mapping = parsed_file.mapping_snapshot
        errors: list[str] = []
        export_batch_id = _optional_uuid(
            _value(raw_payload, mapping, "export_batch_id"),
            error_code="invalid_export_batch_id",
            errors=errors,
        )
        export_row_id = _optional_uuid(
            _value(raw_payload, mapping, "export_row_id"),
            error_code="invalid_export_row_id",
            errors=errors,
        )
        normalized_email = _optional_email(
            _value(raw_payload, mapping, "email"), errors=errors
        )
        campaign = _optional_text(_value(raw_payload, mapping, "campaign"))
        bounce_type = _optional_text(_value(raw_payload, mapping, "bounce_type"))
        message_id = _optional_text(_value(raw_payload, mapping, "message_id"))
        event_type = _canonical_event_type(
            _value(raw_payload, mapping, "event_type"),
            bounce_type=bounce_type,
            errors=errors,
        )
        occurred_at = _occurred_at(
            _value(raw_payload, mapping, "occurred_at"), errors=errors
        )
        if export_row_id is None and normalized_email is None:
            errors.append("match_keys_missing")
        semantic_payload = {
            "export_batch_id": str(export_batch_id) if export_batch_id else None,
            "export_row_id": str(export_row_id) if export_row_id else None,
            "email": normalized_email,
            "campaign": campaign,
            "event_type": event_type.value if event_type else None,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
            "bounce_type": bounce_type,
            "message_id": message_id,
        }
        semantic_fingerprint = hashlib.sha256(
            json.dumps(semantic_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if semantic_fingerprint in seen_semantic:
            errors.append("duplicate_row")
        seen_semantic.add(semantic_fingerprint)
        rows.append(
            _ParsedRow(
                row_number=row_number,
                raw_payload=raw_payload,
                export_batch_id=export_batch_id,
                export_row_id=export_row_id,
                normalized_email=normalized_email,
                campaign=campaign,
                event_type=event_type,
                occurred_at=occurred_at,
                bounce_type=bounce_type,
                message_id=message_id,
                errors=tuple(dict.fromkeys(errors)),
                semantic_fingerprint=semantic_fingerprint,
            )
        )
    return tuple(rows)


def _match_rows(
    *,
    result_import_id: UUID,
    parsed_rows: tuple[_ParsedRow, ...],
    snapshots: tuple[FeedbackExportSnapshot, ...],
) -> tuple[UmailResultRow, ...]:
    by_row_id = {snapshot.export_row_id: snapshot for snapshot in snapshots}
    by_batch_email: dict[tuple[UUID, str], list[FeedbackExportSnapshot]] = defaultdict(list)
    by_campaign_email: dict[tuple[str, str], list[FeedbackExportSnapshot]] = defaultdict(list)
    by_email: dict[str, list[FeedbackExportSnapshot]] = defaultdict(list)
    for candidate_snapshot in snapshots:
        by_batch_email[
            (candidate_snapshot.export_batch_id, candidate_snapshot.email)
        ].append(candidate_snapshot)
        by_campaign_email[
            (candidate_snapshot.campaign, candidate_snapshot.email)
        ].append(candidate_snapshot)
        by_email[candidate_snapshot.email].append(candidate_snapshot)
    rows: list[UmailResultRow] = []
    for parsed in parsed_rows:
        duplicate = "duplicate_row" in parsed.errors
        blocking_errors = tuple(
            error for error in parsed.errors if error != "duplicate_row"
        )
        matched_snapshot: FeedbackExportSnapshot | None = None
        match_method: str | None = None
        match_status = UmailResultMatchStatus.INVALID if blocking_errors else None
        errors = list(parsed.errors)
        if duplicate:
            match_status = UmailResultMatchStatus.DUPLICATE
        elif match_status is None:
            matched_snapshot, match_status, match_method, match_errors = _match_snapshot(
                parsed,
                by_row_id=by_row_id,
                by_batch_email=by_batch_email,
                by_campaign_email=by_campaign_email,
                by_email=by_email,
            )
            errors.extend(match_errors)
        assert match_status is not None
        rows.append(
            UmailResultRow(
                id=uuid4(),
                result_import_id=result_import_id,
                row_number=parsed.row_number,
                raw_payload_json=parsed.raw_payload,
                export_batch_id=parsed.export_batch_id,
                export_row_id=parsed.export_row_id,
                normalized_email=parsed.normalized_email,
                campaign=parsed.campaign,
                canonical_event_type=parsed.event_type,
                occurred_at=parsed.occurred_at,
                bounce_type=parsed.bounce_type,
                message_id=parsed.message_id,
                match_status=match_status,
                matched_export_row_id=(
                    matched_snapshot.export_row_id
                    if match_status is UmailResultMatchStatus.MATCHED and matched_snapshot
                    else None
                ),
                match_method=(
                    match_method
                    if match_status is UmailResultMatchStatus.MATCHED
                    else None
                ),
                error_codes_json=tuple(dict.fromkeys(errors)),
                row_fingerprint=_stored_row_fingerprint(
                    parsed.semantic_fingerprint, parsed.row_number
                ),
                created_at=utcnow(),
            )
        )
    return tuple(rows)


def _match_snapshot(
    parsed: _ParsedRow,
    *,
    by_row_id: dict[UUID, FeedbackExportSnapshot],
    by_batch_email: dict[tuple[UUID, str], list[FeedbackExportSnapshot]],
    by_campaign_email: dict[tuple[str, str], list[FeedbackExportSnapshot]],
    by_email: dict[str, list[FeedbackExportSnapshot]],
) -> tuple[
    FeedbackExportSnapshot | None,
    UmailResultMatchStatus,
    str | None,
    tuple[str, ...],
]:
    if parsed.export_row_id is not None:
        snapshot = by_row_id.get(parsed.export_row_id)
        if snapshot is None:
            return None, UmailResultMatchStatus.UNMATCHED, None, ("export_row_not_found",)
        consistency_errors = _consistency_errors(parsed, snapshot)
        if consistency_errors:
            return None, UmailResultMatchStatus.INVALID, None, consistency_errors
        return snapshot, UmailResultMatchStatus.MATCHED, "export_row_id", ()
    if parsed.export_batch_id is not None and parsed.normalized_email is not None:
        candidates = by_batch_email.get(
            (parsed.export_batch_id, parsed.normalized_email), []
        )
        return _unique_match(candidates, "batch_email")
    if parsed.campaign is not None and parsed.normalized_email is not None:
        candidates = by_campaign_email.get((parsed.campaign, parsed.normalized_email), [])
        if candidates:
            return _unique_match(candidates, "campaign_email")
    if parsed.normalized_email is not None and parsed.occurred_at is not None:
        candidates = [
            snapshot
            for snapshot in by_email.get(parsed.normalized_email, [])
            if parsed.occurred_at - EMAIL_MATCH_WINDOW
            <= snapshot.batch_created_at
            <= parsed.occurred_at + EMAIL_MATCH_CLOCK_SKEW
        ]
        return _unique_match(candidates, "email_time_window")
    return None, UmailResultMatchStatus.UNMATCHED, None, ("export_match_not_found",)


def _unique_match(
    candidates: list[FeedbackExportSnapshot], method: str
) -> tuple[
    FeedbackExportSnapshot | None,
    UmailResultMatchStatus,
    str | None,
    tuple[str, ...],
]:
    if len(candidates) == 1:
        return candidates[0], UmailResultMatchStatus.MATCHED, method, ()
    if len(candidates) > 1:
        return None, UmailResultMatchStatus.AMBIGUOUS, None, (f"ambiguous_{method}",)
    return None, UmailResultMatchStatus.UNMATCHED, None, (f"unmatched_{method}",)


def _consistency_errors(
    parsed: _ParsedRow, snapshot: FeedbackExportSnapshot
) -> tuple[str, ...]:
    errors: list[str] = []
    if parsed.export_batch_id and parsed.export_batch_id != snapshot.export_batch_id:
        errors.append("export_batch_mismatch")
    if parsed.normalized_email and parsed.normalized_email != snapshot.email:
        errors.append("export_email_mismatch")
    if parsed.campaign and parsed.campaign != snapshot.campaign:
        errors.append("export_campaign_mismatch")
    return tuple(errors)


def _events_for_rows(
    rows: tuple[UmailResultRow, ...],
    snapshots: tuple[FeedbackExportSnapshot, ...],
) -> dict[UUID, ContactEngagementEvent]:
    snapshot_by_row = {snapshot.export_row_id: snapshot for snapshot in snapshots}
    events: dict[UUID, ContactEngagementEvent] = {}
    for row in rows:
        if (
            row.match_status is not UmailResultMatchStatus.MATCHED
            or row.matched_export_row_id is None
            or row.canonical_event_type is None
            or row.occurred_at is None
        ):
            continue
        snapshot = snapshot_by_row.get(row.matched_export_row_id)
        if snapshot is None:
            continue
        events[row.id] = ContactEngagementEvent.create(
            result_import_id=row.result_import_id,
            result_row_id=row.id,
            snapshot=snapshot,
            event_type=row.canonical_event_type,
            occurred_at=row.occurred_at,
            metadata_json={
                "message_id": row.message_id,
                "bounce_type": row.bounce_type,
                "match_method": row.match_method,
                "source_row_number": row.row_number,
                "needs_review": (
                    row.canonical_event_type
                    is ContactEngagementEventType.BOUNCE_UNKNOWN
                ),
            },
        )
    return events


def _projected_suppression_count(
    rows: tuple[UmailResultRow, ...],
    *,
    snapshots: tuple[FeedbackExportSnapshot, ...],
    active_suppressions: list[SuppressionEntry],
) -> int:
    active_emails = {
        entry.email for entry in active_suppressions if entry.email is not None
    }
    snapshot_by_row = {snapshot.export_row_id: snapshot for snapshot in snapshots}
    projected_emails: set[str] = set()
    for row in rows:
        if (
            row.match_status is not UmailResultMatchStatus.MATCHED
            or row.canonical_event_type not in SUPPRESSION_REASONS
            or row.matched_export_row_id is None
        ):
            continue
        snapshot = snapshot_by_row.get(row.matched_export_row_id)
        if snapshot is None or snapshot.email in active_emails:
            continue
        projected_emails.add(snapshot.email)
    return len(projected_emails)


def _mark_event_duplicates(
    rows: tuple[UmailResultRow, ...],
    *,
    potential_events: dict[UUID, ContactEngagementEvent],
    existing_fingerprints: set[str],
) -> tuple[UmailResultRow, ...]:
    seen: set[str] = set(existing_fingerprints)
    result: list[UmailResultRow] = []
    for row in rows:
        event = potential_events.get(row.id)
        if event is None or event.event_fingerprint not in seen:
            if event is not None:
                seen.add(event.event_fingerprint)
            result.append(row)
            continue
        result.append(
            dataclasses.replace(
                row,
                match_status=UmailResultMatchStatus.DUPLICATE,
                matched_export_row_id=None,
                match_method=None,
                error_codes_json=(*row.error_codes_json, "duplicate_event"),
            )
        )
    return tuple(result)


def _canonical_event_type(
    value: str,
    *,
    bounce_type: str | None,
    errors: list[str],
) -> ContactEngagementEventType | None:
    normalized = _event_token(value)
    if not normalized:
        errors.append("event_type_missing")
        return None
    if normalized in {"bounce", "bounced"}:
        bounce = _event_token(bounce_type or "")
        if bounce in HARD_BOUNCE_ALIASES:
            return ContactEngagementEventType.HARD_BOUNCED
        if bounce in SOFT_BOUNCE_ALIASES:
            return ContactEngagementEventType.SOFT_BOUNCED
        return ContactEngagementEventType.BOUNCE_UNKNOWN
    event_type = EVENT_ALIASES.get(normalized)
    if event_type is None:
        errors.append("unsupported_event")
    return event_type


def _occurred_at(value: str, *, errors: list[str]) -> datetime | None:
    clean = value.strip()
    if not clean:
        errors.append("occurred_at_missing")
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        errors.append("occurred_at_invalid")
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_uuid(value: str, *, error_code: str, errors: list[str]) -> UUID | None:
    clean = value.strip()
    if not clean:
        return None
    try:
        return UUID(clean)
    except ValueError:
        errors.append(error_code)
        return None


def _optional_email(value: str, *, errors: list[str]) -> str | None:
    clean = value.strip().casefold()
    if not clean:
        return None
    if len(clean) > 320 or EMAIL_PATTERN.fullmatch(clean) is None:
        errors.append("email_invalid")
        return None
    return clean


def _optional_text(value: str) -> str | None:
    clean = value.strip()
    return clean or None


def _event_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _value(
    payload: dict[str, Any], mapping: dict[str, str], logical_field: str
) -> str:
    value = payload.get(mapping[logical_field], "")
    return value if isinstance(value, str) else str(value)


def _stored_row_fingerprint(semantic_fingerprint: str, row_number: int) -> str:
    return hashlib.sha256(f"{semantic_fingerprint}:{row_number}".encode()).hexdigest()


def _empty_event_counts() -> dict[str, int]:
    return {event_type.value: 0 for event_type in ContactEngagementEventType}
