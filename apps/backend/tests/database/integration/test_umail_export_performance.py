"""D5d2a bounded performance and query-count sample on PostgreSQL."""

import hashlib
import tracemalloc
from datetime import UTC, datetime
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import event, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database.models.bulk_import import ImportSessionModel
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactChannelModel, ContactModel
from app.database.models.import_resolution import CompanyContactModel
from app.database.models.prospect_routing import ProspectRouteModel, ProspectRoutingRunModel
from app.database.models.umail_export import SuppressionEntryModel
from app.workflows.umail_export import UmailExportWorkflow, render_umail_csv
from tests.database.integration.conftest import UowFactory

COMPANY_COUNT = 500
CONTACTS_PER_COMPANY = 10


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"d5d2a-performance:{value}")


async def test_500_company_export_stays_inside_mvp_budget(
    engine: AsyncEngine,
    uow_factory: UowFactory,
) -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    session_id = _id("session")
    routing_run_id = _id("routing-run")
    company_ids = tuple(_id(f"company-{index}") for index in range(COMPANY_COUNT))
    async with uow_factory() as uow:
        session = uow._session
        assert session is not None
        await session.execute(
            insert(ImportSessionModel),
            [
                {
                    "id": session_id,
                    "source": "d5d2a_performance",
                    "original_filename": "performance.csv",
                    "file_type": "csv",
                    "file_size_bytes": 1,
                    "file_sha256": hashlib.sha256(b"performance").hexdigest(),
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
                    "rules_version": "real-routing-v1.1",
                    "configuration_hash": hashlib.sha256(b"config").hexdigest(),
                    "entity_state_hash": hashlib.sha256(b"state").hexdigest(),
                    "execution_generation": 1,
                    "criteria_json": {"target_product_keywords": ["hardware"]},
                    "weights_snapshot_json": {},
                    "status": "completed",
                    "total_companies": COMPANY_COUNT,
                    "routed_companies": COMPANY_COUNT,
                    "blocked_companies": 0,
                    "tier_a_count": 0,
                    "tier_b_count": COMPANY_COUNT,
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
                    "name": f"Performance Importer {index:04d}",
                    "normalized_name": f"performance importer {index:04d}",
                    "website": f"https://company-{index}.example",
                    "website_host": f"company-{index}.example",
                    "verified": True,
                    "created_at": now,
                }
                for index, company_id in enumerate(company_ids)
            ],
        )
        await session.execute(
            insert(ProspectRouteModel),
            [
                {
                    "id": _id(f"route-{index}"),
                    "routing_run_id": routing_run_id,
                    "execution_generation": 1,
                    "company_id": company_id,
                    "company_name": f"Performance Importer {index:04d}",
                    "pre_score": 65.0 + (index % 20),
                    "recommended_tier": "B",
                    "effective_tier": "B",
                    "feature_snapshot_json": {},
                    "reason_codes": ["PERFORMANCE_SAMPLE"],
                    "warning_codes": [],
                    "review_status": "confirmed",
                    "override_reason": None,
                    "reviewed_by": "performance-test",
                    "reviewed_at": now,
                    "contact_count": CONTACTS_PER_COMPANY,
                    "has_usable_contact": True,
                    "has_usable_email": True,
                    "preferred_role_category": "procurement",
                    "created_at": now,
                    "updated_at": now,
                }
                for index, company_id in enumerate(company_ids)
            ],
        )
        contact_payloads: list[dict[str, object]] = []
        link_payloads: list[dict[str, object]] = []
        channel_payloads: list[dict[str, object]] = []
        for company_index, company_id in enumerate(company_ids):
            scenario = company_index % 10
            for contact_index in range(CONTACTS_PER_COMPANY):
                contact_id = _id(f"contact-{company_index}-{contact_index}")
                selected_contact = contact_index < 2
                email = f"buyer-{company_index}-{contact_index}@company-{company_index}.example"
                verification = "source_verified"
                if selected_contact and scenario == 1:
                    verification = "invalid"
                if selected_contact and scenario == 2:
                    email = f"duplicate-{company_index}@company-{company_index}.example"
                contact_payloads.append(
                    {
                        "id": contact_id,
                        "company_id": company_id,
                        "name": f"Buyer {company_index}-{contact_index}",
                        "normalized_name": f"buyer {company_index}-{contact_index}",
                        "title_raw": "Procurement Director" if selected_contact else "Specialist",
                        "department": "procurement",
                        "seniority": "director" if selected_contact else "specialist",
                        "status": "active",
                        "invalid_reason": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                link_payloads.append(
                    {
                        "id": _id(f"link-{company_index}-{contact_index}"),
                        "company_id": company_id,
                        "contact_id": contact_id,
                        "raw_title": "Procurement Director" if selected_contact else "Specialist",
                        "role_category": "procurement" if selected_contact else "warehouse",
                        "seniority": "director" if selected_contact else "specialist",
                        "is_department_contact": contact_index >= 8,
                        "status": "active",
                        "first_seen_at": now,
                        "last_seen_at": now,
                        "source_import_row_id": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                channel_payloads.append(
                    {
                        "contact_id": contact_id,
                        "channel_type": "email",
                        "normalized_value": email,
                        "display_value": email,
                        "verification_status": verification,
                        "source": "performance-test",
                        "source_reference": f"performance:{company_index}:{contact_index}",
                        "source_retrieved_at": now,
                        "verified_at": now if verification == "source_verified" else None,
                        "confidence": 0.9 if verification == "source_verified" else 0.0,
                    }
                )
        await session.execute(insert(ContactModel), contact_payloads)
        await session.execute(insert(CompanyContactModel), link_payloads)
        await session.execute(insert(ContactChannelModel), channel_payloads)
        await session.execute(
            insert(SuppressionEntryModel),
            [
                {
                    "id": _id(f"suppression-{index}"),
                    "email": None,
                    "domain": f"company-{index}.example",
                    "company": None,
                    "active": True,
                    "reason": "performance suppression",
                    "source": "performance-test",
                    "created_by": "performance-test",
                    "deactivated_by": None,
                    "deactivated_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
                for index in range(0, COMPANY_COUNT, 10)
            ],
        )
        await uow.commit()

    statement_count = 0

    def count_statement(*_: object) -> None:
        nonlocal statement_count
        statement_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        tracemalloc.start()
        started = perf_counter()
        submission = await UmailExportWorkflow(uow_factory).prepare(
            routing_run_id=routing_run_id,
            company_ids=company_ids,
            campaign="D5d2a 500-company sample",
        )
        preparation_seconds = perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)

    csv_started = perf_counter()
    content = render_umail_csv(submission.rows, campaign=submission.batch.campaign)
    csv_seconds = perf_counter() - csv_started

    assert submission.batch.total_rows == 1000
    assert submission.batch.ready_count == 750
    assert submission.batch.suppressed_count == 100
    assert submission.batch.invalid_count == 100
    assert submission.batch.duplicate_count == 50
    assert preparation_seconds < 30
    assert csv_seconds < 10
    assert peak_bytes < 128 * 1024 * 1024
    assert statement_count <= 15
    assert len(content) > 10_000
