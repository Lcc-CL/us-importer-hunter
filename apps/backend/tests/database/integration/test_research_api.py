"""Real PostgreSQL: the internal research API end to end.

The fetcher is stubbed so no network is touched; everything else — routing,
persistence, serialization — is the real thing.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.deps import get_research_workflow, get_uow_factory
from app.core.config import Settings
from app.domain.company import Company
from app.domain.values import CompanyName, WebsiteUrl
from app.main import create_app
from app.services.research import ClaimValidator, FakeResearchExtractor
from app.tools.website import FetchedPage, FetchFailure, FetchOutcome
from app.workflows.research import ResearchLimits, ResearchWorkflow
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_research_db import session_of

WEBSITE = "https://acme.example"

HOME_HTML = """
<html><head><title>Acme Hardware</title></head><body>
  <a href="/about">About us</a>
  <main>
    <p>Acme Hardware imports fasteners and tools from China every month.</p>
    <p>We operate a 120,000 sq ft warehouse in Long Beach, California.</p>
    <p>Our FCL ocean freight arrives weekly from Shenzhen and Ningbo.</p>
  </main>
</body></html>
"""
ABOUT_HTML = "<html><body><main><p>Founded in 1961 and growing every year.</p></main></body></html>"
JS_SHELL = '<html><body><div id="root"></div><script src="/a.js"></script></body></html>'

ROBOTS_DENY_ALL = "User-agent: *\nDisallow: /\n"


def page(url: str, html: str, content_type: str = "text/html") -> FetchedPage:
    return FetchedPage(
        requested_url=url,
        final_url=url,
        status_code=200,
        content_type=content_type,
        html=html,
        bytes_read=len(html),
        truncated=False,
        redirect_hops=0,
        elapsed_ms=5,
    )


class StubFetcher:
    def __init__(self, responses: dict[str, FetchOutcome]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    async def fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        accept: tuple[str, ...] = ("text/html",),
    ) -> FetchOutcome:
        self.requested.append(url)
        if url in self.responses:
            return self.responses[url]
        return FetchFailure(requested_url=url, code="http_error", detail="HTTP 404")


class StubClient:
    async def __aenter__(self) -> "StubClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


async def make_client(
    uow_factory: UowFactory, responses: dict[str, FetchOutcome] | None = None
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    fetcher = StubFetcher(responses or {WEBSITE: page(WEBSITE, HOME_HTML)})

    def workflow_override() -> ResearchWorkflow:
        return ResearchWorkflow(
            uow_factory=uow_factory,
            extractor=FakeResearchExtractor(),
            fetcher_factory=lambda scope: fetcher,
            client_factory=StubClient,  # type: ignore[arg-type]
            validator=ClaimValidator(),
            limits=ResearchLimits(request_delay_seconds=0.0),
        )

    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_research_workflow] = workflow_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def seed_company(uow_factory: UowFactory) -> Company:
    company = Company.create(CompanyName("Acme Hardware"), WebsiteUrl(WEBSITE))
    async with uow_factory() as uow:
        await uow.companies.add(company)
        await uow.commit()
    return company


class TestCreateRun:
    async def test_research_bound_to_an_existing_company(self, uow_factory: UowFactory) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            response = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["company_id"] == str(company.id)
        assert body["company_name"] == "Acme Hardware"
        assert body["website"] == WEBSITE
        assert body["status"] in {"completed", "partial"}
        assert body["claims"]
        assert body["extractor"]["provider"] == "fake"
        assert body["extractor"]["prompt_version"]

    async def test_prospect_without_a_company(self, uow_factory: UowFactory) -> None:
        async for client in make_client(uow_factory):
            response = await client.post(
                "/api/v1/research/runs",
                json={"company_name": "Unknown Prospect", "website": WEBSITE},
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["company_id"] is None
        assert body["company_name"] == "Unknown Prospect"

    async def test_no_company_row_is_created_for_a_prospect(
        self, uow_factory: UowFactory
    ) -> None:
        async for client in make_client(uow_factory):
            await client.post(
                "/api/v1/research/runs",
                json={"company_name": "Unknown Prospect", "website": WEBSITE},
            )
        async with uow_factory() as uow:
            count = await session_of(uow).execute(
                text("SELECT count(*) FROM companies WHERE name = 'Unknown Prospect'")
            )
            assert count.scalar_one() == 0

    async def test_unknown_company_id_is_404(self, uow_factory: UowFactory) -> None:
        async for client in make_client(uow_factory):
            response = await client.post(
                "/api/v1/research/runs", json={"company_id": str(uuid4())}
            )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "payload",
        [
            {},                                    # neither identity
            {"company_name": "No Website"},        # name without website
            {"website": WEBSITE},                  # website without name
            {"company_id": "not-a-uuid"},          # malformed uuid
            {"company_name": "  ", "website": WEBSITE},  # blank name
        ],
    )
    async def test_invalid_schema_is_422(
        self, uow_factory: UowFactory, payload: dict[str, str]
    ) -> None:
        async for client in make_client(uow_factory):
            response = await client.post("/api/v1/research/runs", json=payload)
        assert response.status_code == 422, response.text


class TestOutcomesAreResultsNotErrors:
    async def test_partial_run_returns_201(self, uow_factory: UowFactory) -> None:
        """Sub-page failures are a result, not a server error."""
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory, {WEBSITE: page(WEBSITE, HOME_HTML)}):
            response = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "partial"
        assert body["pages_failed"] >= 1

    async def test_needs_browser_returns_201_with_failure_code(
        self, uow_factory: UowFactory
    ) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory, {WEBSITE: page(WEBSITE, JS_SHELL)}):
            response = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
        assert response.status_code == 201
        assert response.json()["failure_code"] == "needs_browser"

    async def test_robots_denied_returns_201_with_failure_code(
        self, uow_factory: UowFactory
    ) -> None:
        company = await seed_company(uow_factory)
        responses: dict[str, FetchOutcome] = {
            f"{WEBSITE}/robots.txt": page(
                f"{WEBSITE}/robots.txt", ROBOTS_DENY_ALL, content_type="text/plain"
            ),
            WEBSITE: page(WEBSITE, HOME_HTML),
        }
        async for client in make_client(uow_factory, responses):
            response = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "failed"
        assert body["failure_code"] == "robots_denied"
        assert body["pages_fetched"] == 0


class TestReadRun:
    async def test_get_returns_the_saved_run(self, uow_factory: UowFactory) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            created = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
            run_id = created.json()["research_id"]
            response = await client.get(f"/api/v1/research/runs/{run_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["research_id"] == run_id
        assert body["claims"] == created.json()["claims"]

    async def test_unknown_run_is_404(self, uow_factory: UowFactory) -> None:
        async for client in make_client(uow_factory):
            response = await client.get(f"/api/v1/research/runs/{uuid4()}")
        assert response.status_code == 404

    async def test_rejected_claims_survive_a_reload(self, uow_factory: UowFactory) -> None:
        """Rejection detail is persisted, so GET can explain itself instead of
        degrading to bare warnings."""
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory, {WEBSITE: page(WEBSITE, HOME_HTML)}):
            created = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
            run_id = created.json()["research_id"]
            reloaded = await client.get(f"/api/v1/research/runs/{run_id}")
        assert reloaded.json()["rejected_claims"] == created.json()["rejected_claims"]


class TestCompanyHistory:
    async def test_lists_runs_most_recent_first(self, uow_factory: UowFactory) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            await client.post("/api/v1/research/runs", json={"company_id": str(company.id)})
            await client.post("/api/v1/research/runs", json={"company_id": str(company.id)})
            response = await client.get(f"/api/v1/companies/{company.id}/research-runs")

        assert response.status_code == 200
        body = response.json()
        assert body["company_id"] == str(company.id)
        assert len(body["runs"]) == 2  # many runs per company are allowed

    async def test_unknown_company_is_404(self, uow_factory: UowFactory) -> None:
        async for client in make_client(uow_factory):
            response = await client.get(f"/api/v1/companies/{uuid4()}/research-runs")
        assert response.status_code == 404

    async def test_prospect_runs_are_not_listed_under_any_company(
        self, uow_factory: UowFactory
    ) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            await client.post(
                "/api/v1/research/runs",
                json={"company_name": "Unknown Prospect", "website": WEBSITE},
            )
            response = await client.get(f"/api/v1/companies/{company.id}/research-runs")
        assert response.json()["runs"] == []


class TestCompanyDeletion:
    async def test_run_survives_company_deletion_with_company_id_nulled(
        self, uow_factory: UowFactory
    ) -> None:
        """ON DELETE SET NULL: the audit record outlives the company."""
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            created = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
            run_id = created.json()["research_id"]

            async with uow_factory() as uow:
                await session_of(uow).execute(
                    text("DELETE FROM companies WHERE id = :cid"), {"cid": company.id}
                )
                await uow.commit()

            response = await client.get(f"/api/v1/research/runs/{run_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["company_id"] is None
        assert body["company_name"] == "Acme Hardware"  # snapshot preserved
        assert body["website"] == WEBSITE
        assert body["claims"]


class TestNoSensitiveConfigLeaks:
    async def test_response_carries_no_credentials_or_endpoints(
        self, uow_factory: UowFactory
    ) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            response = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
        raw = response.text.lower()
        for forbidden in ["api_key", "apikey", "base_url", "openai_", "system_prompt", "sk-"]:
            assert forbidden not in raw

    async def test_response_carries_no_raw_html_or_full_page_text(
        self, uow_factory: UowFactory
    ) -> None:
        """Pages are metadata only; evidence is short snippets."""
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            response = await client.post(
                "/api/v1/research/runs", json={"company_id": str(company.id)}
            )
        raw = response.text
        assert "<html" not in raw.lower()
        assert "<main>" not in raw.lower()
        assert "<script" not in raw.lower()
        for page_entry in response.json()["pages"]:
            assert "html" not in page_entry
            assert "text" not in page_entry
            assert set(page_entry) == {
                "position",
                "url",
                "final_url",
                "http_status",
                "content_type",
                "fetched_at",
                "content_chars",
                "truncated",
                "discovery_reason",
            }


# --- claim confirmation (phase 3.3) ---------------------------------------


async def create_run_with_claims(
    client: AsyncClient, company_id: str | None
) -> dict[str, object]:
    payload = (
        {"company_id": company_id}
        if company_id
        else {"company_name": "Acme Hardware", "website": WEBSITE}
    )
    response = await client.post("/api/v1/research/runs", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


class TestConfirmApi:
    async def test_confirm_applies_to_the_bound_company(
        self, uow_factory: UowFactory
    ) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [{"claim_position": 0, "decision": "accepted"}],
                },
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["action"] == "applied"
        assert body["company_id"] == str(company.id)
        assert body["summary"] == {"accepted": 1, "edited": 0, "rejected": 0, "total": 1}
        assert body["promotions"][0]["company_signal_position"] == 0
        assert body["promotions"][0]["company_source_position"] == 0
        assert body["application_payload"] is None

    async def test_confirm_without_a_company_returns_a_form_payload(
        self, uow_factory: UowFactory
    ) -> None:
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, None)
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [{"claim_position": 0, "decision": "accepted"}],
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "recorded"
        assert body["company_id"] is None
        payload = body["application_payload"]
        assert payload["company_name"] == "Acme Hardware"
        assert payload["signals"]
        assert payload["sources"]

    async def test_edited_and_rejected_round_trip(self, uow_factory: UowFactory) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [
                        {
                            "claim_position": 0,
                            "decision": "edited",
                            "edited_detail": "reworded",
                            "edited_kind": "shipping_fit",
                        },
                        {"claim_position": 1, "decision": "rejected"},
                    ],
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["edited"] == 1
        assert body["summary"]["rejected"] == 1
        edited = next(p for p in body["promotions"] if p["decision"] == "edited")
        rejected = next(p for p in body["promotions"] if p["decision"] == "rejected")
        assert edited["kind"] == "shipping_fit"
        assert rejected["company_signal_position"] is None

    async def test_unknown_run_is_404(self, uow_factory: UowFactory) -> None:
        async for client in make_client(uow_factory):
            response = await client.post(
                f"/api/v1/research/runs/{uuid4()}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [{"claim_position": 0, "decision": "accepted"}],
                },
            )
        assert response.status_code == 404

    async def test_unknown_target_company_is_404(self, uow_factory: UowFactory) -> None:
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, None)
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "target_company_id": str(uuid4()),
                    "decisions": [{"claim_position": 0, "decision": "accepted"}],
                },
            )
        assert response.status_code == 404

    async def test_company_mismatch_is_409(self, uow_factory: UowFactory) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "target_company_id": str(uuid4()),
                    "decisions": [{"claim_position": 0, "decision": "accepted"}],
                },
            )
        assert response.status_code == 409

    async def test_contradicting_an_applied_decision_is_409(
        self, uow_factory: UowFactory
    ) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            url = f"/api/v1/research/runs/{run['research_id']}/confirm"
            await client.post(
                url,
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [{"claim_position": 0, "decision": "accepted"}],
                },
            )
            response = await client.post(
                url,
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [{"claim_position": 0, "decision": "rejected"}],
                },
            )
        assert response.status_code == 409

    async def test_identical_replay_is_unchanged(self, uow_factory: UowFactory) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            url = f"/api/v1/research/runs/{run['research_id']}/confirm"
            body = {
                "reviewer_name": "Lcc",
                "decisions": [{"claim_position": 0, "decision": "accepted"}],
            }
            await client.post(url, json=body)
            response = await client.post(url, json=body)
        assert response.status_code == 200
        assert response.json()["action"] == "unchanged"

    async def test_unknown_claim_position_is_422(self, uow_factory: UowFactory) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [{"claim_position": 99, "decision": "accepted"}],
                },
            )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "payload",
        [
            {"reviewer_name": "Lcc", "decisions": []},                      # empty batch
            {"decisions": [{"claim_position": 0, "decision": "accepted"}]},  # no reviewer
            {"reviewer_name": "Lcc", "decisions": [{"claim_position": 0}]},  # no decision
            {
                "reviewer_name": "Lcc",
                "decisions": [{"claim_position": 0, "decision": "edited"}],  # no detail
            },
            {
                "reviewer_name": "Lcc",
                "decisions": [
                    {"claim_position": 0, "decision": "accepted", "edited_detail": "x"}
                ],  # edits on a non-edited decision
            },
            {
                "reviewer_name": "Lcc",
                "decisions": [
                    {"claim_position": 0, "decision": "accepted"},
                    {"claim_position": 0, "decision": "rejected"},  # duplicate claim
                ],
            },
        ],
    )
    async def test_invalid_schema_is_422(
        self, uow_factory: UowFactory, payload: dict[str, object]
    ) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm", json=payload
            )
        assert response.status_code == 422, response.text

    async def test_confirm_response_leaks_no_sensitive_config(
        self, uow_factory: UowFactory
    ) -> None:
        company = await seed_company(uow_factory)
        async for client in make_client(uow_factory):
            run = await create_run_with_claims(client, str(company.id))
            response = await client.post(
                f"/api/v1/research/runs/{run['research_id']}/confirm",
                json={
                    "reviewer_name": "Lcc",
                    "decisions": [{"claim_position": 0, "decision": "accepted"}],
                },
            )
        raw = response.text.lower()
        for forbidden in ["api_key", "apikey", "base_url", "openai_", "system_prompt", "sk-"]:
            assert forbidden not in raw
        assert "<html" not in raw
        assert "<script" not in raw
