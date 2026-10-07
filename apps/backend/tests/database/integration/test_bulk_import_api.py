"""D5a1 API and persistence behavior against real PostgreSQL."""

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.domain.discovery import DiscoveryResult, RawCompanySnapshot
from app.domain.events import CompanyDiscovered
from app.domain.values import SourceReference
from app.main import create_app
from app.workflows.company_ingestion import CompanyIngestionWorkflow
from tests.database.integration.conftest import UowFactory
from tests.services.bulk_import.test_tabular_intake import _build_xlsx


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


async def test_upload_is_idempotent_and_rows_support_pagination_and_status_filter(
    uow_factory: UowFactory,
) -> None:
    content = (
        "公司,邮箱\n"
        "Atlas,a@example.com\n"
        "Atlas,a@example.com\n"
        "\n"
        "MissingOnly\n"
    ).encode()
    session_id: str | None = None
    async for client in make_client(uow_factory):
        first = await client.post(
            "/api/v1/import-sessions",
            data={
                "source": "netease_foreign_trade",
                "mapping": '{"company_name":"公司","contact_email":"邮箱"}',
            },
            files={"file": ("synthetic-netease.csv", content, "text/csv")},
        )
        assert first.status_code == 201, first.text
        body = first.json()
        session_id = body["session_id"]
        assert body["status"] == "partial_failed"
        assert body["encoding"] == "utf-8"
        assert body["total_rows"] == 4
        assert body["accepted_rows"] == 1
        assert body["invalid_rows"] == 2
        assert body["duplicate_rows"] == 1
        assert body["reused_existing"] is False

        duplicate = await client.post(
            "/api/v1/import-sessions",
            data={"source": "netease_foreign_trade"},
            files={"file": ("renamed.csv", content, "text/csv")},
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["session_id"] == session_id
        assert duplicate.json()["reused_existing"] is True

        refreshed = await client.get(f"/api/v1/import-sessions/{session_id}")
        assert refreshed.status_code == 200
        assert refreshed.json()["total_rows"] == 4

        invalid_page = await client.get(
            f"/api/v1/import-sessions/{session_id}/rows",
            params={"status": "invalid", "page": 1, "limit": 1},
        )
        assert invalid_page.status_code == 200, invalid_page.text
        page = invalid_page.json()
        assert page["total"] == 2
        assert len(page["rows"]) == 1
        assert page["rows"][0]["status"] == "invalid"
        assert page["rows"][0]["error_codes"]

        second_page = await client.get(
            f"/api/v1/import-sessions/{session_id}/rows",
            params={"status": "invalid", "page": 2, "limit": 1},
        )
        assert second_page.status_code == 200
        assert second_page.json()["rows"][0]["row_number"] > page["rows"][0]["row_number"]

    assert session_id is not None
    async with uow_factory() as uow:
        persisted = await uow.bulk_import.get_session(UUID(session_id))
        rows, total = await uow.bulk_import.list_rows(
            session_id=UUID(session_id),
            status=None,
            offset=0,
            limit=100,
        )
    assert persisted is not None
    assert len(rows) == total == 4


async def test_rejected_file_creates_no_session_and_uses_unified_error_shape(
    uow_factory: UowFactory,
) -> None:
    async for client in make_client(uow_factory):
        response = await client.post(
            "/api/v1/import-sessions",
            files={"file": ("empty.csv", b"", "text/csv")},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "bulk_import_csv_empty"
        assert response.json()["request_id"]
    async with uow_factory() as uow:
        persisted = await uow.bulk_import.find_session(
            source="netease_foreign_trade",
            file_sha256=hashlib.sha256(b"").hexdigest(),
        )
    assert persisted is None


async def test_xlsx_upload_persists_inherited_rows_and_is_idempotent(
    uow_factory: UowFactory,
) -> None:
    content = _build_xlsx(
        sheet_name="客户线索",
        headers=["公司名称", "官网", "联系人姓名", "联系人邮箱"],
        rows=[
            ["Atlas Hardware", "atlas.example", "Alice", "alice@atlas.example"],
            ["", "", "Bob", "bob@atlas.example"],
        ],
        merges=["A2:A3", "B2:B3"],
    )
    mapping = (
        '{"company_name":"公司名称","website":"官网",'
        '"contact_name":"联系人姓名","contact_email":"联系人邮箱"}'
    )
    session_id: str | None = None
    async for client in make_client(uow_factory):
        first = await client.post(
            "/api/v1/import-sessions",
            data={"source": "netease_foreign_trade", "mapping": mapping},
            files={
                "file": (
                    "synthetic.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert first.status_code == 201, first.text
        body = first.json()
        session_id = body["session_id"]
        assert body["file_type"] == "xlsx"
        assert body["encoding"] == "xlsx-xml"
        assert body["total_rows"] == 2
        assert body["accepted_rows"] == 2

        duplicate = await client.post(
            "/api/v1/import-sessions",
            data={"source": "netease_foreign_trade", "mapping": mapping},
            files={
                "file": (
                    "renamed.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["session_id"] == session_id
        assert duplicate.json()["reused_existing"] is True

        rows_response = await client.get(
            f"/api/v1/import-sessions/{session_id}/rows",
            params={"page": 1, "limit": 100},
        )
        assert rows_response.status_code == 200
        rows = rows_response.json()["rows"]
        assert len(rows) == 2
        inherited = next(
            row for row in rows if row["row_number"] == 3
        )
        payload = inherited["raw_payload"]
        assert payload["fields"]["公司名称"] == "Atlas Hardware"
        assert payload["inherited_company_source_row"] == 2
        assert payload["grouping_rule"] == "xlsx_vertical_merge"

    assert session_id is not None
    async with uow_factory() as uow:
        persisted, total = await uow.bulk_import.list_rows(
            session_id=UUID(session_id),
            status=None,
            offset=0,
            limit=100,
        )
    assert len(persisted) == total == 2


async def test_bulk_import_does_not_change_existing_core_aggregates_or_read_api(
    uow_factory: UowFactory,
) -> None:
    ingestion = CompanyIngestionWorkflow(uow_factory)
    company = await ingestion.handle(
        CompanyDiscovered(
            run_id=uuid4(),
            result=DiscoveryResult(
                snapshot=RawCompanySnapshot(
                    name_text="Existing Core Importer",
                    website_text="https://existing-core.example",
                    source=SourceReference(
                        source="integration_test",
                        reference="https://evidence.example/existing-core",
                        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
                    ),
                )
            ),
        )
    )
    assert company.company_id is not None

    async for client in make_client(uow_factory):
        upload = await client.post(
            "/api/v1/import-sessions",
            files={"file": ("raw-only.csv", b"company\nRaw Only\n", "text/csv")},
        )
        assert upload.status_code == 201, upload.text
        saved = await client.get(f"/api/v1/mvp/prospects/{company.company_id}")
        assert saved.status_code == 200, saved.text
        assert UUID(saved.json()["company"]["company_id"]) == company.company_id
