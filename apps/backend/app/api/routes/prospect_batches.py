"""Thin HTTP adapter for D2 prospect batches."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ProspectBatchQueryDep, ProspectBatchWorkflowDep
from app.schemas.mvp import ApiErrorResponse
from app.schemas.prospect_batch import (
    ProspectBatchCompanyListResponse,
    ProspectBatchCompanyResponse,
    ProspectBatchCreateRequest,
    ProspectBatchResponse,
    ProspectBatchResumeRequest,
    ProspectBatchRetryRequest,
    ProspectCompanyBlockersResponse,
)
from app.shared.exceptions import ResourceNotFoundError
from app.workflows.prospect_batch import (
    CreateProspectBatchCommand,
    ResumeProspectCompanyCommand,
    RetryProspectCompanyCommand,
)

router = APIRouter(tags=["prospect-batches"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "/discovery-tasks/{discovery_task_id}/batch-process",
    response_model=ProspectBatchResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def create_prospect_batch(
    discovery_task_id: UUID,
    payload: ProspectBatchCreateRequest,
    workflow: ProspectBatchWorkflowDep,
) -> ProspectBatchResponse:
    batch = await workflow.create(
        discovery_task_id,
        CreateProspectBatchCommand(
            company_ids=tuple(payload.company_ids),
            limit=payload.limit,
            sender=payload.sender.to_domain() if payload.sender else None,
        ),
    )
    return ProspectBatchResponse.from_domain(batch)


@router.get(
    "/prospect-batches/{batch_id}",
    response_model=ProspectBatchResponse,
    responses=ERRORS,
)
async def get_prospect_batch(
    batch_id: UUID,
    workflow: ProspectBatchQueryDep,
) -> ProspectBatchResponse:
    batch = await workflow.get(batch_id)
    if batch is None:
        raise ResourceNotFoundError(f"prospect batch not found: {batch_id}")
    return ProspectBatchResponse.from_domain(batch)


@router.get(
    "/prospect-batches/{batch_id}/companies",
    response_model=ProspectBatchCompanyListResponse,
    responses=ERRORS,
)
async def get_prospect_batch_companies(
    batch_id: UUID,
    workflow: ProspectBatchQueryDep,
) -> ProspectBatchCompanyListResponse:
    batch = await workflow.get(batch_id)
    if batch is None:
        raise ResourceNotFoundError(f"prospect batch not found: {batch_id}")
    return ProspectBatchCompanyListResponse(
        batch_id=batch.id,
        companies=[ProspectBatchCompanyResponse.from_domain(item) for item in batch.companies],
    )


@router.get(
    "/prospect-batches/{batch_id}/companies/{company_id}/blockers",
    response_model=ProspectCompanyBlockersResponse,
    responses=ERRORS,
)
async def get_prospect_batch_company_blockers(
    batch_id: UUID,
    company_id: UUID,
    workflow: ProspectBatchQueryDep,
) -> ProspectCompanyBlockersResponse:
    return ProspectCompanyBlockersResponse.from_workflow(
        await workflow.blockers(batch_id, company_id)
    )


@router.post(
    "/prospect-batches/{batch_id}/companies/{company_id}/retry",
    response_model=ProspectBatchResponse,
    responses=ERRORS,
)
async def retry_prospect_batch_company(
    batch_id: UUID,
    company_id: UUID,
    payload: ProspectBatchRetryRequest,
    workflow: ProspectBatchWorkflowDep,
) -> ProspectBatchResponse:
    batch = await workflow.retry(
        batch_id,
        company_id,
        RetryProspectCompanyCommand(sender=payload.sender.to_domain() if payload.sender else None),
    )
    return ProspectBatchResponse.from_domain(batch)


@router.post(
    "/prospect-batches/{batch_id}/companies/{company_id}/resume",
    response_model=ProspectBatchResponse,
    responses=ERRORS,
)
async def resume_prospect_batch_company(
    batch_id: UUID,
    company_id: UUID,
    payload: ProspectBatchResumeRequest,
    workflow: ProspectBatchWorkflowDep,
) -> ProspectBatchResponse:
    batch = await workflow.resume(
        batch_id,
        company_id,
        ResumeProspectCompanyCommand(
            sender=payload.sender.to_domain() if payload.sender else None
        ),
    )
    return ProspectBatchResponse.from_domain(batch)
