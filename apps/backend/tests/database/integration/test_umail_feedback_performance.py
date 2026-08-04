"""D5d2b bounded 10,000-row performance and query-count sample."""

import csv
import gc
import hashlib
import io
import tracemalloc
from datetime import UTC, datetime
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import event, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database.models.bulk_import import ImportSessionModel
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactModel
from app.database.models.prospect_routing import ProspectRoutingRunModel
from app.database.models.umail_export import UmailExportBatchModel, UmailExportRowModel
from app.workflows.umail_feedback import UmailResultImportWorkflow
from tests.database.integration.conftest import UowFactory

MATCHED_COUNT = 7_000
UNMATCHED_COUNT = 1_000
AMBIGUOUS_COUNT = 500
INVALID_COUNT = 1_000
DUPLICATE_COUNT = 500
EXPORT_ROW_COUNT = MATCHED_COUNT + AMBIGUOUS_COUNT * 2
EVENT_TYPES = (
    "sent",
    "delivered",
    "hard_bounce",
    "soft_bounce",
    "bounce",
    "unsubscribed",
    "complained",
    "replied",
    "opened",
    "clicked",
)


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"d5d2b-performance:{value}")


def _result_csv(row_ids: tuple[UUID, ...]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        (
            "export_batch_id",
            "export_row_id",
            "email",
            "campaign",
            "event_type",
            "occurred_at",
            "bounce_type",
            "message_id",
        )
    )
    matched_rows: list[tuple[str, ...]] = []
    for index in range(MATCHED_COUNT):
        event_type = EVENT_TYPES[index % len(EVENT_TYPES)]
        bounce_type = "mystery" if event_type == "bounce" else ""
        row: tuple[str, ...] = (
            "",
            str(row_ids[index]),
            f"matched-{index}@example.test",
            "Performance Campaign",
            event_type,
            "2026-08-02T12:00:00Z",
            bounce_type,
            f"matched-message-{index}",
        )
        matched_rows.append(row)
        writer.writerow(row)
    for index in range(UNMATCHED_COUNT):
        writer.writerow(
            (
                "",
                "",
                f"unmatched-{index}@example.test",
                "Missing Campaign",
                "delivered",
                "2026-08-02T12:00:00Z",
                "",
                f"unmatched-message-{index}",
            )
        )
    for index in range(AMBIGUOUS_COUNT):
        writer.writerow(
            (
                "",
                "",
                f"ambiguous-{index}@example.test",
                "Performance Campaign",
                "replied",
                "2026-08-02T12:00:00Z",
                "",
                f"ambiguous-message-{index}",
            )
        )
    for index in range(INVALID_COUNT):
        writer.writerow(
            (
                "",
                str(row_ids[index]),
                f"matched-{index}@example.test",
                "Performance Campaign",
                "unsupported_event",
                "2026-08-02T12:00:00Z",
                "",
                f"invalid-message-{index}",
            )
        )
    for duplicate_row in matched_rows[:DUPLICATE_COUNT]:
        writer.writerow(duplicate_row)
    return output.getvalue().encode()


async def _seed_exports(uow_factory: UowFactory) -> tuple[UUID, ...]:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    session_id = _id("session")
    routing_run_id = _id("routing-run")
    primary_batch_id = _id("primary-batch")
    secondary_batch_id = _id("secondary-batch")
    company_ids = tuple(_id(f"company-{index}") for index in range(EXPORT_ROW_COUNT))
    contact_ids = tuple(_id(f"contact-{index}") for index in range(EXPORT_ROW_COUNT))
    row_ids = tuple(_id(f"row-{index}") for index in range(EXPORT_ROW_COUNT))
    async with uow_factory() as uow:
        session = uow._session
        assert session is not None
        await session.execute(
            insert(ImportSessionModel),
            [
                {
                    "id": session_id,
                    "source": "d5d2b_performance",
                    "original_filename": "performance.csv",
                    "file_type": "csv",
                    "file_size_bytes": 1,
                    "file_sha256": hashlib.sha256(b"d5d2b-performance").hexdigest(),
                    "mapping_json": {},
                    "encoding": "utf-8",
                    "status": "completed",
                    "total_rows": 0,
                    "accepted_rows": 0,
                    "invalid_rows": 0,
                    "duplicate_rows": 0,
                    "started_at": now,
                    "completed_at": now,
                    "error_summary": None,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        await session.execute(
            insert(ProspectRoutingRunModel),
            [
                {
                    "id": routing_run_id,
                    "import_session_id": session_id,
                    "rules_version": "d5c-deterministic-routing-v1",
                    "configuration_hash": hashlib.sha256(b"performance-config").hexdigest(),
                    "entity_state_hash": hashlib.sha256(b"performance-state").hexdigest(),
                    "execution_generation": 1,
                    "criteria_json": {"target_product_keywords": ["hardware"]},
                    "weights_snapshot_json": {},
                    "status": "completed",
                    "total_companies": EXPORT_ROW_COUNT,
                    "routed_companies": EXPORT_ROW_COUNT,
                    "blocked_companies": 0,
                    "tier_a_count": 0,
                    "tier_b_count": EXPORT_ROW_COUNT,
                    "tier_c_count": 0,
                    "tier_d_count": 0,
                    "started_at": now,
                    "completed_at": now,
                    "error_summary": None,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        await session.execute(
            insert(CompanyModel),
            [
                {
                    "id": company_id,
                    "name": f"Feedback Performance Importer {index:05d}",
                    "normalized_name": f"feedback performance importer {index:05d}",
                    "website": None,
                    "website_host": None,
                    "verified": True,
                    "created_at": now,
                }
                for index, company_id in enumerate(company_ids)
            ],
        )
        await session.execute(
            insert(ContactModel),
            [
                {
                    "id": contact_id,
                    "company_id": company_ids[index],
                    "name": f"Performance Buyer {index:05d}",
                    "normalized_name": f"performance buyer {index:05d}",
                    "title_raw": "Procurement Director",
                    "department": "procurement",
                    "seniority": "director",
                    "status": "active",
                    "invalid_reason": None,
                    "created_at": now,
                    "updated_at": now,
                }
                for index, contact_id in enumerate(contact_ids)
            ],
        )
        await session.execute(
            insert(UmailExportBatchModel),
            [
                {
                    "id": primary_batch_id,
                    "routing_run_id": routing_run_id,
                    "execution_generation": 1,
                    "campaign": "Performance Campaign",
                    "mapping_version": "umail-export-contract-v1",
                    "selection_hash": hashlib.sha256(b"performance-primary").hexdigest(),
                    "status": "prepared",
                    "total_rows": MATCHED_COUNT + AMBIGUOUS_COUNT,
                    "ready_count": MATCHED_COUNT + AMBIGUOUS_COUNT,
                    "suppressed_count": 0,
                    "invalid_count": 0,
                    "duplicate_count": 0,
                    "content_sha256": hashlib.sha256(b"performance-primary-content").hexdigest(),
                    "downloaded_at": None,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": secondary_batch_id,
                    "routing_run_id": routing_run_id,
                    "execution_generation": 1,
                    "campaign": "Performance Campaign",
                    "mapping_version": "umail-export-contract-v1",
                    "selection_hash": hashlib.sha256(b"performance-secondary").hexdigest(),
                    "status": "prepared",
                    "total_rows": AMBIGUOUS_COUNT,
                    "ready_count": AMBIGUOUS_COUNT,
                    "suppressed_count": 0,
                    "invalid_count": 0,
                    "duplicate_count": 0,
                    "content_sha256": hashlib.sha256(b"performance-secondary-content").hexdigest(),
                    "downloaded_at": None,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        export_rows: list[dict[str, object]] = []
        for index in range(EXPORT_ROW_COUNT):
            if index < MATCHED_COUNT:
                batch_id = primary_batch_id
                position = index + 1
                email = f"matched-{index}@example.test"
            elif index < MATCHED_COUNT + AMBIGUOUS_COUNT:
                batch_id = primary_batch_id
                position = index + 1
                email = f"ambiguous-{index - MATCHED_COUNT}@example.test"
            else:
                batch_id = secondary_batch_id
                position = index - MATCHED_COUNT - AMBIGUOUS_COUNT + 1
                email = f"ambiguous-{index - MATCHED_COUNT - AMBIGUOUS_COUNT}@example.test"
            export_rows.append(
                {
                    "id": row_ids[index],
                    "batch_id": batch_id,
                    "position": position,
                    "company_id": company_ids[index],
                    "contact_id": contact_ids[index],
                    "company_name": f"Feedback Performance Importer {index:05d}",
                    "company_website": None,
                    "contact_name": f"Performance Buyer {index:05d}",
                    "first_name": "Performance",
                    "last_name": f"Buyer {index:05d}",
                    "contact_title": "Procurement Director",
                    "contact_role": "procurement",
                    "contact_seniority": "director",
                    "is_department_contact": False,
                    "email": email,
                    "phone": None,
                    "country": "US",
                    "route": "B",
                    "route_review_status": "confirmed",
                    "pre_score": 70.0,
                    "route_reasons": ["D5D2B_PERFORMANCE"],
                    "status": "ready",
                    "exclusion_reason": None,
                    "row_fingerprint": hashlib.sha256(f"row-{index}".encode()).hexdigest(),
                    "created_at": now,
                }
            )
        await session.execute(insert(UmailExportRowModel), export_rows)
        await uow.commit()
    return row_ids


async def test_10000_result_rows_stay_inside_feedback_budget(
    engine: AsyncEngine,
    uow_factory: UowFactory,
) -> None:
    row_ids = await _seed_exports(uow_factory)
    content = _result_csv(row_ids)
    workflow = UmailResultImportWorkflow(uow_factory)
    upload_statements = 0
    apply_statements = 0
    phase = "upload"

    def count_statement(*_: object) -> None:
        nonlocal upload_statements, apply_statements
        if phase == "upload":
            upload_statements += 1
        else:
            apply_statements += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        tracemalloc.start()
        started = perf_counter()
        submission = await workflow.upload(
            file=io.BytesIO(content),
            source_filename="performance-results.csv",
            mapping={},
            created_by="performance-test",
        )
        parse_match_seconds = perf_counter() - started
        _, upload_peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        gc.collect()
        phase = "apply"
        tracemalloc.start()
        started = perf_counter()
        applied = await workflow.apply(submission.result_import.id)
        apply_seconds = perf_counter() - started
        _, apply_peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
        if tracemalloc.is_tracing():
            tracemalloc.stop()

    assert submission.result_import.input_row_count == 10_000
    assert submission.result_import.matched_count == MATCHED_COUNT
    assert submission.result_import.unmatched_count == UNMATCHED_COUNT
    assert submission.result_import.ambiguous_count == AMBIGUOUS_COUNT
    assert submission.result_import.invalid_count == INVALID_COUNT
    assert submission.result_import.duplicate_count == DUPLICATE_COUNT
    assert applied.result_import.applied_event_count == MATCHED_COUNT
    assert applied.result_import.suppression_created_count == 2_100
    assert parse_match_seconds < 30
    assert apply_seconds < 30
    assert max(upload_peak_bytes, apply_peak_bytes) < 256 * 1024 * 1024
    assert upload_statements <= 12
    assert apply_statements <= 12
    print(
        "D5d2b performance: "
        f"parse_match={parse_match_seconds:.3f}s, apply={apply_seconds:.3f}s, "
        f"peak={max(upload_peak_bytes, apply_peak_bytes) / 1024 / 1024:.1f}MiB, "
        f"sql={upload_statements}+{apply_statements}"
    )
