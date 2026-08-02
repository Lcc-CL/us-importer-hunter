from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.bulk_import import (
    ImportSession,
    ImportSessionStatus,
    RawImportRow,
    RawImportRowStatus,
)
from app.domain.exceptions import DomainError, InvalidStateTransition


def make_session() -> ImportSession:
    return ImportSession.create(
        source="netease_foreign_trade",
        original_filename="synthetic.csv",
        file_size_bytes=128,
        file_sha256="a" * 64,
        mapping_json={"logical_fields": {}, "source_headers": ["company"]},
        encoding="utf-8",
    )


def test_session_tracks_progress_and_partial_failure() -> None:
    session = make_session()
    session.start_processing()
    session.record_progress(
        total_rows=3,
        accepted_rows=1,
        invalid_rows=1,
        duplicate_rows=1,
    )
    session.complete()

    assert session.status is ImportSessionStatus.PARTIAL_FAILED
    assert session.total_rows == 3
    assert session.completed_at is not None


def test_session_rejects_inconsistent_counts_and_terminal_restart() -> None:
    session = make_session()
    session.start_processing()
    with pytest.raises(DomainError, match="add up"):
        session.record_progress(
            total_rows=2,
            accepted_rows=1,
            invalid_rows=0,
            duplicate_rows=0,
        )
    session.record_progress(
        total_rows=1,
        accepted_rows=1,
        invalid_rows=0,
        duplicate_rows=0,
    )
    session.complete()
    with pytest.raises(InvalidStateTransition):
        session.start_processing()


def test_raw_row_requires_errors_for_non_accepted_status() -> None:
    with pytest.raises(DomainError, match="require error codes"):
        RawImportRow(
            id=uuid4(),
            import_session_id=uuid4(),
            row_number=2,
            raw_payload={"fields": {}},
            row_hash="b" * 64,
            status=RawImportRowStatus.INVALID,
            error_codes=(),
            created_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
