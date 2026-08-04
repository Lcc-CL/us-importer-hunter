"""Domain invariants for append-only Umail feedback."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.exceptions import DomainError
from app.domain.prospect_routing import ProspectTier
from app.domain.umail_feedback import (
    ContactEngagementEvent,
    ContactEngagementEventType,
    FeedbackExportSnapshot,
    UmailResultImport,
    UmailResultMatchStatus,
    UmailResultRow,
)


def _snapshot() -> FeedbackExportSnapshot:
    return FeedbackExportSnapshot(
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


def test_engagement_fingerprint_is_stable_across_reimports() -> None:
    snapshot = _snapshot()
    occurred_at = datetime(2026, 8, 2, 12, tzinfo=UTC)
    first = ContactEngagementEvent.create(
        result_import_id=uuid4(),
        result_row_id=uuid4(),
        snapshot=snapshot,
        event_type=ContactEngagementEventType.REPLIED,
        occurred_at=occurred_at,
        metadata_json={"message_id": "message-1", "match_method": "export_row_id"},
    )
    repeated = ContactEngagementEvent.create(
        result_import_id=uuid4(),
        result_row_id=uuid4(),
        snapshot=snapshot,
        event_type=ContactEngagementEventType.REPLIED,
        occurred_at=occurred_at,
        metadata_json={"message_id": "message-1", "match_method": "batch_email"},
    )

    assert first.event_fingerprint == repeated.event_fingerprint
    assert first.provider == "umail_offline_csv"


def test_result_import_requires_complete_row_counters() -> None:
    result_import_id = uuid4()
    row = UmailResultRow(
        id=uuid4(),
        result_import_id=result_import_id,
        row_number=2,
        raw_payload_json={"event_type": "sent"},
        export_batch_id=None,
        export_row_id=None,
        normalized_email="buyer@example.test",
        campaign=None,
        canonical_event_type=ContactEngagementEventType.SENT,
        occurred_at=datetime(2026, 8, 2, tzinfo=UTC),
        bounce_type=None,
        message_id=None,
        match_status=UmailResultMatchStatus.UNMATCHED,
        matched_export_row_id=None,
        match_method=None,
        error_codes_json=("export_match_not_found",),
        row_fingerprint="a" * 64,
        created_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    value = UmailResultImport.ready_for_review(
        source_filename="results.csv",
        file_sha256="b" * 64,
        mapping_snapshot_json={"event_type": "event"},
        rows=(row,),
        projected_suppression_count=0,
        created_by="reviewer",
    )
    assert value.unmatched_count == 1

    with pytest.raises(DomainError):
        UmailResultImport(
            id=result_import_id,
            source_filename="results.csv",
            file_sha256="b" * 64,
            mapping_version="v1",
            mapping_snapshot_json={},
            status=value.status,
            input_row_count=2,
            matched_count=0,
            unmatched_count=1,
            ambiguous_count=0,
            invalid_count=0,
            duplicate_count=0,
            projected_event_count=1,
            projected_suppression_count=0,
            applied_event_count=0,
            suppression_created_count=0,
            created_by="reviewer",
            created_at=value.created_at,
            applied_at=None,
            error_summary=None,
        )
