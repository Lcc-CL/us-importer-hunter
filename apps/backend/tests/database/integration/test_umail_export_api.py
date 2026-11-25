"""D5d2a PostgreSQL API closure for B-route export and suppression."""

import csv
import io
import json
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update

from app.database.models.contact import ContactChannelModel, ContactModel
from app.database.models.import_resolution import CompanyContactModel
from app.database.models.outreach import OutcomeModel, OutreachModel
from app.database.models.umail_export import UmailExportBatchModel, UmailExportRowModel
from app.database.repositories.mail_delivery import MailDeliveryRepository
from app.domain.operator import AuditActor
from app.workflows.mail_delivery.workflow import (
    CampaignRequest,
    MailCampaignWorkflow,
    configured_sender,
    sender_fingerprint,
)
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_mail_delivery import configured_settings
from tests.database.integration.test_prospect_routing_api import (
    make_client,
    make_runner,
    upload_mixed_routing_fixture,
)


async def test_b_export_preview_suppression_download_and_no_send(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        session_id = await upload_mixed_routing_fixture(client)
        resolved = await client.post(f"/api/v1/import-sessions/{session_id}/resolve")
        assert resolved.status_code == 202, resolved.text
        assert await runner.run_once(owner="d5d2a-resolution") is True
        routed = await client.post(
            f"/api/v1/import-sessions/{session_id}/routing-runs",
            json={
                "criteria": {
                    "target_product_keywords": ["hardware"],
                    "target_hs_codes": ["8205"],
                    "preferred_origin_countries": ["China"],
                    "preferred_pol": ["Shanghai"],
                    "preferred_pod": ["Los Angeles"],
                },
                "campaign_name": "D5d2a integration",
            },
        )
        assert routed.status_code == 202, routed.text
        routing_run_id = str(routed.json()["routing_run_id"])
        assert await runner.run_once(owner="d5d2a-routing") is True
        route_page = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/routes",
            params={"limit": 200},
        )
        routes = cast(list[dict[str, object]], route_page.json()["routes"])
        selected = [
            route
            for route in routes
            if route["review_status"] == "suggested" and route["has_usable_email"] is True
        ][:4]
        assert len(selected) == 4
        for route in selected:
            reviewed = await client.post(
                f"/api/v1/prospect-routes/{route['route_id']}/review",
                json={
                    "action": "override",
                    "effective_tier": "B",
                    "override_reason": "D5d2a export fixture",
                    "reviewed_by": "D5d2a Reviewer",
                },
            )
            assert reviewed.status_code == 200, reviewed.text

        company_ids = [str(route["company_id"]) for route in selected]
        async with uow_factory() as uow:
            session = uow._session
            assert session is not None
            channel_rows = list(
                (
                    await session.execute(
                        select(
                            CompanyContactModel.company_id,
                            ContactChannelModel.contact_id,
                            ContactChannelModel.normalized_value,
                        )
                        .join(
                            ContactChannelModel,
                            ContactChannelModel.contact_id
                            == CompanyContactModel.contact_id,
                        )
                        .where(
                            CompanyContactModel.company_id.in_(company_ids),
                            ContactChannelModel.channel_type == "email",
                        )
                        .order_by(CompanyContactModel.company_id)
                    )
                ).tuples()
            )
            channels = {
                str(company_id): (contact_id, email)
                for company_id, contact_id, email in channel_rows
            }
            ready_email = channels[company_ids[0]][1]
            ready_contact_id = channels[company_ids[0]][0]
            suppressed_email = channels[company_ids[1]][1]
            invalid_contact_id = channels[company_ids[2]][0]
            duplicate_contact_id = channels[company_ids[3]][0]
            await session.execute(
                update(ContactModel)
                .where(ContactModel.id == ready_contact_id)
                .values(name="Alice Buyer", normalized_name="alice buyer")
            )
            await session.execute(
                update(ContactChannelModel)
                .where(
                    ContactChannelModel.contact_id == invalid_contact_id,
                    ContactChannelModel.channel_type == "email",
                )
                .values(verification_status="invalid")
            )
            await session.execute(
                update(ContactChannelModel)
                .where(
                    ContactChannelModel.contact_id == duplicate_contact_id,
                    ContactChannelModel.channel_type == "email",
                )
                .values(normalized_value=ready_email, display_value=ready_email)
            )
            await uow.commit()

        suppression = await client.post(
            "/api/v1/suppressions",
            json={
                "email": suppressed_email,
                "reason": "manual exclusion",
                "source": "integration_test",
                "created_by": "D5d2a Reviewer",
            },
        )
        assert suppression.status_code == 201, suppression.text
        created = await client.post(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/umail-export-batches",
            json={"company_ids": company_ids, "campaign": "D5d2a integration"},
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["ready_count"] == 1
        assert payload["suppressed_count"] == 1
        assert payload["invalid_count"] == 1
        assert payload["duplicate_count"] == 1
        assert payload["sent"] is False
        statuses = [row["status"] for row in payload["rows"]]
        assert statuses == ["ready", "suppressed", "invalid", "duplicate"]

        repeated = await client.post(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/umail-export-batches",
            json={"company_ids": company_ids, "campaign": "D5d2a integration"},
        )
        assert repeated.status_code == 201
        assert repeated.json()["batch_id"] == payload["batch_id"]
        assert repeated.json()["content_sha256"] == payload["content_sha256"]
        assert repeated.json()["reused"] is True

        first_download = await client.get(
            f"/api/v1/umail-export-batches/{payload['batch_id']}/download"
        )
        second_download = await client.get(
            f"/api/v1/umail-export-batches/{payload['batch_id']}/download"
        )
        assert first_download.status_code == 200
        assert first_download.content == second_download.content
        assert first_download.headers["x-content-sha256"] == payload["content_sha256"]
        assert first_download.headers["x-email-sent"] == "false"
        assert ready_email.encode() in first_download.content
        assert suppressed_email.encode() not in first_download.content
        csv_rows = list(
            csv.DictReader(io.StringIO(first_download.content.decode("utf-8-sig")))
        )
        ready_rows = [row for row in payload["rows"] if row["status"] == "ready"]
        assert len(csv_rows) == len(ready_rows) == 1
        assert [row["export_batch_id"] for row in csv_rows] == [payload["batch_id"]]
        assert [row["export_row_id"] for row in csv_rows] == [
            row["row_id"] for row in ready_rows
        ]
        assert csv_rows[0]["first_name"] == "Alice"
        assert csv_rows[0]["last_name"] == "Buyer"
        assert csv_rows[0]["phone"] == ""
        assert csv_rows[0]["country"] == ""
        assert json.loads(csv_rows[0]["route_reasons"]) == ready_rows[0]["route_reasons"]

        async with uow_factory() as uow:
            session = uow._session
            assert session is not None
            assert int(
                await session.scalar(select(func.count()).select_from(OutreachModel)) or 0
            ) == 0
            assert int(
                await session.scalar(select(func.count()).select_from(OutcomeModel)) or 0
            ) == 0
            assert int(
                await session.scalar(select(func.count()).select_from(UmailExportBatchModel)) or 0
            ) == 1
            assert int(
                await session.scalar(select(func.count()).select_from(UmailExportRowModel)) or 0
            ) == 4
            mail_campaign_id = uuid4()
            campaign = await MailCampaignWorkflow(
                MailDeliveryRepository(session), session.commit, configured_settings()
            ).prepare(
                CampaignRequest(
                    id=mail_campaign_id,
                    name="B outreach",
                    export_id=UUID(payload["batch_id"]),
                    outreach_id=None,
                    draft_version=None,
                    recipient=None,
                    subject="Logistics for {company}",
                    body="Hi {first_name}",
                )
            )
            assert campaign.counts == {"pending": 1}
            previews = await MailDeliveryRepository(session).preview(mail_campaign_id, 0, 20)
            assert [item.recipient for item in previews] == [ready_email]
            assert previews[0].body.startswith("Hi Alice\n")
            repo = MailDeliveryRepository(session)
            sender = configured_sender(configured_settings())
            assert sender is not None
            fingerprint = sender_fingerprint(sender)
            await repo.transition(mail_campaign_id, "approve", AuditActor("Reviewer"), fingerprint)
            assert await repo.claim(fingerprint, 2) is None
            blocked = (await repo.preview(mail_campaign_id, 0, 1))[0]
            assert blocked.result_code == "recent_or_reserved_touch"
            persisted_ready_rows = list(
                await session.scalars(
                    select(UmailExportRowModel)
                    .where(
                        UmailExportRowModel.batch_id == payload["batch_id"],
                        UmailExportRowModel.status == "ready",
                    )
                    .order_by(UmailExportRowModel.position)
                )
            )
            assert [str(row.id) for row in persisted_ready_rows] == [
                row["export_row_id"] for row in csv_rows
            ]

        # An independently prepared export must not inherit the first batch reservation.
        second_export = await client.post(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/umail-export-batches",
            json={"company_ids": company_ids, "campaign": "Separate campaign"},
        )
        assert second_export.status_code == 201, second_export.text
        blocked_export = await client.get(
            f"/api/v1/umail-export-batches/{second_export.json()['batch_id']}/download"
        )
        assert blocked_export.status_code == 409
        assert "recently contacted" in blocked_export.json()["message"]
        added_after_preview = await client.post(
            "/api/v1/suppressions",
            json={
                "email": ready_email, "reason": "late opt-out",
                "source": "integration_test", "created_by": "Reviewer",
            },
        )
        assert added_after_preview.status_code == 201
        stale_export = await client.get(
            f"/api/v1/umail-export-batches/{payload['batch_id']}/download"
        )
        assert stale_export.status_code == 409
        assert "suppression after the preview" in stale_export.json()["message"]

        deactivated = await client.post(
            f"/api/v1/suppressions/{suppression.json()['suppression_id']}/deactivate",
            json={"deactivated_by": "D5d2a Reviewer"},
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["active"] is False
