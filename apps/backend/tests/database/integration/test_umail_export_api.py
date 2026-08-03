"""D5d2a PostgreSQL API closure for B-route export and suppression."""

from typing import cast

from sqlalchemy import func, select, update

from app.database.models.contact import ContactChannelModel
from app.database.models.import_resolution import CompanyContactModel
from app.database.models.outreach import OutcomeModel, OutreachModel
from app.database.models.umail_export import UmailExportBatchModel, UmailExportRowModel
from tests.database.integration.conftest import UowFactory
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
            suppressed_email = channels[company_ids[1]][1]
            invalid_contact_id = channels[company_ids[2]][0]
            duplicate_contact_id = channels[company_ids[3]][0]
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

        deactivated = await client.post(
            f"/api/v1/suppressions/{suppression.json()['suppression_id']}/deactivate",
            json={"deactivated_by": "D5d2a Reviewer"},
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["active"] is False
