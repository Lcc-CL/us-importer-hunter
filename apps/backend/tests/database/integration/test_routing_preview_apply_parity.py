"""D5e2g.2 Routing Preview/Apply semantic parity tests (real PostgreSQL).

Preview and Apply must share the exact same evaluator, taxonomy and
rules_version, and must produce identical tier/score/reason_codes/blocked for
every company. Importer company country drives NON_US_TARGET; shipment/supplier
origin (China) must never exclude a US importer.
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.main import create_app
from app.workflows.import_resolution import (
    ImportEntityResolutionWorkflow,
    ImportProcessingJobCoordinator,
    ImportProcessingJobRunner,
)
from app.workflows.prospect_routing import ProspectRoutingExecutionWorkflow
from tests.database.integration.conftest import UowFactory

MAPPING = (
    '{"company_name":"company","external_company_id":"external_id",'
    '"website":"website","address":"address","company_type":"company_type",'
    '"country":"country","contact_name":"contact","contact_email":"email",'
    '"contact_title":"title","product_description":"product","hs_code":"hs",'
    '"shipment_date":"date","origin_country":"origin","pol":"pol","pod":"pod",'
    '"amount":"amount","last_import_at":"last_import"}'
)
HEADER = (
    "company,external_id,website,address,company_type,country,contact,email,title,"
    "product,hs,date,origin,pol,pod,amount,last_import"
)


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


def make_runner(uow_factory: UowFactory) -> ImportProcessingJobRunner:
    coordinator = ImportProcessingJobCoordinator(
        uow_factory,
        lease_ttl=timedelta(seconds=120),
        retry_delay=timedelta(0),
    )
    return ImportProcessingJobRunner(
        coordinator=coordinator,
        workflow=ImportEntityResolutionWorkflow(uow_factory),
        routing_workflow=ProspectRoutingExecutionWorkflow(uow_factory),
    )


async def upload_fixture(client: AsyncClient) -> str:
    rows = "\n".join(
        (
            (
                "Atlas Fitness,ATLAS-1,atlas.example,100 Main St Austin TX,importer,"
                "United States,Maria Chen,maria@atlas.example,Director Logistics,"
                "fitness equipment,950691,2026-07-01,China,Shanghai,Los Angeles,"
                "118000,2026-07-01"
            ),
            (
                "Atlas Fitness LLC,,atlas.example,900 Ocean Dr Miami FL,warehouse,"
                "United States,Pat Lee,pat@atlas-llc.example,Procurement Manager,"
                "fitness equipment,950691,2026-07-01,China,Shanghai,Los Angeles,"
                "50000,2026-07-01"
            ),
            (
                "Beta Fitness,BETA-1,beta.example,300 Hill Rd Denver CO,importer,"
                "United States,Tom Yu,tom@beta.example,Logistics Director,"
                "fitness equipment,950691,2026-07-01,China,Shanghai,Los Angeles,"
                "118000,2026-07-01"
            ),
            (
                "Canada Fitness,CAN-1,canada.example,500 King St Toronto ON,importer,"
                "Canada,Sara Wu,sara@canada.example,Logistics Director,"
                "fitness equipment,950691,2026-07-01,China,Shanghai,Los Angeles,"
                "118000,2026-07-01"
            ),
            (
                "Unknown Fitness,UNK-1,,600 Oak Rd Chicago IL,importer,,Dan Li,,,"
                "fitness equipment,950691,2026-07-01,China,Shanghai,Los Angeles,,"
            ),
        )
    )
    response = await client.post(
        "/api/v1/import-sessions",
        data={"source": "netease_foreign_trade", "mapping": MAPPING},
        files={
            "file": (
                "parity.csv",
                (f"{HEADER}\n{rows}").encode(),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


async def preview(
    client: AsyncClient,
    session_id: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/import-sessions/{session_id}/routing-preview",
        json={
            "criteria": {
                "target_product_keywords": ["fitness", "gym equipment"],
                "target_hs_codes": ["9506", "950691"],
                "preferred_origin_countries": [],
                "preferred_pol": [],
                "preferred_pod": [],
            },
            "campaign_name": "D5e2g2 parity",
        },
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json())


async def test_preview_and_apply_produce_identical_decisions(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        session_id = await upload_fixture(client)
        resolution = await client.post(
            f"/api/v1/import-sessions/{session_id}/resolve"
        )
        assert resolution.status_code == 202, resolution.text
        assert await runner.run_once(owner="parity-resolution-worker") is True
        resolution_body = await client.get(
            f"/api/v1/import-sessions/{session_id}/resolution"
        )
        assert resolution_body.status_code == 200
        canonical_companies = resolution_body.json()["canonical_company_count"]
        canonical_contacts = resolution_body.json()["canonical_contact_count"]
        assert canonical_companies == 4  # Atlas, Beta, Canada, Unknown
        assert canonical_contacts >= 4

        preview_body = await preview(client, session_id)
        assert preview_body["rules_version"] == "real-routing-v1.1"
        assert preview_body["entity_pending_count"] == 1
        assert len(
            cast(list[dict[str, object]], preview_body["companies"])
        ) == canonical_companies
        totals = cast(dict[str, int], preview_body["totals"])
        assert sum(totals.values()) == canonical_companies
        preview_companies = {
            str(company["company_id"]): company
            for company in cast(
                list[dict[str, object]], preview_body["companies"]
            )
        }

        # Preview is deterministic across identical inputs.
        second_preview = await preview(client, session_id)
        assert (
            second_preview["companies"] == preview_body["companies"]
        )

        # A US importer with China shipment origin must not be D.
        beta = next(
            company
            for company in cast(
                list[dict[str, object]], preview_body["companies"]
            )
            if company["company_name"] == "Beta Fitness"
        )
        assert beta["tier"] in {"A", "B"}
        assert "NON_US_TARGET" not in cast(list[str], beta["reason_codes"])

        # An explicit non-US importer is D.
        canada = next(
            company
            for company in cast(
                list[dict[str, object]], preview_body["companies"]
            )
            if company["company_name"] == "Canada Fitness"
        )
        assert canada["tier"] == "D"
        assert "NON_US_TARGET" in cast(list[str], canada["reason_codes"])

        # Unknown importer country is unknown, never D.
        unknown = next(
            company
            for company in cast(
                list[dict[str, object]], preview_body["companies"]
            )
            if company["company_name"] == "Unknown Fitness"
        )
        assert unknown["tier"] != "D"
        assert "IMPORTER_COUNTRY_UNKNOWN" in cast(
            list[str], unknown["unknown_evidence"]
        )

        # The pending entity-review company is blocked in preview.
        conflict = next(
            company
            for company in cast(
                list[dict[str, object]], preview_body["companies"]
            )
            if company["tier"] == "blocked"
        )
        assert conflict["company_name"] == "Atlas Fitness"
        assert conflict["tier"] == "blocked"
        assert "UNRESOLVED_COMPANY_CONFLICT_BLOCKED" in cast(
            list[str], conflict["reason_codes"]
        )

        # Apply with the same data must persist identical decisions.
        submitted = await client.post(
            f"/api/v1/import-sessions/{session_id}/routing-runs",
            json={
                "criteria": {
                    "target_product_keywords": ["fitness", "gym equipment"],
                    "target_hs_codes": ["9506", "950691"],
                    "preferred_origin_countries": [],
                    "preferred_pol": [],
                    "preferred_pod": [],
                },
                "campaign_name": "D5e2g2 parity",
            },
        )
        assert submitted.status_code == 202, submitted.text
        routing_run_id = str(submitted.json()["routing_run_id"])
        assert await runner.run_once(owner="parity-routing-worker") is True

        run_response = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}"
        )
        assert run_response.status_code == 200
        assert run_response.json()["rules_version"] == "real-routing-v1.1"

        routes_response = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/routes",
            params={"limit": 20},
        )
        assert routes_response.status_code == 200
        routes = cast(
            list[dict[str, object]], routes_response.json()["routes"]
        )
        assert len(routes) == canonical_companies
        routes_by_company = {str(route["company_id"]): route for route in routes}

        for company_id, preview_company in preview_companies.items():
            route = routes_by_company[company_id]
            expected_tier = (
                None if preview_company["tier"] == "blocked"
                else preview_company["tier"]
            )
            assert route["recommended_tier"] == expected_tier
            assert route["pre_score"] == preview_company["pre_score"]
            assert set(cast(list[str], route["reason_codes"])) == set(
                cast(list[str], preview_company["reason_codes"])
            )
            if preview_company["tier"] == "blocked":
                assert route["review_status"] == "blocked"


async def test_pending_entity_review_blocks_apply_and_blocked_route_cannot_batch(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        session_id = await upload_fixture(client)
        resolution = await client.post(
            f"/api/v1/import-sessions/{session_id}/resolve"
        )
        assert resolution.status_code == 202
        assert await runner.run_once(owner="parity-blocked-resolution-worker") is True

        preview_body = await preview(client, session_id)
        assert preview_body["entity_pending_count"] == 1
        conflict = next(
            company
            for company in cast(
                list[dict[str, object]], preview_body["companies"]
            )
            if company["tier"] == "blocked"
        )
        assert conflict["company_name"] == "Atlas Fitness"
        assert conflict["tier"] == "blocked"

        submitted = await client.post(
            f"/api/v1/import-sessions/{session_id}/routing-runs",
            json={
                "criteria": {
                    "target_product_keywords": ["fitness"],
                    "target_hs_codes": ["950691"],
                    "preferred_origin_countries": [],
                    "preferred_pol": [],
                    "preferred_pod": [],
                },
                "campaign_name": "D5e2g2 blocked",
            },
        )
        assert submitted.status_code == 202
        routing_run_id = str(submitted.json()["routing_run_id"])
        assert await runner.run_once(owner="parity-blocked-routing-worker") is True

        routes_response = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/routes",
            params={"limit": 20},
        )
        routes = cast(
            list[dict[str, object]], routes_response.json()["routes"]
        )
        conflict_route = next(
            route
            for route in routes
            if route["company_name"] == "Atlas Fitness"
        )
        assert conflict_route["review_status"] == "blocked"

        blocked_batch = await client.post(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/prospect-batches",
            json={"company_ids": [conflict_route["company_id"]]},
        )
        assert blocked_batch.status_code == 409

        blocked_confirm = await client.post(
            f"/api/v1/prospect-routes/{conflict_route['route_id']}/review",
            json={
                "action": "confirm",
                "reviewed_by": "qa",
            },
        )
        assert blocked_confirm.status_code == 409


async def test_preview_without_hs_or_pol_pod_still_succeeds(
    uow_factory: UowFactory,
) -> None:
    """Missing HS Code / POL / POD must never block the priority preview."""
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        session_id = await upload_fixture(client)
        resolution = await client.post(
            f"/api/v1/import-sessions/{session_id}/resolve"
        )
        assert resolution.status_code == 202
        assert await runner.run_once(owner="parity-minimal-criteria-worker") is True

        response = await client.post(
            f"/api/v1/import-sessions/{session_id}/routing-preview",
            json={
                "criteria": {
                    "target_product_keywords": ["fitness"],
                    "target_hs_codes": [],
                    "preferred_origin_countries": [],
                    "preferred_pol": [],
                    "preferred_pod": [],
                },
                "campaign_name": "minimal criteria",
            },
        )
        assert response.status_code == 200, response.text
        body = cast(dict[str, object], response.json())
        totals = cast(dict[str, int], body["totals"])
        assert sum(totals.values()) == 4
        assert body["rules_version"] == "real-routing-v1.1"


async def test_keep_separate_adds_one_canonical_company_and_routing_counts_match(
    uow_factory: UowFactory,
) -> None:
    """KEEP_SEPARATE creates one new canonical company; routing must count it
    exactly once and never double-score anchors that map to the same company."""
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        session_id = await upload_fixture(client)
        resolution = await client.post(
            f"/api/v1/import-sessions/{session_id}/resolve"
        )
        assert resolution.status_code == 202
        assert await runner.run_once(owner="parity-keep-separate-worker") is True

        before = await client.get(
            f"/api/v1/import-sessions/{session_id}/resolution"
        )
        before_body = before.json()
        assert before_body["canonical_company_count"] == 4

        decisions_response = await client.get(
            f"/api/v1/import-sessions/{session_id}/entity-decisions",
            params={"entity_type": "company", "review_status": "pending", "limit": 20},
        )
        pending = decisions_response.json()["decisions"]
        assert len(pending) == 1
        kept = await client.post(
            f"/api/v1/import-entity-decisions/{pending[0]['decision_id']}/review",
            json={"action": "keep_separate", "reviewed_by": "qa"},
        )
        assert kept.status_code == 200

        after = await client.get(
            f"/api/v1/import-sessions/{session_id}/resolution"
        )
        after_body = after.json()
        assert after_body["canonical_company_count"] == 5

        preview_body = await preview(client, session_id)
        assert preview_body["entity_pending_count"] == 0
        totals = cast(dict[str, int], preview_body["totals"])
        assert len(
            cast(list[dict[str, object]], preview_body["companies"])
        ) == 5
        assert sum(totals.values()) == 5
        # The two original anchors (Atlas + Atlas LLC) now resolve to two
        # distinct canonical companies; both appear exactly once.
        names = {
            str(company["company_name"])
            for company in cast(
                list[dict[str, object]], preview_body["companies"]
            )
        }
        assert "Atlas Fitness" in names
        assert "Atlas Fitness LLC" in names
