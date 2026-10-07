"""CSV-contract tests for offline Umail feedback intake."""

import io

import pytest

from app.services.umail_feedback import (
    FeedbackCsvValidationError,
    UmailResultCsvIntake,
)


def test_feedback_csv_accepts_bom_and_persists_custom_mapping() -> None:
    content = (
        "\ufeffrow_id,recipient,status,time\n"
        "00000000-0000-4000-8000-000000000001,buyer@example.test,delivered,"
        "2026-08-02T12:00:00Z\n"
    ).encode()
    parsed = UmailResultCsvIntake().parse(
        io.BytesIO(content),
        mapping={
            "export_row_id": "row_id",
            "email": "recipient",
            "event_type": "status",
            "occurred_at": "time",
        },
    )

    assert parsed.encoding == "utf-8-sig"
    assert parsed.mapping_snapshot["event_type"] == "status"
    assert parsed.rows[0]["recipient"] == "buyer@example.test"


def test_feedback_csv_rejects_missing_required_mapping_column() -> None:
    with pytest.raises(FeedbackCsvValidationError) as caught:
        UmailResultCsvIntake().parse(
            io.BytesIO(b"email,event_type\nbuyer@example.test,sent\n"),
            mapping={},
        )

    assert caught.value.code == "umail_result_mapping_invalid"
