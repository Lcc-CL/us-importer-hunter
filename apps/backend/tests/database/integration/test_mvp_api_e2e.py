"""Real PostgreSQL: analyze → query → approve, with no network providers."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.main import create_app
from tests.database.integration.conftest import UowFactory


def payload() -> dict[str, object]:
    return {
        "company": {
            "name": "MVP API Integration Importer",
            "website": "https://mvp-api-integration.example",
            "sources": [
                {
                    "source": "importyeti",
                    "reference": "https://www.importyeti.com/company/mvp-api-integration-importer",
                },
                {
                    "source": "company_website",
                    "reference": "https://mvp-api-integration.example/about",
                },
            ],
            "signals": [
                {"kind": "import_activity", "detail": "customs shipments recorded"},
                {"kind": "china_dependency", "detail": "China origin observed"},
                {"kind": "shipping_fit", "detail": "ocean FCL container freight"},
                {"kind": "cargo_value", "detail": "high value cargo"},
                {"kind": "company_scale", "detail": "warehouse and employees"},
                {"kind": "growth", "detail": "growing import activity"},
                {"kind": "complexity", "detail": "multi-origin logistics"},
            ],
        },
        "contact": {
            "name": "Maria Chen",
            "title": "Director of Supply Chain",
            "email": "maria@mvp-api-integration.example",
            "source": "integration_fixture",
        },
        "sender": {
            "name": "Alex Morgan",
            "company": "Harbor Bridge Logistics",
            "value_proposition": "We simplify Asia-to-US inbound freight.",
        },
        "options": {"generate_email": True},
    }


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        app_env="development",
        email_generator_provider="fake",
    )
    app = create_app(settings)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_analyze_query_approve_and_replay_are_persisted(
    uow_factory: UowFactory,
) -> None:
    async for client in make_client(uow_factory):
        response = await client.post("/api/v1/mvp/prospects/analyze", json=payload())
        assert response.status_code == 200, response.text
        analyzed = response.json()
        assert analyzed["overall_status"] == "COMPLETED", analyzed
        assert analyzed["company"]["action"] == "CREATED"
        assert analyzed["opportunity"]["qualification_decision"] == "qualified"
        assert analyzed["contact"]["action"] == "CREATED"
        assert analyzed["decision_maker"]["action"] == "SELECTED"
        assert analyzed["email_draft"]["action"] == "GENERATED"
        company_id = analyzed["company"]["company_id"]
        outreach_id = analyzed["email_draft"]["outreach_id"]

        detail = await client.get(f"/api/v1/mvp/prospects/{company_id}")
        assert detail.status_code == 200, detail.text
        saved = detail.json()
        assert saved["company"]["sources"] == ["importyeti", "company_website"]
        assert saved["latest_assessment"]["score"] >= 70.0
        assert saved["contacts"][0]["status"] == "active"
        assert saved["decision_maker"]["selected_contact_id"] == analyzed["contact"]["contact_id"]
        assert saved["decision_maker"]["rankings"]
        assert saved["latest_email_draft"]["status"] == "generated"
        assert saved["latest_email_draft"]["approval_status"] == "generated"
        assert saved["latest_email_draft"]["approved_at"] is None
        assert saved["latest_email_draft"]["approved_by_name"] is None
        assert len(saved["draft_history"]) == 1

        approved = await client.post(
            f"/api/v1/mvp/outreaches/{outreach_id}/drafts/1/approve",
            json={"approver_name": "Alex Morgan"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["approval_status"] == "approved"
        assert approved.json()["approved_by"] == "Alex Morgan"
        assert approved.json()["approved_by_name"] == "Alex Morgan"
        assert approved.json()["approved_at"]

        refreshed = await client.get(f"/api/v1/mvp/prospects/{company_id}")
        refreshed_draft = refreshed.json()["latest_email_draft"]
        assert refreshed_draft["approval_status"] == "approved"
        assert refreshed_draft["approved_at"] == approved.json()["approved_at"]
        assert refreshed_draft["approved_by_name"] == "Alex Morgan"

        replay = await client.post("/api/v1/mvp/prospects/analyze", json=payload())
        assert replay.status_code == 200, replay.text
        replayed = replay.json()
        assert replayed["company"]["action"] == "MERGED"
        assert replayed["email_draft"]["action"] == "SKIPPED"

        final_detail = await client.get(f"/api/v1/mvp/prospects/{company_id}")
        final_saved = final_detail.json()
        assert final_saved["latest_email_draft"]["status"] == "approved"
        assert final_saved["latest_email_draft"]["approved_by_name"] == "Alex Morgan"
        assert len(final_saved["draft_history"]) == 1
