"""D1 API persistence against PostgreSQL with deterministic provider claims."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

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
        assert "REAL_PROVIDER_BLOCKED_BY_API_CAPABILITY" in created["error_summary"]

        saved = await client.get(
            f"/api/v1/discovery-tasks/{created['task_id']}"
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "failed"
        assert saved.json()["completed_at"] is not None
