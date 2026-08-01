"""D1 API persistence against PostgreSQL with deterministic provider claims."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_company_discovery_provider,
    get_uow_factory,
)
from app.core.config import Settings
from app.domain.discovery import (
    CompanyCandidate,
    CompanyDiscoveryQuery,
    CompanyDiscoverySearchResult,
    DiscoveryProviderFailure,
    DiscoveryResult,
    RawCompanySnapshot,
)
from app.domain.events import CompanyDiscovered
from app.domain.values import SourceReference
from app.main import create_app
from app.services.discovery.manual_csv import MAX_MANUAL_CSV_BYTES, MAX_MANUAL_CSV_ROWS
from app.workflows.company_ingestion import CompanyIngestionWorkflow
from tests.database.integration.conftest import UowFactory


class StaticDiscoveryProvider:
    provider_name = "integration_provider"

    def __init__(
        self,
        candidates: tuple[CompanyCandidate, ...],
        failures: tuple[DiscoveryProviderFailure, ...] = (),
    ) -> None:
        self._result = CompanyDiscoverySearchResult(
            candidates=candidates,
            failures=failures,
        )

    async def search(self, query: CompanyDiscoveryQuery) -> CompanyDiscoverySearchResult:
        assert query.effective_count == 20
        return self._result


async def make_client(
    uow_factory: UowFactory,
    provider: StaticDiscoveryProvider,
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_company_discovery_provider] = lambda: provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def make_default_provider_client(
    uow_factory: UowFactory,
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def provider_candidate(
    name: str,
    *,
    source_id: str,
    website: str,
) -> CompanyCandidate:
    return CompanyCandidate(
        source="integration_provider",
        company_name=name,
        source_url=f"https://evidence.example/{source_id}",
        website=website,
        region="United States",
        product_description="Hardware importer",
        import_evidence=f"BOL-{source_id}",
    )


async def test_create_query_partial_failure_and_refresh_persistence(
    uow_factory: UowFactory,
) -> None:
    broken_name = "Broken Candidate " + ("x" * 190)
    provider = StaticDiscoveryProvider(
        candidates=(
            provider_candidate(
                "Atlas Hardware",
                source_id="atlas-1",
                website="https://www.atlas-hardware.example",
            ),
            provider_candidate(
                "Atlas Imports Alias",
                source_id="atlas-2",
                website="atlas-hardware.example/about",
            ),
            provider_candidate(
                broken_name,
                source_id="broken",
                website="broken-candidate.example",
            ),
        ),
        failures=(DiscoveryProviderFailure(reason="one provider row was unusable"),),
    )

    task_id: str | None = None
    async for client in make_client(uow_factory, provider):
        response = await client.post(
            "/api/v1/discovery-tasks",
            json={"prompt": "帮我找 20 家北美五金进口商"},
        )
        assert response.status_code == 201, response.text
        task = response.json()
        task_id = task["task_id"]
        assert task["status"] == "partial_failed"
        assert task["requested_count"] == 20
        assert task["parsed_region"] == "North America"
        assert task["parsed_category"] == "hardware"
        assert task["discovered_count"] == 3
        assert task["ingested_count"] == 1
        assert task["duplicate_count"] == 1
        assert task["failed_count"] == 2
        assert "unusable company name" in task["error_summary"]

        companies = await client.get(
            f"/api/v1/discovery-tasks/{task_id}/companies"
        )
        assert companies.status_code == 200, companies.text
        visible = companies.json()["companies"]
        visible_by_name = {item["company_name"]: item for item in visible}
        assert set(visible_by_name) == {"Atlas Hardware", broken_name}
        assert visible_by_name["Atlas Hardware"]["status"] == "ingested"
        assert visible_by_name[broken_name]["status"] == "failed"
        assert all(item["source"] == "integration_provider" for item in visible)

    assert task_id is not None
    async for refreshed_client in make_client(uow_factory, provider):
        refreshed = await refreshed_client.get(f"/api/v1/discovery-tasks/{task_id}")
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["status"] == "partial_failed"
        assert refreshed.json()["discovered_count"] == 3


async def test_existing_company_is_reused_by_domain_before_name(
    uow_factory: UowFactory,
) -> None:
    ingestion = CompanyIngestionWorkflow(uow_factory)
    existing = await ingestion.handle(
        CompanyDiscovered(
            run_id=uuid4(),
            result=DiscoveryResult(
                snapshot=RawCompanySnapshot(
                    name_text="Existing Canonical Importer",
                    website_text="shared-domain.example",
                    source=SourceReference(
                        source="company_website",
                        reference="https://shared-domain.example/about",
                        retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                    ),
                )
            ),
        )
    )
    assert existing.company_id is not None

    provider = StaticDiscoveryProvider(
        candidates=(
            provider_candidate(
                "Completely Different Importer Name",
                source_id="same-domain",
                website="https://www.shared-domain.example/products",
            ),
        )
    )
    async for client in make_client(uow_factory, provider):
        response = await client.post(
            "/api/v1/discovery-tasks",
            json={"prompt": "帮我找 20 家北美五金进口商"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "completed"
        assert body["ingested_count"] == 0
        assert body["duplicate_count"] == 1

        candidates = await client.get(
            f"/api/v1/discovery-tasks/{body['task_id']}/companies"
        )
        linked = candidates.json()["companies"][0]
        assert linked["status"] == "duplicate"
        assert UUID(linked["company_id"]) == existing.company_id


async def test_default_importyeti_blocker_is_persisted_as_terminal_failure(
    uow_factory: UowFactory,
) -> None:
    async for client in make_default_provider_client(uow_factory):
        response = await client.post(
            "/api/v1/discovery-tasks",
            json={"prompt": "帮我找 20 家北美五金进口商"},
        )
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["provider"] == "importyeti"
        assert created["status"] == "failed"
        assert created["failed_count"] == 1
        assert created["error_code"] == "REAL_PROVIDER_BLOCKED_BY_API_CAPABILITY"
        assert "website scraping is disabled" in created["error_summary"]

        saved = await client.get(
            f"/api/v1/discovery-tasks/{created['task_id']}"
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "failed"
        assert saved.json()["error_code"] == "REAL_PROVIDER_BLOCKED_BY_API_CAPABILITY"
        assert saved.json()["completed_at"] is not None


async def test_manual_csv_complex_partial_failure_dedup_and_repeat_upload(
    uow_factory: UowFactory,
) -> None:
    content = (
        b"company_name,source_url,external_id,website,address,region,"
        b"product_description,import_evidence\n"
        b"Atlas Hardware,https://evidence.example/atlas-1,,https://atlas.example,"
        b"1 Harbor Way,US,Hand tools,BOL-ATLAS-1\n"
        b"Atlas Hardware Alias,https://evidence.example/atlas-2,,atlas.example/about,"
        b"1 Harbor Way,US,Hand tools,BOL-ATLAS-2\n"
        b"Harbor Supply,https://evidence.example/harbor-1,,,100 Main St,US,,\n"
        b"Harbor Supply,https://evidence.example/harbor-2,,,100 Main St,US,,\n"
        b"Optional Fields,https://evidence.example/optional,,,,,,\n"
        b"Invalid Row,,,,,,,\n"
        b"Bad Website,https://evidence.example/bad-url,,not a valid url,"
        b"9 Test Ave,US,Lighting importer,BOL-BAD-URL\n"
    )

    first_visible: dict[str, dict[str, object]] = {}
    async for client in make_default_provider_client(uow_factory):
        first = await client.post(
            "/api/v1/discovery-tasks/manual-csv",
            data={"prompt": "帮我找 20 家北美五金进口商"},
            files={"file": ("d1-synthetic.csv", content, "text/csv")},
        )
        assert first.status_code == 201, first.text
        first_task = first.json()
        assert first_task["provider"] == "manual_csv"
        assert first_task["status"] == "partial_failed"
        assert first_task["discovered_count"] == 6
        assert first_task["ingested_count"] == 4
        assert first_task["duplicate_count"] == 2
        assert first_task["failed_count"] == 1
        assert first_task["error_code"] == "DISCOVERY_RESULT_ERRORS"
        assert "row 7 requires company_name and source_url/external_id" in first_task[
            "error_summary"
        ]

        first_companies = await client.get(
            f"/api/v1/discovery-tasks/{first_task['task_id']}/companies"
        )
        assert first_companies.status_code == 200, first_companies.text
        first_rows = first_companies.json()["companies"]
        assert [item["position"] for item in first_rows] == [0, 2, 4, 5]
        assert [item["company_name"] for item in first_rows] == [
            "Atlas Hardware",
            "Harbor Supply",
            "Optional Fields",
            "Bad Website",
        ]
        assert all(item["source"] == "manual_csv" for item in first_rows)
        assert all(item["company_id"] is not None for item in first_rows)
        first_visible = {item["company_name"]: item for item in first_rows}

        repeated_get = await client.get(
            f"/api/v1/discovery-tasks/{first_task['task_id']}/companies"
        )
        assert repeated_get.json()["companies"] == first_rows

        second = await client.post(
            "/api/v1/discovery-tasks/manual-csv",
            data={"prompt": "帮我找 20 家北美五金进口商"},
            files={"file": ("d1-synthetic.csv", content, "text/csv")},
        )
        assert second.status_code == 201, second.text
        second_task = second.json()
        assert second_task["task_id"] != first_task["task_id"]
        assert second_task["ingested_count"] == 0
        assert second_task["duplicate_count"] == 6
        assert second_task["failed_count"] == 1

        second_companies = await client.get(
            f"/api/v1/discovery-tasks/{second_task['task_id']}/companies"
        )
        second_rows = second_companies.json()["companies"]
        assert [item["position"] for item in second_rows] == [0, 2, 4, 5]
        assert {
            item["company_name"]: item["company_id"] for item in second_rows
        } == {
            name: item["company_id"] for name, item in first_visible.items()
        }


@pytest.mark.parametrize(
    ("content", "error_code"),
    [
        (b"", "discovery_csv_empty"),
        (b"\xff\xfeinvalid", "discovery_csv_invalid_encoding"),
        (b"name,source_url\nAtlas,record-1\n", "discovery_csv_invalid_header"),
        (
            b"company_name,source_url\n" + (b"x" * MAX_MANUAL_CSV_BYTES),
            "discovery_csv_too_large",
        ),
        (
            (
                "company_name,source_url\n"
                + "\n".join(
                    f"Company {index},record-{index}"
                    for index in range(MAX_MANUAL_CSV_ROWS + 1)
                )
            ).encode(),
            "discovery_csv_too_many_rows",
        ),
    ],
)
async def test_manual_csv_file_errors_are_structured_4xx(
    uow_factory: UowFactory,
    content: bytes,
    error_code: str,
) -> None:
    async for client in make_default_provider_client(uow_factory):
        response = await client.post(
            "/api/v1/discovery-tasks/manual-csv",
            data={"prompt": "帮我找 20 家北美五金进口商"},
            files={"file": ("invalid.csv", content, "text/csv")},
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == error_code
        assert response.json()["message"]
        UUID(response.json()["request_id"])


async def test_missing_discovery_task_is_structured_404(
    uow_factory: UowFactory,
) -> None:
    missing_id = uuid4()
    async for client in make_default_provider_client(uow_factory):
        for path in (
            f"/api/v1/discovery-tasks/{missing_id}",
            f"/api/v1/discovery-tasks/{missing_id}/companies",
        ):
            response = await client.get(path)
            assert response.status_code == 404
            assert response.json()["code"] == "resource_not_found"
            UUID(response.json()["request_id"])


async def test_manual_csv_blank_prompt_is_structured_4xx(
    uow_factory: UowFactory,
) -> None:
    async for client in make_default_provider_client(uow_factory):
        response = await client.post(
            "/api/v1/discovery-tasks/manual-csv",
            data={"prompt": "   "},
            files={
                "file": (
                    "valid.csv",
                    b"company_name,source_url\nAtlas,https://evidence.example/atlas\n",
                    "text/csv",
                )
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "discovery_prompt_invalid"


async def test_discovery_openapi_exposes_structured_error_and_order_fields(
    uow_factory: UowFactory,
) -> None:
    async for client in make_default_provider_client(uow_factory):
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schemas = response.json()["components"]["schemas"]
        assert "error_code" in schemas["DiscoveryTaskResponse"]["properties"]
        assert "position" in schemas["DiscoveryCompanyResponse"]["properties"]
        manual_responses = response.json()["paths"][
            "/api/v1/discovery-tasks/manual-csv"
        ]["post"]["responses"]
        assert "422" in manual_responses
