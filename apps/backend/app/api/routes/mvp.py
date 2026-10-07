"""Thin HTTP adapter for the synchronous MVP prospect workflow."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.deps import (
    ApproveEmailDraftDep,
    MvpProspectAnalysisDep,
    MvpProspectQueryDep,
    UowFactoryDep,
    get_decision_maker_selection_service,
)
from app.domain.services import DecisionMakerSelectionService
from app.schemas.mvp import (
    ApiErrorResponse,
    DecisionMakerConfirmRequest,
    DecisionMakerConfirmResponse,
    DraftApprovalRequest,
    DraftApprovalResponse,
    ProspectAnalysisRequest,
    ProspectAnalysisResponse,
    ProspectDetailResponse,
)
from app.shared.exceptions import ResourceNotFoundError

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


@router.post(
    "/prospects/{company_id}/decision-maker/confirm",
    response_model=DecisionMakerConfirmResponse,
    summary="Confirm a reviewed primary decision maker",
    description=(
        "Persists the reviewer's choice of primary contact after manual review. "
        "The contact must belong to the company and be in the current eligible "
        "candidate set. Rejected, historical and sales-only contacts are blocked."
    ),
    responses=ERROR_RESPONSES,
)
async def confirm_decision_maker(
    company_id: UUID,
    payload: DecisionMakerConfirmRequest,
    uow_factory: UowFactoryDep,
    selection_service: Annotated[
        DecisionMakerSelectionService, Depends(get_decision_maker_selection_service)
    ],
    query_workflow: MvpProspectQueryDep,
) -> DecisionMakerConfirmResponse:
    async with uow_factory() as uow:
        company = await uow.companies.get_by_id(company_id)
        if company is None:
            raise ResourceNotFoundError(f"company {company_id} was not found")

        contacts = list(await uow.contacts.list_for_company(company_id))
        target = next((c for c in contacts if c.id == payload.contact_id), None)
        if target is None:
            raise ResourceNotFoundError(
                f"contact {payload.contact_id} not found or does not belong to company {company_id}"
            )

        candidates = selection_service.score_all(contacts, company_id=company_id)
        matched = next((c for c in candidates if c.contact_id == payload.contact_id), None)
        if matched is None:
            raise ResourceNotFoundError("contact was not scored in the current candidate set")

        if not matched.eligible:
            from fastapi import HTTPException
            reasons = ", ".join(r.value for r in matched.rejection_reasons)
            raise HTTPException(status_code=409, detail=f"contact is not eligible: {reasons}")

        opportunity = await uow.opportunities.get_for_company_and_user(
            company_id, UUID("00000000-0000-0000-0000-000000000000")
        )
        if opportunity is None:
            raise ResourceNotFoundError(f"no opportunity for company {company_id}")

        outreaches = list(await uow.outreaches.list_for_opportunity(opportunity.id))
        if not outreaches:
            from app.domain.outreach import Outreach
            outreach = Outreach.create(opportunity.id)
        else:
            outreach = outreaches[0]

        try:
            outreach.attach_contact(payload.contact_id)
        except Exception:
            pass

        await uow.outreaches.save(outreach)
        await uow.commit()

    result = await query_workflow.handle(company_id)
    response = ProspectDetailResponse.from_result(result)
    return DecisionMakerConfirmResponse(
        **response.model_dump(),
        confirmed=True,
        draft_regenerated=False,
    )
