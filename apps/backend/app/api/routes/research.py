"""Internal research API (v0.2 phase 3.2).

**Not for anonymous public deployment.** Until the DNS-rebinding window is
closed by connection-level IP pinning or a public-only egress proxy, these
endpoints must only be reachable by authenticated internal callers — the
attack needs someone able to submit arbitrary URLs (ADR-0026).

A research run that ends in `robots_denied`, `needs_browser` or
`budget_exceeded` is a *result*, not a server error: it is persisted and
returned with 201, and the caller branches on `status` / `failure_code`.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ClaimPromotionDep, ResearchWorkflowDep, UowFactoryDep
from app.domain.research import PromotionDecision
from app.schemas.mvp import ApiErrorResponse
from app.schemas.research import (
    ConfirmResearchRequest,
    ConfirmResearchResponse,
    ResearchRunCreatedResponse,
    ResearchRunListResponse,
    ResearchRunRequest,
    ResearchRunResponse,
    ResearchRunSummaryResponse,
)
from app.workflows.research import (
    ClaimDecision,
    CompanyNotFound,
    InvalidDecision,
    PromotionConflict,
    ResearchAction,
    ResearchRequest,
    ResearchRunNotFound,
    ReviewRequest,
)

router = APIRouter(tags=["research"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse, "description": "Requested resource was not found"},
    409: {"model": ApiErrorResponse, "description": "Conflicts with an applied decision"},
    422: {"model": ApiErrorResponse, "description": "Request validation failed"},
}


@router.post(
    "/research/runs",
    response_model=ResearchRunCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run website research",
    description=(
        "Fetches a company's own website, extracts standardized claims and validates each "
        "one against the pages actually read. Produces a proposal for human review: it "
        "never writes Company, Opportunity or company_signals, and never calls "
        "qualification or draft generation. Supply company_id for a known company, or "
        "company_name + website for a prospect that is not in the database yet. Runs that "
        "end partial or failed are still persisted and returned with 201."
    ),
    responses=ERROR_RESPONSES,
)
async def create_research_run(
    payload: ResearchRunRequest,
    workflow: ResearchWorkflowDep,
    uow_factory: UowFactoryDep,
) -> ResearchRunCreatedResponse:
    outcome = await workflow.handle(
        ResearchRequest(
            company_id=payload.company_id,
            company_name=payload.company_name,
            website=payload.website,
        )
    )

    if outcome.action is ResearchAction.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"company not found: {payload.company_id}",
        )

    assert outcome.research_id is not None  # every non-rejected run is persisted
    async with uow_factory() as uow:
        run = await uow.research_runs.get_by_id(outcome.research_id)
    if run is None:  # pragma: no cover — defensive
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="research run vanished after commit"
        )
    return ResearchRunCreatedResponse.from_outcome(outcome, run)


@router.get(
    "/research/runs/{run_id}",
    response_model=ResearchRunResponse,
    summary="Get one research run",
    description="Reads a saved run. Never re-fetches the website.",
    responses=ERROR_RESPONSES,
)
async def get_research_run(run_id: UUID, uow_factory: UowFactoryDep) -> ResearchRunResponse:
    async with uow_factory() as uow:
        run = await uow.research_runs.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"research run not found: {run_id}"
        )
    return ResearchRunResponse.from_run(run)


@router.get(
    "/companies/{company_id}/research-runs",
    response_model=ResearchRunListResponse,
    summary="List a company's research history",
    description=(
        "Most recent first. Runs whose company was deleted keep their snapshot but lose "
        "the link, so they no longer appear here."
    ),
    responses=ERROR_RESPONSES,
)
async def list_company_research_runs(
    company_id: UUID, uow_factory: UowFactoryDep, limit: int = 20
) -> ResearchRunListResponse:
    async with uow_factory() as uow:
        if not await uow.companies.exists(company_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"company not found: {company_id}"
            )
        runs = await uow.research_runs.list_for_company(company_id, limit=limit)
    return ResearchRunListResponse(
        company_id=company_id,
        runs=[ResearchRunSummaryResponse.from_run(run) for run in runs],
    )


@router.post(
    "/research/runs/{run_id}/confirm",
    response_model=ConfirmResearchResponse,
    summary="Review claims and promote the accepted ones",
    description=(
        "Records a reviewer's accept / edit / reject decisions for a run's claims. The "
        "whole batch is one transaction: either every decision lands or none does. "
        "Accepted and edited claims become Company sources and signals when a target "
        "company exists; rejected claims never produce company data. Replaying an "
        "identical request is a no-op. Contradicting a decision that already wrote "
        "company rows returns 409. Qualification, decision-maker selection and draft "
        "generation are never called from here."
    ),
    responses=ERROR_RESPONSES,
)
async def confirm_research_run(
    run_id: UUID,
    payload: ConfirmResearchRequest,
    workflow: ClaimPromotionDep,
) -> ConfirmResearchResponse:
    request = ReviewRequest(
        research_run_id=run_id,
        reviewer_name=payload.reviewer_name,
        target_company_id=payload.target_company_id,
        decisions=tuple(
            ClaimDecision(
                claim_position=decision.claim_position,
                decision=PromotionDecision(decision.decision),
                edited_detail=decision.edited_detail,
                edited_kind=decision.edited_kind,
            )
            for decision in payload.decisions
        ),
    )
    try:
        outcome = await workflow.handle(request)
    except (ResearchRunNotFound, CompanyNotFound) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PromotionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidDecision as exc:
        raise HTTPException(
            status_code=422, detail=str(exc)
        ) from exc
    return ConfirmResearchResponse.from_outcome(outcome)
