"""HTTP contract and safety gates for D5e1 acceptance readiness."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_bulk_import_workflow, get_umail_result_import_workflow
from app.core.config import Settings
from app.main import create_app
from app.workflows.umail_feedback import UmailResultMatchEstimate


class _ShouldNotRun:
    async def upload(self, **_kwargs: object) -> None:
        raise AssertionError("write workflow must not run while the safety gate is blocked")

    async def estimate_matches(self, **_kwargs: object) -> UmailResultMatchEstimate:
        return UmailResultMatchEstimate(
            strong_id_matches=0,
            email_fallback_matches=0,
            ambiguous_rows=0,
        )


async def _client(*, acknowledged: bool = False) -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="development",
            real_data_acknowledged=acknowledged,
        )
    )
    app.dependency_overrides[get_bulk_import_workflow] = _ShouldNotRun
    app.dependency_overrides[get_umail_result_import_workflow] = _ShouldNotRun
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


async def test_netease_and_umail_preflight_have_no_write_dependencies() -> None:
    async for client in _client():
        netease = await client.post(
            "/api/v1/acceptance/netease-preflight",
            files={
                "file": (
                    "netease.csv",
                    "公司名称,邮箱,产品\nAtlas,a@example.test,hinges\n".encode(),
                    "text/csv",
                )
            },
        )
        assert netease.status_code == 200, netease.text
        assert netease.json()["no_business_side_effects"] is True
        assert netease.json()["real_data_gate"] == "blocked"

        umail = await client.post(
            "/api/v1/acceptance/umail-result-preflight",
            files={
                "file": (
                    "umail.csv",
                    b"email,event_type,occurred_at\na@example.test,delivered,2026-08-01\n",
                    "text/csv",
                )
            },
        )
        assert umail.status_code == 200, umail.text
        assert umail.json()["no_business_side_effects"] is True
        assert umail.json()["match_estimate_basis"] == "database_snapshot"


async def test_real_imports_require_mapping_confirmation_and_local_acknowledgement() -> None:
    content = b"company,email\nAtlas,a@example.test\n"
    async for client in _client():
        missing_confirmation = await client.post(
            "/api/v1/import-sessions",
            data={"real_data": "true"},
            files={"file": ("real.csv", content, "text/csv")},
        )
        assert missing_confirmation.status_code == 422
        assert (
            missing_confirmation.json()["code"]
            == "real_data_mapping_confirmation_required"
        )

        blocked = await client.post(
            "/api/v1/import-sessions",
            data={
                "real_data": "true",
                "mapping_confirmed": "true",
                "mapping": '{"company_name":"company","contact_email":"email"}',
            },
            files={"file": ("real.csv", content, "text/csv")},
        )
        assert blocked.status_code == 422
        assert blocked.json()["code"] == "real_data_acknowledgement_required"

        feedback = await client.post(
            "/api/v1/umail-result-imports",
            data={
                "real_data": "true",
                "mapping_confirmed": "true",
                "mapping": '{"event_type":"event_type","occurred_at":"occurred_at"}',
            },
            files={
                "file": (
                    "real-umail.csv",
                    b"event_type,occurred_at\ndelivered,2026-08-01\n",
                    "text/csv",
                )
            },
        )
        assert feedback.status_code == 422
        assert feedback.json()["code"] == "real_data_acknowledgement_required"

        apply = await client.post(
            "/api/v1/umail-result-imports/00000000-0000-4000-8000-000000000001/apply",
            json={"confirmed": True, "real_data": True},
        )
        assert apply.status_code == 422
        assert apply.json()["code"] == "real_data_acknowledgement_required"
