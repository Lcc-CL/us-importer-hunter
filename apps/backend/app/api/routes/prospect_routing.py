"""Thin HTTP adapter for deterministic prospect routing."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import (
    ProspectRouteReviewDep,
    ProspectRoutingBatchDep,
    ProspectRoutingQueryDep,
    ProspectRoutingSubmissionDep,
)
from app.domain.prospect_routing import ProspectRouteReviewStatus, ProspectTier
from app.schemas.mvp import ApiErrorResponse
from app.schemas.prospect_routing import (
    ProspectRouteListResponse,
    ProspectRouteResponse,
    ProspectRouteReviewRequest,
    ProspectRoutingBatchCreateRequest,
    ProspectRoutingBatchCreateResponse,
    ProspectRoutingCreateRequest,
    ProspectRoutingCreateResponse,
    ProspectRoutingRunResponse,
)

router = APIRouter(tags=["prospect-routing"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "/import-sessions/{session_id}/routing-runs",
    response_model=ProspectRoutingCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def create_prospect_routing_run(
    session_id: UUID,
    payload: ProspectRoutingCreateRequest,
    workflow: ProspectRoutingSubmissionDep,
) -> ProspectRoutingCreateResponse:
    submission = await workflow.submit(session_id, payload.to_domain())
    return ProspectRoutingCreateResponse(
        routing_run_id=submission.run.id,
        processing_job_id=submission.job.id,
        status=submission.job.status,
        reused=submission.reused,
        recalculated=submission.recalculated,
    )


@router.get(
    "/prospect-routing-runs/{routing_run_id}",
    response_model=ProspectRoutingRunResponse,
    responses=ERRORS,
)
async def get_prospect_routing_run(
    routing_run_id: UUID,
    workflow: ProspectRoutingQueryDep,
) -> ProspectRoutingRunResponse:
    run, job, generations = await workflow.get(routing_run_id)
    return ProspectRoutingRunResponse.from_domain(run, job, generations)


@router.get(
    "/prospect-routing-runs/{routing_run_id}/routes",
    response_model=ProspectRouteListResponse,
    responses=ERRORS,
)
async def list_prospect_routes(
    routing_run_id: UUID,
    workflow: ProspectRoutingQueryDep,
    generation: Annotated[int | None, Query(ge=1)] = None,
    tier: Annotated[ProspectTier | None, Query()] = None,
    review_status: Annotated[ProspectRouteReviewStatus | None, Query()] = None,
    minimum_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    maximum_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    has_contact: Annotated[bool | None, Query()] = None,
    role_category: Annotated[str | None, Query(max_length=40)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ProspectRouteListResponse:
    result = await workflow.list_routes(
        routing_run_id=routing_run_id,
        generation=generation,
        tier=tier,
        review_status=review_status,
        minimum_score=minimum_score,
        maximum_score=maximum_score,
        has_contact=has_contact,
        role_category=role_category,
        page=page,
        limit=limit,
    )
    return ProspectRouteListResponse.from_page(result)


@router.post(
    "/prospect-routes/{route_id}/review",
    response_model=ProspectRouteResponse,
    responses=ERRORS,
)
async def review_prospect_route(
    route_id: UUID,
    payload: ProspectRouteReviewRequest,
    workflow: ProspectRouteReviewDep,
) -> ProspectRouteResponse:
    route = await workflow.review(
        route_id,
        action=payload.action,
        effective_tier=payload.effective_tier,
        override_reason=payload.override_reason,
        reviewed_by=payload.reviewed_by,
    )
    return ProspectRouteResponse.from_domain(route)


@router.post(
    "/prospect-routing-runs/{routing_run_id}/prospect-batches",
    response_model=ProspectRoutingBatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def create_routed_prospect_batch(
    routing_run_id: UUID,
    payload: ProspectRoutingBatchCreateRequest,
    workflow: ProspectRoutingBatchDep,
) -> ProspectRoutingBatchCreateResponse:
    submission = await workflow.create(routing_run_id, tuple(payload.company_ids))
    return ProspectRoutingBatchCreateResponse(
        batch_id=submission.batch.id,
        status=submission.batch.status.value,
        reused=submission.reused,
        processing_started=False,
    )
