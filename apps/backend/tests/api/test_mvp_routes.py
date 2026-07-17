"""HTTP adapter tests for the three minimal MVP endpoints."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_approve_email_draft_workflow,
    get_mvp_prospect_analysis_workflow,
    get_mvp_prospect_query_workflow,
)
from app.core.config import Settings
from app.domain.company import Company
from app.domain.services import SenderProfile
from app.domain.values import CompanyName, SourceReference, WebsiteUrl
from app.main import create_app
from app.shared.exceptions import (
    ApplicationConflictError,
    ProviderUnavailableError,
    ResourceNotFoundError,
)
from app.workflows.mvp_prospect_analysis import (
    CompanyStageResult,
    ContactStageResult,
    DecisionMakerStageResult,
    DraftApprovalOutcome,
    EmailDraftStageResult,
    MvpProspectAnalysisCommand,
    MvpProspectAnalysisOutcome,
    OpportunityStageResult,
    OverallStatus,
    ProspectQueryResult,
    StageStatus,
)

REQUEST_ID = "11111111-1111-1111-1111-111111111111"
COMPANY_ID = UUID("22222222-2222-2222-2222-222222222222")
OPPORTUNITY_ID = UUID("33333333-3333-3333-3333-333333333333")
CONTACT_ID = UUID("44444444-4444-4444-4444-444444444444")
OUTREACH_ID = UUID("55555555-5555-5555-5555-555555555555")


class StubAnalysisWorkflow:
    def __init__(self, outcome: MvpProspectAnalysisOutcome) -> None:
        self.outcome = outcome
        self.command: MvpProspectAnalysisCommand | None = None

    async def handle(
        self, command: MvpProspectAnalysisCommand
    ) -> MvpProspectAnalysisOutcome:
        self.command = command
        return self.outcome


class StubQueryWorkflow:
    def __init__(
        self,
        result: ProspectQueryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

    async def handle(self, company_id: UUID) -> ProspectQueryResult:
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


class StubApprovalWorkflow:
    def __init__(
        self,
        outcome: DraftApprovalOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.error = error

    async def handle(
        self,
        *,
        outreach_id: UUID,
        version: int,
        approver_id: UUID | None,
        approver_name: str | None,
    ) -> DraftApprovalOutcome:
        if self.error:
            raise self.error
        assert self.outcome is not None
        return self.outcome


def analysis_outcome(
    status: OverallStatus = OverallStatus.COMPLETED,
) -> MvpProspectAnalysisOutcome:
    completed = status is OverallStatus.COMPLETED
    return MvpProspectAnalysisOutcome(
        request_id=REQUEST_ID,
        overall_status=status,
        company=CompanyStageResult(
            action=(StageStatus.CREATED if completed else StageStatus.REJECTED),
            company_id=COMPANY_ID if completed else None,
            name="Pacific Home Goods",
        ),
        opportunity=OpportunityStageResult(
            action=(StageStatus.QUALIFIED if completed else StageStatus.SKIPPED),
            opportunity_id=OPPORTUNITY_ID if completed else None,
            score=81.0 if completed else None,
            qualification_decision="qualified" if completed else None,
        ),
        contact=ContactStageResult(
            action=StageStatus.CREATED if completed else StageStatus.SKIPPED,
            contact_id=CONTACT_ID if completed else None,
        ),
        decision_maker=DecisionMakerStageResult(
            action=StageStatus.SELECTED if completed else StageStatus.SKIPPED,
            selected_contact_id=CONTACT_ID if completed else None,
        ),
        email_draft=EmailDraftStageResult(
            action=StageStatus.GENERATED if completed else StageStatus.SKIPPED,
            outreach_id=OUTREACH_ID if completed else None,
            version=1 if completed else None,
            subject="Freight partnership",
            body="Hi Maria",
            status="generated" if completed else None,
        ),
    )


def query_result() -> ProspectQueryResult:
    company = Company.create(
        CompanyName("Pacific Home Goods"), WebsiteUrl("https://phg.example")
    )
    company._id = COMPANY_ID
    company.add_source(
        SourceReference(
            source="importyeti",
            reference="https://phg.example",
            retrieved_at=datetime(2026, 7, 16, tzinfo=UTC),
        )
    )
    return ProspectQueryResult(
        company=company,
        opportunity=None,
        contacts=(),
        decision_maker_rankings=(),
        outreaches=(),
    )


def request_payload() -> dict[str, object]:
    return {
        "company": {
            "name": "Pacific Home Goods",
            "website": "https://phg.example",
            "sources": [
                {
                    "source": "importyeti",
                    "reference": "https://www.importyeti.com/company/pacific-home-goods",
                },
                {
                    "source": "company_website",
                    "reference": "https://phg.example/about",
                },
            ],
            "signals": [],
        },
        "contact": {
            "name": "Maria Chen",
            "title": "Director of Supply Chain",
            "email": "maria@phg.example",
            "source": "website",
        },
        "sender": {
            "name": "Alex",
            "company": "Harbor Logistics",
            "value_proposition": "Reliable inbound freight support.",
        },
    }


@pytest.fixture
async def api_client() -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    settings = Settings(_env_file=None, app_env="development")
    app = create_app(settings)
    app.dependency_overrides[get_mvp_prospect_analysis_workflow] = (
        lambda: StubAnalysisWorkflow(analysis_outcome())
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app


async def test_post_analyze_success_and_no_internal_type_leak(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client
    workflow = StubAnalysisWorkflow(analysis_outcome())
    app.dependency_overrides[get_mvp_prospect_analysis_workflow] = lambda: workflow
    response = await client.post(
        "/api/v1/mvp/prospects/analyze",
        json=request_payload(),
        headers={"X-Request-ID": REQUEST_ID},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] == "COMPLETED"
    assert body["email_draft"]["status"] == "generated"
    assert "_sa_instance_state" not in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert workflow.command is not None
    assert isinstance(workflow.command.sender, SenderProfile)
    assert [source.source for source in workflow.command.company.sources] == [
        "importyeti",
        "company_website",
    ]
    assert workflow.command.company.source is None


async def test_post_analyze_legacy_source_uses_website_as_reference(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client
    workflow = StubAnalysisWorkflow(analysis_outcome())
    app.dependency_overrides[get_mvp_prospect_analysis_workflow] = lambda: workflow
    payload = request_payload()
    company = payload["company"]
    assert isinstance(company, dict)
    company.pop("sources")
    company["source"] = "importyeti"

    response = await client.post("/api/v1/mvp/prospects/analyze", json=payload)

    assert response.status_code == 200
    assert workflow.command is not None
    assert workflow.command.company.source == "importyeti"


async def test_post_analyze_legacy_source_without_website_requires_migration(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _app = api_client
    payload = request_payload()
    company = payload["company"]
    assert isinstance(company, dict)
    company.pop("sources")
    company["source"] = "importyeti"
    company["website"] = None

    response = await client.post("/api/v1/mvp/prospects/analyze", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


async def test_post_analyze_validation_error(api_client: tuple[AsyncClient, FastAPI]) -> None:
    client, _app = api_client
    response = await client.post("/api/v1/mvp/prospects/analyze", json={})
    assert response.status_code == 422
    assert set(response.json()) == {"code", "message", "request_id"}


async def test_invalid_supplied_request_id_is_replaced(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client
    workflow = StubAnalysisWorkflow(analysis_outcome())
    app.dependency_overrides[get_mvp_prospect_analysis_workflow] = lambda: workflow
    response = await client.post(
        "/api/v1/mvp/prospects/analyze",
        json=request_payload(),
        headers={"X-Request-ID": "not-a-uuid"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "not-a-uuid"
    assert workflow.command is not None
    UUID(workflow.command.request_id)


async def test_post_analyze_business_rejection_is_200(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client
    app.dependency_overrides[get_mvp_prospect_analysis_workflow] = lambda: StubAnalysisWorkflow(
        analysis_outcome(OverallStatus.REJECTED)
    )
    response = await client.post("/api/v1/mvp/prospects/analyze", json=request_payload())
    assert response.status_code == 200
    assert response.json()["overall_status"] == "REJECTED"


async def test_post_analyze_partial_is_200(api_client: tuple[AsyncClient, FastAPI]) -> None:
    client, app = api_client
    partial = analysis_outcome()
    partial = MvpProspectAnalysisOutcome(
        request_id=partial.request_id,
        overall_status=OverallStatus.PARTIAL,
        company=partial.company,
        opportunity=partial.opportunity,
        contact=partial.contact,
        decision_maker=partial.decision_maker,
        email_draft=EmailDraftStageResult(action=StageStatus.FAILED),
        warnings=("provider unavailable",),
    )
    app.dependency_overrides[get_mvp_prospect_analysis_workflow] = lambda: StubAnalysisWorkflow(
        partial
    )
    response = await client.post("/api/v1/mvp/prospects/analyze", json=request_payload())
    assert response.status_code == 200
    assert response.json()["overall_status"] == "PARTIAL"


async def test_get_prospect_success(api_client: tuple[AsyncClient, FastAPI]) -> None:
    client, app = api_client
    app.dependency_overrides[get_mvp_prospect_query_workflow] = lambda: StubQueryWorkflow(
        query_result()
    )
    response = await client.get(f"/api/v1/mvp/prospects/{COMPANY_ID}")
    assert response.status_code == 200
    assert response.json()["company"]["name"] == "Pacific Home Goods"


async def test_get_prospect_missing_returns_404(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client
    app.dependency_overrides[get_mvp_prospect_query_workflow] = lambda: StubQueryWorkflow(
        error=ResourceNotFoundError("company was not found")
    )
    response = await client.get(f"/api/v1/mvp/prospects/{COMPANY_ID}")
    assert response.status_code == 404
    assert response.json()["code"] == "resource_not_found"


async def test_approve_missing_draft_returns_404(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client
    app.dependency_overrides[get_approve_email_draft_workflow] = lambda: StubApprovalWorkflow(
        error=ResourceNotFoundError("draft version was not found")
    )
    response = await client.post(
        f"/api/v1/mvp/outreaches/{OUTREACH_ID}/drafts/99/approve",
        json={"approver_name": "Alex"},
    )
    assert response.status_code == 404


async def test_approve_success(api_client: tuple[AsyncClient, FastAPI]) -> None:
    client, app = api_client
    outcome = DraftApprovalOutcome(
        outreach_id=OUTREACH_ID,
        version=1,
        approval_status="approved",
        approved_at=datetime(2026, 7, 16, tzinfo=UTC),
        approved_by_name="Alex",
    )
    app.dependency_overrides[get_approve_email_draft_workflow] = lambda: StubApprovalWorkflow(
        outcome
    )
    response = await client.post(
        f"/api/v1/mvp/outreaches/{OUTREACH_ID}/drafts/1/approve",
        json={"approver_name": "Alex"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["approval_status"] == "approved"
    assert response.json()["approved_by_name"] == "Alex"


async def test_approve_conflict_returns_409(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client
    app.dependency_overrides[get_approve_email_draft_workflow] = lambda: StubApprovalWorkflow(
        error=ApplicationConflictError("outreach is terminal")
    )
    response = await client.post(
        f"/api/v1/mvp/outreaches/{OUTREACH_ID}/drafts/1/approve",
        json={"approver_name": "Alex"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state"


async def test_provider_dependency_unavailable_returns_503(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = api_client

    def unavailable() -> None:
        raise ProviderUnavailableError("do not expose provider internals")

    app.dependency_overrides[get_mvp_prospect_analysis_workflow] = unavailable
    response = await client.post("/api/v1/mvp/prospects/analyze", json=request_payload())
    assert response.status_code == 503
    assert response.json()["message"] == "The configured provider is unavailable"
    assert "provider internals" not in response.text


async def test_swagger_and_openapi_include_all_mvp_routes(
    api_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _app = api_client
    docs = await client.get("/docs")
    schema = (await client.get("/openapi.json")).json()
    assert docs.status_code == 200
    paths = schema["paths"]
    assert "/api/v1/mvp/prospects/analyze" in paths
    assert "/api/v1/mvp/prospects/{company_id}" in paths
    assert "/api/v1/mvp/outreaches/{outreach_id}/drafts/{version}/approve" in paths
    analyze_schema = schema["components"]["schemas"]["ProspectAnalysisRequest"]
    assert analyze_schema["examples"]
