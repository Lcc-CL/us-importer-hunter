"""Real PostgreSQL coverage for the single-company CSV evidence flow."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_import_evidence_projection_reader, get_uow_factory
from app.core.config import Settings
from app.database.repositories import SqlAlchemyImportEvidenceProjectionReader
from app.main import create_app
from tests.database.integration.conftest import UowFactory

DEMO_CSV = (
    Path(__file__).resolve().parents[5]
    / "fixtures"
    / "import-evidence"
    / "demo-hardware-imports.csv"
).read_bytes()


def analysis_payload(name: str = "Pacific Home Goods Inc.") -> dict[str, object]:
    return {
        "company": {
            "name": name,
            "website": "https://pacifichomegoods.example",
            "sources": [
                {"source": "company_website", "reference": "https://pacifichomegoods.example"},
                {"source": "annual_report", "reference": "https://pacifichomegoods.example/report"},
            ],
            "signals": [
                {"kind": "shipping_fit", "detail": "ocean FCL container freight"},
                {"kind": "cargo_value", "detail": "high value cargo"},
                {"kind": "company_scale", "detail": "warehouse and employees"},
                {"kind": "growth", "detail": "growing import operations"},
            ],
        },
        "contact": {
            "name": "Maria Chen",
            "title": "Director of Supply Chain",
            "email": "maria@pacifichomegoods.example",
            "source": "company_website",
        },
        "sender": {
            "name": "Alex Morgan",
            "company": "Harbor Bridge Logistics",
            "value_proposition": "We simplify Asia-to-US inbound freight.",
        },
        "options": {"generate_email": True},
    }


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(_env_file=None, app_env="development", email_generator_provider="fake")
    )
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    session_factory = uow_factory()._session_factory  # noqa: SLF001 - test adapter wiring
    app.dependency_overrides[get_import_evidence_projection_reader] = lambda: (
        SqlAlchemyImportEvidenceProjectionReader(session_factory)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_upload_promotes_requalifies_drafts_reloads_and_replays(
    uow_factory: UowFactory,
) -> None:
    async for client in make_client(uow_factory):
        initial = await client.post("/api/v1/mvp/prospects/analyze", json=analysis_payload())
        assert initial.status_code == 200, initial.text
        initial_body = initial.json()
        assert initial_body["opportunity"]["qualification_decision"] != "qualified"
        assert initial_body["email_draft"]["action"] == "SKIPPED"
        company_id = initial_body["company"]["company_id"]

        files = {"file": ("demo.csv", DEMO_CSV, "text/csv")}
        form = {
            "sender_name": "Alex Morgan",
            "sender_company": "Harbor Bridge Logistics",
            "sender_value_proposition": "We simplify Asia-to-US inbound freight.",
        }
        uploaded = await client.post(
            f"/api/v1/companies/{company_id}/import-evidence/upload",
            files=files,
            data=form,
        )
        assert uploaded.status_code == 200, uploaded.text
        result = uploaded.json()
        assert result["records_received"] == 3
        assert result["shipments_matched"] == 3
        assert {"import_activity", "china_dependency"} <= set(result["promoted_signals"])
        assert result["qualification_status"] == "qualified", (
            result["qualification_score"],
            result["qualification_reasons"],
            result["promoted_signals"],
        )
        assert result["qualification_score"] > result["previous_qualification_score"]
        assert result["draft_status"] != "skipped"

        current = await client.get(f"/api/v1/companies/{company_id}/import-evidence")
        assert current.status_code == 200
        assert current.json()["aggregate_id"] == result["aggregate_id"]

        replay = await client.post(
            f"/api/v1/companies/{company_id}/import-evidence/upload",
            files=files,
            data=form,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["aggregate_id"] == result["aggregate_id"]

        detail = (await client.get(f"/api/v1/mvp/prospects/{company_id}")).json()
        assert len(detail["draft_history"]) == 1
        for kind in ("shipping_fit", "cargo_value", "company_scale", "growth"):
            assert any(signal.startswith(f"{kind}:") for signal in detail["company"]["signals"])


async def test_unmatched_csv_returns_review_without_draft(
    uow_factory: UowFactory,
) -> None:
    async for client in make_client(uow_factory):
        initial = await client.post(
            "/api/v1/mvp/prospects/analyze", json=analysis_payload("Different Importer LLC")
        )
        company_id = initial.json()["company"]["company_id"]
        response = await client.post(
            f"/api/v1/companies/{company_id}/import-evidence/upload",
            files={"file": ("demo.csv", DEMO_CSV, "text/csv")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "needs_review"
        assert body["aggregate_id"] is None
        assert body["promoted_signals"] == []
        assert body["draft_status"] == "skipped"


@pytest.mark.parametrize(
    ("content", "filename"),
    [(b"arrival_date\n2026-01-01\n", "bad.csv"), (b"x" * (5 * 1024 * 1024 + 1), "large.csv")],
)
async def test_upload_rejects_invalid_or_oversized_csv(
    uow_factory: UowFactory,
    content: bytes,
    filename: str,
) -> None:
    async for client in make_client(uow_factory):
        initial = await client.post("/api/v1/mvp/prospects/analyze", json=analysis_payload())
        company_id = initial.json()["company"]["company_id"]
        response = await client.post(
            f"/api/v1/companies/{company_id}/import-evidence/upload",
            files={"file": (filename, content, "text/csv")},
        )
        assert response.status_code == 422
        assert "csv_parse" in response.json()["detail"]
