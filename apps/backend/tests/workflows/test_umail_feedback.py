"""Application-level two-phase behavior for offline Umail feedback."""

import io
from datetime import UTC, datetime
from typing import Self, cast
from uuid import UUID, uuid4

from app.domain.prospect_routing import ProspectTier
from app.domain.repositories import UmailFeedbackUnitOfWork
from app.domain.umail_export import SuppressionEntry
from app.domain.umail_feedback import (
    ContactEngagementEvent,
    FeedbackExportSnapshot,
    UmailResultImport,
    UmailResultMatchStatus,
    UmailResultRow,
)
from app.workflows.umail_feedback import UmailResultImportWorkflow


class _FeedbackRepository:
    def __init__(self, snapshot: FeedbackExportSnapshot) -> None:
        self.snapshot = snapshot
        self.result_import: UmailResultImport | None = None
        self.rows: tuple[UmailResultRow, ...] = ()
        self.events: list[ContactEngagementEvent] = []

    async def find_import_by_file_hash(self, file_sha256: str) -> UmailResultImport | None:
        if self.result_import and self.result_import.file_sha256 == file_sha256:
            return self.result_import
        return None

    async def get_import(self, result_import_id: UUID) -> UmailResultImport | None:
        if self.result_import and self.result_import.id == result_import_id:
            return self.result_import
        return None

    async def get_import_for_update(self, result_import_id: UUID) -> UmailResultImport | None:
        return await self.get_import(result_import_id)

    async def add_import(
        self,
        result_import: UmailResultImport,
        rows: tuple[UmailResultRow, ...],
    ) -> None:
        self.result_import = result_import
        self.rows = rows

    async def save_import(self, result_import: UmailResultImport) -> None:
        self.result_import = result_import

    async def list_rows(
        self,
        *,
        result_import_id: UUID,
        match_status: UmailResultMatchStatus | None,
        event_type: str | None,
        campaign: str | None,
        suppression_impact: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[UmailResultRow], int]:
        del result_import_id, suppression_impact
        rows = [
            row
            for row in self.rows
            if (match_status is None or row.match_status is match_status)
            and (
                event_type is None
                or (
                    row.canonical_event_type is not None
                    and row.canonical_event_type.value == event_type
                )
            )
            and (campaign is None or row.campaign == campaign)
        ]
        return rows[offset : offset + limit], len(rows)

    async def list_rows_for_apply(self, result_import_id: UUID) -> list[UmailResultRow]:
        return [
            row
            for row in self.rows
            if row.result_import_id == result_import_id
            and row.match_status is UmailResultMatchStatus.MATCHED
        ]

    async def load_export_snapshots(
        self,
        *,
        export_row_ids: tuple[UUID, ...],
        emails: tuple[str, ...],
    ) -> tuple[FeedbackExportSnapshot, ...]:
        if self.snapshot.export_row_id in export_row_ids or self.snapshot.email in emails:
            return (self.snapshot,)
        return ()

    async def existing_event_fingerprints(self, fingerprints: tuple[str, ...]) -> set[str]:
        existing = {event.event_fingerprint for event in self.events}
        return existing.intersection(fingerprints)

    async def add_events(self, events: tuple[ContactEngagementEvent, ...]) -> None:
        self.events.extend(events)

    async def list_events(self, result_import_id: UUID) -> list[ContactEngagementEvent]:
        return [event for event in self.events if event.result_import_id == result_import_id]


class _ExportRepository:
    def __init__(self) -> None:
        self.suppressions: list[SuppressionEntry] = []

    async def list_active_suppressions(self) -> list[SuppressionEntry]:
        return [entry for entry in self.suppressions if entry.active]

    async def add_suppression(self, entry: SuppressionEntry) -> None:
        self.suppressions.append(entry)


class _UnitOfWork:
    def __init__(self, snapshot: FeedbackExportSnapshot) -> None:
        self.umail_feedback = _FeedbackRepository(snapshot)
        self.umail_exports = _ExportRepository()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        del exc_type, exc, tb

    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


async def test_preview_has_no_side_effects_and_apply_is_idempotent() -> None:
    snapshot = FeedbackExportSnapshot(
        export_batch_id=uuid4(),
        export_row_id=uuid4(),
        email="buyer@example.test",
        campaign="D5d2b",
        company_id=uuid4(),
        company_name="Example Importer",
        contact_id=uuid4(),
        route=ProspectTier.B,
        batch_created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    uow = _UnitOfWork(snapshot)
    workflow = UmailResultImportWorkflow(
        lambda: cast(UmailFeedbackUnitOfWork, uow)
    )
    csv_content = (
        "export_row_id,event_type,occurred_at,bounce_type,message_id\n"
        f"{snapshot.export_row_id},delivered,2026-08-02T10:00:00Z,,m1\n"
        f"{snapshot.export_row_id},bounce,2026-08-02T11:00:00Z,unknown,m2\n"
        f"{snapshot.export_row_id},hard_bounce,2026-08-02T12:00:00Z,,m3\n"
    ).encode()

    submission = await workflow.upload(
        file=io.BytesIO(csv_content),
        source_filename="feedback.csv",
        mapping={},
        created_by="reviewer",
    )
    assert submission.result_import.matched_count == 3
    assert submission.result_import.projected_event_count == 3
    assert submission.result_import.projected_suppression_count == 1
    assert uow.umail_feedback.events == []
    assert uow.umail_exports.suppressions == []

    applied = await workflow.apply(submission.result_import.id)
    assert applied.result_import.applied_event_count == 3
    assert applied.result_import.suppression_created_count == 1
    assert len(uow.umail_feedback.events) == 3
    unknown = next(
        event
        for event in uow.umail_feedback.events
        if event.event_type.value == "bounce_unknown"
    )
    assert unknown.metadata_json["needs_review"] is True

    repeated = await workflow.apply(submission.result_import.id)
    assert repeated.reused is True
    assert len(uow.umail_feedback.events) == 3
    assert len(uow.umail_exports.suppressions) == 1
