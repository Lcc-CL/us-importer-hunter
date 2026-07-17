"""Thin HTTP adapter for the synchronous MVP prospect workflow."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request

from app.api.deps import (
    ApproveEmailDraftDep,
    MvpProspectAnalysisDep,
    MvpProspectQueryDep,
)
from app.schemas.mvp import (
    ApiErrorResponse,
    DraftApprovalRequest,
    DraftApprovalResponse,
    ProspectAnalysisRequest,
    ProspectAnalysisResponse,
    ProspectDetailResponse,
)

router = APIRouter(prefix="/mvp", tags=["mvp"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse, "description": "Requested resource was not found"},
    409: {"model": ApiErrorResponse, "description": "Invalid domain state transition"},
    422: {"model": ApiErrorResponse, "description": "Request validation failed"},
    503: {"model": ApiErrorResponse, "description": "Configured provider is unavailable"},
    500: {"model": ApiErrorResponse, "description": "Unexpected system error"},
}


@router.post(
    "/prospects/analyze",
    response_model=ProspectAnalysisResponse,
    summary="Analyze one MVP prospect",
    description=(
        "Ingests one company and optional contact, then runs the existing opportunity, "
        "decision-maker, and email-draft workflows. Business rejection and partial success "
        "are returned as typed results. The conservative v1 qualification policy requires "
        "multiple distinct evidence sources; company.sources accepts those real references "
        "in one request so Swagger can exercise the complete Fake email path. The legacy "
        "company.source field remains valid only when company.website supplies its reference. "
        "No email is sent."
    ),
    responses=ERROR_RESPONSES,
)
async def analyze_prospect(
    payload: ProspectAnalysisRequest,
    request: Request,
    workflow: MvpProspectAnalysisDep,
) -> ProspectAnalysisResponse:
    outcome = await workflow.handle(payload.to_command(str(request.state.request_id)))
    return ProspectAnalysisResponse.from_outcome(outcome)


@router.get(
    "/prospects/{company_id}",
    response_model=ProspectDetailResponse,
    summary="Get a saved MVP prospect analysis",
    description=(
        "Reads saved domain aggregates only. It does not rescore the company, generate a "
        "draft, or emit domain events."
    ),
    responses=ERROR_RESPONSES,
)
async def get_prospect(
    company_id: UUID,
    workflow: MvpProspectQueryDep,
) -> ProspectDetailResponse:
    result = await workflow.handle(company_id)
    return ProspectDetailResponse.from_result(result)


@router.post(
    "/outreaches/{outreach_id}/drafts/{version}/approve",
    response_model=DraftApprovalResponse,
    summary="Approve an email draft",
    description=(
        "Calls the Outreach aggregate's approval behavior and persists approval status, "
        "timestamp, and approver name. Approval never sends the email."
    ),
    responses=ERROR_RESPONSES,
)
async def approve_email_draft(
    outreach_id: UUID,
    version: int,
    payload: DraftApprovalRequest,
    workflow: ApproveEmailDraftDep,
) -> DraftApprovalResponse:
    outcome = await workflow.handle(
        outreach_id=outreach_id,
        version=version,
        approver_id=payload.approver_id,
        approver_name=payload.approver_name,
    )
    return DraftApprovalResponse.from_outcome(outcome)
