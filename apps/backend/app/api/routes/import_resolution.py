"""Thin HTTP adapter for D5b1 entity resolution and human review."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import (
    ImportEntityReviewDep,
    ImportResolutionQueryDep,
    ImportResolutionSubmissionDep,
)
from app.domain.import_resolution import ImportEntityReviewStatus, ImportEntityType
from app.schemas.import_resolution import (
    ImportEntityDecisionListResponse,
    ImportEntityDecisionResponse,
    ImportEntityReviewRequest,
    ImportResolutionResponse,
    ImportResolutionStartResponse,
)
from app.schemas.mvp import ApiErrorResponse

router = APIRouter(tags=["import-entity-resolution"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "/import-sessions/{session_id}/resolve",
    response_model=ImportResolutionStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def start_import_resolution(
    session_id: UUID,
    workflow: ImportResolutionSubmissionDep,
) -> ImportResolutionStartResponse:
    submission = await workflow.submit(session_id)
    return ImportResolutionStartResponse(
        session_id=session_id,
        processing_job_id=submission.job.id,
        status=submission.job.status,
        reused=submission.reused,
    )


@router.get(
    "/import-sessions/{session_id}/resolution",
    response_model=ImportResolutionResponse,
    responses=ERRORS,
)
async def get_import_resolution(
    session_id: UUID,
    workflow: ImportResolutionQueryDep,
) -> ImportResolutionResponse:
    resolution, job = await workflow.get(session_id)
    company_count, contact_count = await workflow.get_canonical_counts(session_id)
    return ImportResolutionResponse.from_domain(
        resolution,
        job,
        canonical_company_count=company_count,
        canonical_contact_count=contact_count,
    )


@router.get(
    "/import-sessions/{session_id}/entity-decisions",
    response_model=ImportEntityDecisionListResponse,
    responses=ERRORS,
)
async def list_import_entity_decisions(
    session_id: UUID,
    workflow: ImportResolutionQueryDep,
    entity_type: Annotated[ImportEntityType | None, Query()] = None,
    review_status: Annotated[ImportEntityReviewStatus | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    max_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ImportEntityDecisionListResponse:
    result = await workflow.list_decisions(
        session_id=session_id,
        entity_type=entity_type,
        review_status=review_status,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        page=page,
        limit=limit,
    )
    return ImportEntityDecisionListResponse.from_page(result)


@router.post(
    "/import-entity-decisions/{decision_id}/review",
    response_model=ImportEntityDecisionResponse,
    responses=ERRORS,
)
async def review_import_entity_decision(
    decision_id: UUID,
    payload: ImportEntityReviewRequest,
    workflow: ImportEntityReviewDep,
) -> ImportEntityDecisionResponse:
    reviewed = await workflow.review(
        decision_id,
        action=payload.action,
        reviewed_by=payload.reviewed_by,
    )
    return ImportEntityDecisionResponse.from_domain(reviewed)
