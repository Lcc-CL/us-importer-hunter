"""D5d2b PostgreSQL API closure for offline Umail result feedback."""

import csv
import hashlib
import io
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, insert, select

from app.database.models.bulk_import import ImportSessionModel
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactModel
from app.database.models.opportunity import OpportunityModel
from app.database.models.outreach import EmailDraftModel, OutcomeModel, OutreachModel
from app.database.models.prospect_routing import ProspectRoutingRunModel
from app.database.models.umail_export import (
    SuppressionEntryModel,
    UmailExportBatchModel,
    UmailExportRowModel,
)
from app.database.models.umail_feedback import (
    ContactEngagementEventModel,
    UmailResultRowModel,
)
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_prospect_routing_api import make_client


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"d5d2b-integration:{value}")


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "export_batch_id",
            "export_row_id",
            "email",
            "campaign",
            "event_type",
            "occurred_at",
            "bounce_type",
            "message_id",
            "note",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


async def _seed_feedback_exports(uow_factory: UowFactory) -> dict[str, UUID]:
    now = datetime(2026, 8, 1, 10, tzinfo=UTC)
    session_id = _id("session")
    routing_run_id = _id("routing-run")
    batch_alpha_id = _id("batch-alpha")
    batch_alpha_duplicate_id = _id("batch-alpha-duplicate")
    labels = (
        "exact",
        "batch",
        "campaign",
        "window",
        "ambiguous-one",
        "ambiguous-two",
        "clicked",
        "hard",
        "soft",
        "unknown",
        "unsubscribe",
        "complaint",
        "active-suppressed",
    )
    ids = {
        "session": session_id,
        "routing_run": routing_run_id,
        "batch_alpha": batch_alpha_id,
        "batch_alpha_duplicate": batch_alpha_duplicate_id,
        "opportunity": _id("opportunity"),
        "outreach": _id("outreach"),
    }
    for label in labels:
        ids[f"company_{label}"] = _id(f"company-{label}")
        ids[f"contact_{label}"] = _id(f"contact-{label}")
        ids[f"row_{label}"] = _id(f"row-{label}")

    async with uow_factory() as uow:
        session = uow._session
        assert session is not None
        await session.execute(
            insert(ImportSessionModel),
            [
                {
                    "id": session_id,
                    "source": "d5d2b_integration",
                    "original_filename": "feedback-seed.csv",
                    "file_type": "csv",
                    "file_size_bytes": 1,
                    "file_sha256": hashlib.sha256(b"d5d2b-integration").hexdigest(),
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
                    "configuration_hash": hashlib.sha256(b"d5d2b-config").hexdigest(),
                    "entity_state_hash": hashlib.sha256(b"d5d2b-state").hexdigest(),
                    "execution_generation": 1,
                    "criteria_json": {"target_product_keywords": ["hardware"]},
                    "weights_snapshot_json": {},
                    "status": "completed",
                    "total_companies": len(labels),
                    "routed_companies": len(labels),
                    "blocked_companies": 0,
                    "tier_a_count": 0,
                    "tier_b_count": len(labels),
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
                    "id": ids[f"company_{label}"],
                    "name": f"Feedback {label.title()} Importer",
                    "normalized_name": f"feedback {label} importer",
                    "website": f"https://{label}.example.test",
                    "website_host": f"{label}.example.test",
                    "verified": True,
                    "created_at": now,
                }
                for label in labels
            ],
        )
        await session.execute(
            insert(ContactModel),
            [
                {
                    "id": ids[f"contact_{label}"],
                    "company_id": ids[f"company_{label}"],
                    "name": f"Buyer {label.title()}",
                    "normalized_name": f"buyer {label}",
                    "title_raw": "Procurement Director",
                    "department": "procurement",
                    "seniority": "director",
                    "status": "active",
                    "invalid_reason": None,
                    "created_at": now,
                    "updated_at": now,
                }
                for label in labels
            ],
        )
        await session.execute(
            insert(UmailExportBatchModel),
            [
                {
                    "id": batch_alpha_id,
                    "routing_run_id": routing_run_id,
                    "execution_generation": 1,
                    "campaign": "Campaign Alpha",
                    "mapping_version": "umail-export-contract-v1",
                    "selection_hash": hashlib.sha256(b"batch-alpha").hexdigest(),
                    "status": "prepared",
                    "total_rows": len(labels) - 1,
                    "ready_count": len(labels) - 1,
                    "suppressed_count": 0,
                    "invalid_count": 0,
                    "duplicate_count": 0,
                    "content_sha256": hashlib.sha256(b"alpha-content").hexdigest(),
                    "downloaded_at": None,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": batch_alpha_duplicate_id,
                    "routing_run_id": routing_run_id,
                    "execution_generation": 1,
                    "campaign": "Campaign Alpha",
                    "mapping_version": "umail-export-contract-v1",
                    "selection_hash": hashlib.sha256(b"batch-alpha-duplicate").hexdigest(),
                    "status": "prepared",
                    "total_rows": 1,
                    "ready_count": 1,
                    "suppressed_count": 0,
                    "invalid_count": 0,
                    "duplicate_count": 0,
                    "content_sha256": hashlib.sha256(b"duplicate-content").hexdigest(),
                    "downloaded_at": None,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        export_rows: list[dict[str, object]] = []
        primary_labels = tuple(label for label in labels if label != "ambiguous-two")
        for position, label in enumerate(primary_labels, start=1):
            email_label = "ambiguous" if label == "ambiguous-one" else label
            export_rows.append(
                {
                    "id": ids[f"row_{label}"],
                    "batch_id": batch_alpha_id,
                    "position": position,
                    "company_id": ids[f"company_{label}"],
                    "contact_id": ids[f"contact_{label}"],
                    "company_name": f"Feedback {label.title()} Importer",
                    "company_website": f"https://{label}.example.test",
                    "contact_name": f"Buyer {label.title()}",
                    "first_name": "Buyer",
                    "last_name": label.title(),
                    "contact_title": "Procurement Director",
                    "contact_role": "procurement",
                    "contact_seniority": "director",
                    "is_department_contact": False,
                    "email": f"{email_label}@example.test",
                    "phone": None,
                    "country": "US",
                    "route": "B",
                    "route_review_status": "confirmed",
                    "pre_score": 72.0,
                    "route_reasons": ["D5D2B_INTEGRATION"],
                    "status": "ready",
                    "exclusion_reason": None,
                    "row_fingerprint": hashlib.sha256(label.encode()).hexdigest(),
                    "created_at": now,
                }
            )
        export_rows.append(
            {
                "id": ids["row_ambiguous-two"],
                "batch_id": batch_alpha_duplicate_id,
                "position": 1,
                "company_id": ids["company_ambiguous-two"],
                "contact_id": ids["contact_ambiguous-two"],
                "company_name": "Feedback Ambiguous Two Importer",
                "company_website": "https://ambiguous-two.example.test",
                "contact_name": "Buyer Ambiguous Two",
                "first_name": "Buyer",
                "last_name": "Ambiguous Two",
                "contact_title": "Procurement Director",
                "contact_role": "procurement",
                "contact_seniority": "director",
                "is_department_contact": False,
                "email": "ambiguous@example.test",
                "phone": None,
                "country": "US",
                "route": "B",
                "route_review_status": "confirmed",
                "pre_score": 70.0,
                "route_reasons": ["D5D2B_AMBIGUOUS"],
                "status": "ready",
                "exclusion_reason": None,
                "row_fingerprint": hashlib.sha256(b"ambiguous-two").hexdigest(),
                "created_at": now,
            }
        )
        await session.execute(insert(UmailExportRowModel), export_rows)
        await session.execute(
            insert(OpportunityModel),
            [
                {
                    "id": ids["opportunity"],
                    "company_id": ids["company_exact"],
                    "user_id": _id("user"),
                    "stage": "qualified",
                    "stage_reason": "baseline",
                    "score": 72.0,
                    "confidence": 0.8,
                    "priority": "medium",
                    "created_at": now,
                }
            ],
        )
        await session.execute(
            insert(OutreachModel),
            [
                {
                    "id": ids["outreach"],
                    "opportunity_id": ids["opportunity"],
                    "contact_id": ids["contact_exact"],
                    "status": "active",
                    "approved_version": 1,
                    "sent_version": 7,
                    "follow_up_active": True,
                    "closed_reason": None,
                    "created_at": now,
                }
            ],
        )
        await session.execute(
            insert(EmailDraftModel),
            [
                {
                    "outreach_id": ids["outreach"],
                    "version": 1,
                    "subject": "Existing draft",
                    "body": "Existing body",
                    "approval_status": "approved",
                    "approved_at": now,
                    "approved_by_name": "Existing Reviewer",
                    "provider": "fake",
                    "model": "fake-static-v1",
                    "prompt_version": "existing-v1",
                    "context_fingerprint": hashlib.sha256(b"existing-draft").hexdigest(),
                    "generated_at": now,
                }
            ],
        )
        await session.execute(
            insert(OutcomeModel),
            [
                {
                    "outreach_id": ids["outreach"],
                    "position": 1,
                    "kind": "manual_note",
                    "detail": "Existing outcome",
                    "draft_version": 1,
                    "occurred_at": now,
                }
            ],
        )
        await session.execute(
            insert(SuppressionEntryModel),
            [
                {
                    "id": _id("suppression-active"),
                    "email": "active-suppressed@example.test",
                    "domain": None,
                    "company": None,
                    "active": True,
                    "reason": "existing hard bounce",
                    "source": "integration_test",
                    "created_by": "existing-reviewer",
                    "deactivated_by": None,
                    "deactivated_at": None,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": _id("suppression-inactive"),
                    "email": "unsubscribe@example.test",
                    "domain": None,
                    "company": None,
                    "active": False,
                    "reason": "historical unsubscribe",
                    "source": "integration_test",
                    "created_by": "existing-reviewer",
                    "deactivated_by": "existing-reviewer",
                    "deactivated_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        await uow.commit()
    return ids


async def test_feedback_preview_apply_matching_events_and_suppression(
    uow_factory: UowFactory,
) -> None:
    ids = await _seed_feedback_exports(uow_factory)
    occurred = "2026-08-02T12:00:00Z"
    rows = [
        {
            "export_batch_id": str(ids["batch_alpha"]),
            "export_row_id": str(ids["row_exact"]),
            "email": "exact@example.test",
            "campaign": "Campaign Alpha",
            "event_type": "sent",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-exact",
            "note": "exact row id",
        },
        {
            "export_batch_id": str(ids["batch_alpha"]),
            "export_row_id": "",
            "email": "batch@example.test",
            "campaign": "",
            "event_type": "delivered",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-batch",
            "note": "batch email",
        },
        {
            "export_batch_id": "",
            "export_row_id": "",
            "email": "campaign@example.test",
            "campaign": "Campaign Alpha",
            "event_type": "replied",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-campaign",
            "note": "campaign email",
        },
        {
            "export_batch_id": "",
            "export_row_id": "",
            "email": "window@example.test",
            "campaign": "",
            "event_type": "opened",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-window",
            "note": "email window",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_clicked"]),
            "email": "clicked@example.test",
            "campaign": "Campaign Alpha",
            "event_type": "clicked",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-clicked",
            "note": "clicked",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_hard"]),
            "email": "hard@example.test",
            "campaign": "",
            "event_type": "hard_bounce",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-hard",
            "note": "hard suppression",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_soft"]),
            "email": "soft@example.test",
            "campaign": "",
            "event_type": "soft_bounce",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-soft",
            "note": "no suppression",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_unknown"]),
            "email": "unknown@example.test",
            "campaign": "",
            "event_type": "bounce",
            "occurred_at": occurred,
            "bounce_type": "mystery",
            "message_id": "m-unknown",
            "note": "needs review",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_unsubscribe"]),
            "email": "unsubscribe@example.test",
            "campaign": "",
            "event_type": "unsubscribed",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-unsubscribe",
            "note": "reactivate suppression",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_complaint"]),
            "email": "complaint@example.test",
            "campaign": "",
            "event_type": "complained",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-complaint",
            "note": "complaint suppression",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_active-suppressed"]),
            "email": "active-suppressed@example.test",
            "campaign": "",
            "event_type": "hard_bounce",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-active",
            "note": "existing active suppression",
        },
        {
            "export_batch_id": "",
            "export_row_id": "",
            "email": "ambiguous@example.test",
            "campaign": "Campaign Alpha",
            "event_type": "clicked",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-ambiguous",
            "note": "ambiguous",
        },
        {
            "export_batch_id": "",
            "export_row_id": "",
            "email": "not-exported@example.test",
            "campaign": "Campaign Missing",
            "event_type": "delivered",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-unmatched",
            "note": "unmatched",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_exact"]),
            "email": "wrong@example.test",
            "campaign": "Campaign Alpha",
            "event_type": "delivered",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-mismatch",
            "note": "invalid consistency",
        },
        {
            "export_batch_id": "",
            "export_row_id": str(ids["row_exact"]),
            "email": "exact@example.test",
            "campaign": "Campaign Alpha",
            "event_type": "teleported",
            "occurred_at": occurred,
            "bounce_type": "",
            "message_id": "m-invalid",
            "note": "unsupported",
        },
    ]
    rows.append(dict(rows[0]))
    content = _csv_bytes(rows)

    async for client in make_client(uow_factory):
        uploaded = await client.post(
            "/api/v1/umail-result-imports",
            data={"created_by": "D5d2b Reviewer"},
            files={"file": ("umail-results.csv", content, "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        preview = uploaded.json()
        assert preview["input_row_count"] == 16
        assert preview["matched_count"] == 11
        assert preview["unmatched_count"] == 1
        assert preview["ambiguous_count"] == 1
        assert preview["invalid_count"] == 2
        assert preview["duplicate_count"] == 1
        assert preview["projected_event_count"] == 11
        assert preview["projected_suppression_count"] == 3
        assert preview["applied_event_count"] == 0
        assert preview["suppression_created_count"] == 0
        assert preview["system_sent_email"] is False
        result_import_id = preview["result_import_id"]

        repeated_file = await client.post(
            "/api/v1/umail-result-imports",
            files={"file": ("same-results.csv", content, "text/csv")},
        )
        assert repeated_file.status_code == 200
        assert repeated_file.json()["result_import_id"] == result_import_id
        assert repeated_file.json()["reused"] is True

        row_page = await client.get(
            f"/api/v1/umail-result-imports/{result_import_id}/rows",
            params={"limit": 50},
        )
        assert row_page.status_code == 200
        response_rows = row_page.json()["rows"]
        assert [row["match_method"] for row in response_rows[:4]] == [
            "export_row_id",
            "batch_email",
            "campaign_email",
            "email_time_window",
        ]
        assert response_rows[7]["canonical_event_type"] == "bounce_unknown"
        assert response_rows[-1]["match_status"] == "duplicate"
        ambiguous = await client.get(
            f"/api/v1/umail-result-imports/{result_import_id}/rows",
            params={"match_status": "ambiguous"},
        )
        assert ambiguous.json()["total"] == 1
        suppressing = await client.get(
            f"/api/v1/umail-result-imports/{result_import_id}/rows",
            params={"suppression_impact": True},
        )
        assert suppressing.json()["total"] == 4

        rejected_confirmation = await client.post(
            f"/api/v1/umail-result-imports/{result_import_id}/apply",
            json={"confirmed": False},
        )
        assert rejected_confirmation.status_code == 422

        async with uow_factory() as uow:
            session = uow._session
            assert session is not None
            assert int(
                await session.scalar(
                    select(func.count()).select_from(ContactEngagementEventModel)
                )
                or 0
            ) == 0
            assert int(
                await session.scalar(select(func.count()).select_from(SuppressionEntryModel))
                or 0
            ) == 2
            assert await session.scalar(
                select(OutreachModel.sent_version).where(OutreachModel.id == ids["outreach"])
            ) == 7

        applied = await client.post(
            f"/api/v1/umail-result-imports/{result_import_id}/apply",
            json={"confirmed": True},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["status"] == "partial_applied"
        assert applied.json()["applied_event_count"] == 11
        assert applied.json()["suppression_created_count"] == 3
        assert applied.json()["system_sent_email"] is False

        statistics = await client.get(
            f"/api/v1/umail-result-imports/{result_import_id}/statistics"
        )
        assert statistics.status_code == 200
        stats = statistics.json()
        assert stats["total_result_rows"] == 16
        assert stats["rates"]["total_events"] == 11
        assert set(stats["rates"]["event_counts"]) == {
            "sent",
            "delivered",
            "hard_bounced",
            "soft_bounced",
            "bounce_unknown",
            "unsubscribed",
            "complained",
            "replied",
            "opened",
            "clicked",
        }
        assert stats["campaign_statistics"]["Campaign Alpha"]["sent"] == 1
        assert stats["route_statistics"]["B"]["hard_bounced"] == 2
        assert len(stats["company_statistics"]) == 11

        repeated_apply = await client.post(
            f"/api/v1/umail-result-imports/{result_import_id}/apply",
            json={"confirmed": True},
        )
        assert repeated_apply.status_code == 200
        assert repeated_apply.json()["reused"] is True
        assert repeated_apply.json()["applied_event_count"] == 11

        duplicate_event_content = _csv_bytes([{**rows[0], "note": "different file hash"}])
        duplicate_event = await client.post(
            "/api/v1/umail-result-imports",
            files={
                "file": (
                    "duplicate-event.csv",
                    duplicate_event_content,
                    "text/csv",
                )
            },
        )
        assert duplicate_event.status_code == 201
        assert duplicate_event.json()["duplicate_count"] == 1
        duplicate_import_id = duplicate_event.json()["result_import_id"]
        duplicate_applied = await client.post(
            f"/api/v1/umail-result-imports/{duplicate_import_id}/apply",
            json={"confirmed": True},
        )
        assert duplicate_applied.status_code == 200
        assert duplicate_applied.json()["applied_event_count"] == 0

    async with uow_factory() as uow:
        session = uow._session
        assert session is not None
        assert int(
            await session.scalar(
                select(func.count()).select_from(ContactEngagementEventModel)
            )
            or 0
        ) == 11
        event_types = set(
            await session.scalars(select(ContactEngagementEventModel.event_type))
        )
        assert event_types == {
            "sent",
            "delivered",
            "hard_bounced",
            "soft_bounced",
            "bounce_unknown",
            "unsubscribed",
            "complained",
            "replied",
            "opened",
            "clicked",
        }
        unknown_event = await session.scalar(
            select(ContactEngagementEventModel).where(
                ContactEngagementEventModel.event_type == "bounce_unknown"
            )
        )
        assert unknown_event is not None
        assert unknown_event.metadata_json["needs_review"] is True
        assert int(
            await session.scalar(select(func.count()).select_from(SuppressionEntryModel))
            or 0
        ) == 5
        assert int(
            await session.scalar(
                select(func.count())
                .select_from(SuppressionEntryModel)
                .where(SuppressionEntryModel.email == "unsubscribe@example.test")
            )
            or 0
        ) == 2
        assert int(
            await session.scalar(
                select(func.count())
                .select_from(SuppressionEntryModel)
                .where(
                    SuppressionEntryModel.email == "unsubscribe@example.test",
                    SuppressionEntryModel.active.is_(True),
                )
            )
            or 0
        ) == 1
        assert int(
            await session.scalar(
                select(func.count())
                .select_from(SuppressionEntryModel)
                .where(SuppressionEntryModel.email == "active-suppressed@example.test")
            )
            or 0
        ) == 1
        assert await session.scalar(
            select(OutreachModel.sent_version).where(OutreachModel.id == ids["outreach"])
        ) == 7
        assert int(
            await session.scalar(select(func.count()).select_from(EmailDraftModel)) or 0
        ) == 1
        assert int(
            await session.scalar(select(func.count()).select_from(OutcomeModel)) or 0
        ) == 1
        export_rows = list(
            await session.scalars(
                select(UmailExportRowModel).order_by(UmailExportRowModel.id)
            )
        )
        assert all(row.status == "ready" for row in export_rows)
        assert int(
            await session.scalar(
                select(func.count())
                .select_from(UmailResultRowModel)
                .where(UmailResultRowModel.match_status == "ambiguous")
            )
            or 0
        ) == 1
