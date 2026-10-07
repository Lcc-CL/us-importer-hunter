"""Framework-free state for offline Umail result feedback."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition
from app.domain.prospect_routing import ProspectTier

UMAIL_RESULT_MAPPING_VERSION = "umail-result-import-contract-v1"


class UmailResultImportStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSED = "parsed"
    READY_FOR_REVIEW = "ready_for_review"
    APPLIED = "applied"
    PARTIAL_APPLIED = "partial_applied"
    FAILED = "failed"


class UmailResultMatchStatus(StrEnum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    DUPLICATE = "duplicate"


class ContactEngagementEventType(StrEnum):
    SENT = "sent"
    DELIVERED = "delivered"
    HARD_BOUNCED = "hard_bounced"
    SOFT_BOUNCED = "soft_bounced"
    BOUNCE_UNKNOWN = "bounce_unknown"
    UNSUBSCRIBED = "unsubscribed"
    COMPLAINED = "complained"
    REPLIED = "replied"
    OPENED = "opened"
    CLICKED = "clicked"


class UmailResultImport:
    def __init__(
        self,
        *,
        id: UUID,
        source_filename: str,
        file_sha256: str,
        mapping_version: str,
        mapping_snapshot_json: dict[str, str],
        status: UmailResultImportStatus,
        input_row_count: int,
        matched_count: int,
        unmatched_count: int,
        ambiguous_count: int,
        invalid_count: int,
        duplicate_count: int,
        projected_event_count: int,
        projected_suppression_count: int,
        applied_event_count: int,
        suppression_created_count: int,
        created_by: str,
        created_at: datetime,
        applied_at: datetime | None,
        error_summary: str | None,
    ) -> None:
        self.id = id
        self.source_filename = source_filename
        self.file_sha256 = file_sha256
        self.mapping_version = mapping_version
        self.mapping_snapshot_json = dict(mapping_snapshot_json)
        self.status = status
        self.input_row_count = input_row_count
        self.matched_count = matched_count
        self.unmatched_count = unmatched_count
        self.ambiguous_count = ambiguous_count
        self.invalid_count = invalid_count
        self.duplicate_count = duplicate_count
        self.projected_event_count = projected_event_count
        self.projected_suppression_count = projected_suppression_count
        self.applied_event_count = applied_event_count
        self.suppression_created_count = suppression_created_count
        self.created_by = created_by
        self.created_at = created_at
        self.applied_at = applied_at
        self.error_summary = error_summary
        self._validate()

    @classmethod
    def ready_for_review(
        cls,
        *,
        source_filename: str,
        file_sha256: str,
        mapping_snapshot_json: dict[str, str],
        rows: tuple["UmailResultRow", ...],
        projected_suppression_count: int,
        created_by: str,
    ) -> "UmailResultImport":
        counts = {
            status: sum(row.match_status is status for row in rows)
            for status in UmailResultMatchStatus
        }
        return cls(
            id=rows[0].result_import_id if rows else uuid4(),
            source_filename=source_filename.strip(),
            file_sha256=file_sha256,
            mapping_version=UMAIL_RESULT_MAPPING_VERSION,
            mapping_snapshot_json=mapping_snapshot_json,
            status=UmailResultImportStatus.READY_FOR_REVIEW,
            input_row_count=len(rows),
            matched_count=counts[UmailResultMatchStatus.MATCHED],
            unmatched_count=counts[UmailResultMatchStatus.UNMATCHED],
            ambiguous_count=counts[UmailResultMatchStatus.AMBIGUOUS],
            invalid_count=counts[UmailResultMatchStatus.INVALID],
            duplicate_count=counts[UmailResultMatchStatus.DUPLICATE],
            projected_event_count=counts[UmailResultMatchStatus.MATCHED],
            projected_suppression_count=projected_suppression_count,
            applied_event_count=0,
            suppression_created_count=0,
            created_by=created_by.strip(),
            created_at=utcnow(),
            applied_at=None,
            error_summary=None,
        )

    def mark_applied(
        self,
        *,
        applied_event_count: int,
        suppression_created_count: int,
    ) -> None:
        if self.status in {
            UmailResultImportStatus.APPLIED,
            UmailResultImportStatus.PARTIAL_APPLIED,
        }:
            return
        if self.status is not UmailResultImportStatus.READY_FOR_REVIEW:
            raise InvalidStateTransition("only a reviewed Umail result import can be applied")
        if applied_event_count < 0 or suppression_created_count < 0:
            raise DomainError("applied counters must not be negative")
        excluded = (
            self.unmatched_count
            + self.ambiguous_count
            + self.invalid_count
            + self.duplicate_count
        )
        self.status = (
            UmailResultImportStatus.PARTIAL_APPLIED
            if excluded
            else UmailResultImportStatus.APPLIED
        )
        self.applied_event_count = applied_event_count
        self.suppression_created_count = suppression_created_count
        self.applied_at = utcnow()
        self._validate()

    def _validate(self) -> None:
        if not self.source_filename or not self.mapping_version or not self.created_by:
            raise DomainError("Umail result import requires file, mapping, and creator")
        if len(self.file_sha256) != 64:
            raise DomainError("Umail result file hash must be SHA-256")
        counts = (
            self.matched_count,
            self.unmatched_count,
            self.ambiguous_count,
            self.invalid_count,
            self.duplicate_count,
        )
        if self.input_row_count < 0 or any(value < 0 for value in counts):
            raise DomainError("Umail result counters must not be negative")
        if sum(counts) != self.input_row_count:
            raise DomainError("Umail result match counters must equal input rows")
        if (
            self.projected_event_count < 0
            or self.projected_suppression_count < 0
            or self.applied_event_count < 0
            or self.suppression_created_count < 0
        ):
            raise DomainError("Umail result apply counters must not be negative")
        if self.projected_event_count != self.matched_count:
            raise DomainError("projected Umail events must equal matched preview rows")
        if self.projected_suppression_count > self.projected_event_count:
            raise DomainError("projected suppressions cannot exceed projected events")
        applied = self.status in {
            UmailResultImportStatus.APPLIED,
            UmailResultImportStatus.PARTIAL_APPLIED,
        }
        if applied != (self.applied_at is not None):
            raise DomainError("Umail result applied status and timestamp must agree")


@dataclass(frozen=True)
class UmailResultRow:
    id: UUID
    result_import_id: UUID
    row_number: int
    raw_payload_json: dict[str, Any]
    export_batch_id: UUID | None
    export_row_id: UUID | None
    normalized_email: str | None
    campaign: str | None
    canonical_event_type: ContactEngagementEventType | None
    occurred_at: datetime | None
    bounce_type: str | None
    message_id: str | None
    match_status: UmailResultMatchStatus
    matched_export_row_id: UUID | None
    match_method: str | None
    error_codes_json: tuple[str, ...]
    row_fingerprint: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.row_number < 2:
            raise DomainError("Umail result row number must include the CSV header offset")
        if len(self.row_fingerprint) != 64:
            raise DomainError("Umail result row fingerprint must be SHA-256")
        if self.match_status is UmailResultMatchStatus.MATCHED:
            if self.matched_export_row_id is None or self.match_method is None:
                raise DomainError("matched Umail result row requires its exact match source")
            if self.canonical_event_type is None or self.occurred_at is None:
                raise DomainError("matched Umail result row requires a canonical event and time")
        elif self.matched_export_row_id is not None:
            raise DomainError("non-matched Umail result row cannot claim an export row")


@dataclass(frozen=True)
class FeedbackExportSnapshot:
    export_batch_id: UUID
    export_row_id: UUID
    email: str
    campaign: str
    company_id: UUID
    company_name: str
    contact_id: UUID
    route: ProspectTier
    batch_created_at: datetime


@dataclass(frozen=True)
class ContactEngagementEvent:
    id: UUID
    result_import_id: UUID
    result_row_id: UUID
    export_batch_id: UUID
    export_row_id: UUID
    company_id: UUID
    contact_id: UUID
    event_type: ContactEngagementEventType
    occurred_at: datetime
    campaign: str
    provider: str
    event_fingerprint: str
    metadata_json: dict[str, Any]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        result_import_id: UUID,
        result_row_id: UUID,
        snapshot: FeedbackExportSnapshot,
        event_type: ContactEngagementEventType,
        occurred_at: datetime,
        metadata_json: dict[str, Any],
    ) -> "ContactEngagementEvent":
        provider = "umail_offline_csv"
        payload = {
            "export_batch_id": str(snapshot.export_batch_id),
            "export_row_id": str(snapshot.export_row_id),
            "event_type": event_type.value,
            "occurred_at": occurred_at.isoformat(),
            "campaign": snapshot.campaign,
            "provider": provider,
            "message_id": metadata_json.get("message_id"),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            id=uuid4(),
            result_import_id=result_import_id,
            result_row_id=result_row_id,
            export_batch_id=snapshot.export_batch_id,
            export_row_id=snapshot.export_row_id,
            company_id=snapshot.company_id,
            contact_id=snapshot.contact_id,
            event_type=event_type,
            occurred_at=occurred_at,
            campaign=snapshot.campaign,
            provider=provider,
            event_fingerprint=fingerprint,
            metadata_json=dict(metadata_json),
            created_at=utcnow(),
        )
