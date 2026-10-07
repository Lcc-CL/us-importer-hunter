"""D4a calibration persistence, refresh recovery, evaluation and exports."""

from collections.abc import AsyncIterator, Callable
from typing import cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_calibration_create_workflow,
    get_prospect_batch_workflow,
    get_uow_factory,
)
from app.core.config import Settings
from app.domain.calibration import (
    DraftProviderMode,
    ResearchProviderMode,
    WebsiteFetchMode,
)
from app.domain.clock import utcnow
from app.domain.repositories import CalibrationUnitOfWork, ProspectBatchUnitOfWork
from app.domain.values import SourceReference
from app.main import create_app
from app.workflows.calibration import CreateCalibrationRunWorkflow
from app.workflows.prospect_batch import ProspectBatchSubmissionWorkflow, ProspectBatchWorkflow
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_prospect_batch_api import (
    batch_workflow,
    run_pending_job,
)


async def make_client(
    uow_factory: UowFactory,
    workflow: ProspectBatchWorkflow,
) -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="development",
            research_extractor_provider="fake",
            email_generator_provider="fake",
        )
    )
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_prospect_batch_workflow] = lambda: workflow

    def calibration_create() -> CreateCalibrationRunWorkflow:
        batch_submission = ProspectBatchSubmissionWorkflow(
            cast(Callable[[], ProspectBatchUnitOfWork], uow_factory),
            max_attempts=3,
        )
        return CreateCalibrationRunWorkflow(
            uow_factory=cast(Callable[[], CalibrationUnitOfWork], uow_factory),
            batch_submission=batch_submission,
            website_fetch_mode=WebsiteFetchMode.FIXTURE,
            research_provider_mode=ResearchProviderMode.DETERMINISTIC_FAKE,
            draft_provider_mode=DraftProviderMode.DETERMINISTIC_FAKE,
        )

    app.dependency_overrides[get_calibration_create_workflow] = calibration_create
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_calibration_api_persists_report_evaluation_and_safe_exports(
    uow_factory: UowFactory,
) -> None:
    workflow = batch_workflow(uow_factory)
    calibration_id: str | None = None
    task_id: str | None = None
    company_ids: list[str] = []

    async for client in make_client(uow_factory, workflow):
        csv_content = (
            b"company_name,source_external_id,website,region,import_evidence\n"
            b"Atlas Hardware,atlas-1,https://atlas.example,US,BOL-ATLAS\n"
            b"Harbor Supply,harbor-1,https://harbor.example,US,BOL-HARBOR\n"
            b"Summit Tools,summit-1,https://summit.example,US,BOL-SUMMIT\n"
        )
        discovery = await client.post(
            "/api/v1/discovery-tasks/manual-csv",
            data={"prompt": "帮我找 3 家北美五金进口商"},
            files={"file": ("calibration.csv", csv_content, "text/csv")},
        )
        assert discovery.status_code == 201, discovery.text
        task_id = discovery.json()["task_id"]
        companies = await client.get(f"/api/v1/discovery-tasks/{task_id}/companies")
        company_ids = [item["company_id"] for item in companies.json()["companies"]]
        assert len(company_ids) == 3

        async with uow_factory() as uow:
            for position, company_id in enumerate(company_ids):
                company = await uow.companies.get_by_id(UUID(company_id))
                assert company is not None
                company.add_source(
                    SourceReference(
                        source="import_evidence",
                        reference=f"BOL-CALIBRATION-{position}",
                        retrieved_at=utcnow(),
                    )
                )
                for signal in (
                    "import_activity: customs shipments recorded",
                    "china_dependency: China origin observed",
                    "shipping_fit: ocean FCL container freight",
                    "cargo_value_potential: high value cargo",
                    "company_scale: warehouse and employees",
                    "growth_signal: growing import activity",
                    "logistics_complexity: multi-origin distribution centers",
                ):
                    company.add_signal(signal)
                await uow.companies.save(company)
            await uow.commit()

        path = f"/api/v1/discovery-tasks/{task_id}/calibrations"
        payload = {
            "company_ids": company_ids,
            "sender": {
                "name": "Alex Morgan",
                "company": "Harbor Bridge Logistics",
                "value_proposition": "We simplify Asia-to-US freight.",
            },
        }
        too_small = await client.post(path, json={"company_ids": company_ids[:2]})
        assert too_small.status_code == 422, too_small.text
        assert too_small.json()["code"] == "CALIBRATION_SAMPLE_SIZE_INVALID"

        created = await client.post(
            path,
            json=payload,
            headers={"Idempotency-Key": "calibration-click"},
        )
        duplicate = await client.post(
            path,
            json=payload,
            headers={"Idempotency-Key": "calibration-click"},
        )
        assert created.status_code == 202, created.text
        assert duplicate.status_code == 202, duplicate.text
        assert duplicate.json()["calibration_id"] == created.json()["calibration_id"]
        assert duplicate.json()["reused"] is True
        calibration_id = created.json()["calibration_id"]

        await run_pending_job(uow_factory, workflow)
        report = await client.get(f"/api/v1/calibrations/{calibration_id}")
        assert report.status_code == 200, report.text
        body = report.json()
        assert body["summary"]["sample_count"] == 3
        assert body["summary"]["website_research_success_count"] == 3
        assert body["summary"]["opportunity_generated_count"] == 3
        assert body["summary"]["draft_generated_count"] == 3
        assert body["providers"] == {
            "website_fetch_mode": "fixture",
            "research_provider_mode": "deterministic_fake",
            "draft_provider_mode": "deterministic_fake",
            "contact_source_mode": "official_website",
            "paid_request_count": 0,
            "research_provider_call_count": 0,
            "draft_provider_call_count": 0,
            "provider_duration_ms": body["providers"]["provider_duration_ms"],
            "token_usage_total": 0,
        }
        assert all(item["contact"]["contact_type"] == "personal" for item in body["companies"])
        assert all(item["draft"]["all_facts_traceable"] for item in body["companies"])
        assert all(item["draft"]["explicitly_not_sent"] for item in body["companies"])
        assert all(
            value == 0
            for key, value in body["truth_checks"].items()
            if key != "opportunity_score_is_probability"
        )
        assert body["truth_checks"]["opportunity_score_is_probability"] is False

        evaluation = await client.put(
            f"/api/v1/calibrations/{calibration_id}/companies/{company_ids[0]}/evaluation",
            json={
                "research_accuracy": 4,
                "opportunity_reasonableness": 4,
                "contact_usability": 4,
                "draft_personalization": 3,
                "draft_professionalism": 5,
                "ready_for_real_outreach": True,
                "reviewer_name": "Integration Reviewer",
                "notes": "Internal calibration note",
            },
        )
        assert evaluation.status_code == 200, evaluation.text

    assert calibration_id is not None and task_id is not None
    async for refreshed in make_client(uow_factory, workflow):
        report = await refreshed.get(f"/api/v1/calibrations/{calibration_id}")
        assert report.status_code == 200, report.text
        saved = report.json()["companies"][0]["evaluation"]
        assert saved["reviewer_name"] == "Integration Reviewer"
        assert saved["ready_for_real_outreach"] is True

        csv_export = await refreshed.get(
            f"/api/v1/calibrations/{calibration_id}/calibration-summary.csv"
        )
        json_export = await refreshed.get(
            f"/api/v1/calibrations/{calibration_id}/calibration-report.json"
        )
        assert csv_export.status_code == 200
        assert "Integration Reviewer" in csv_export.text
        assert json_export.status_code == 200
        lowered = json_export.text.lower()
        assert "api_key" not in lowered
        assert "provider_prompt" not in lowered
        assert "raw_html" not in lowered
