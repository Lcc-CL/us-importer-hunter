"""Thin HTTP adapter for D2 prospect batches."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, status

from app.api.deps import (
    ProspectBatchQueryDep,
    ProspectBatchSubmissionDep,
    ProspectJobQueryDep,
)
from app.schemas.mvp import ApiErrorResponse
from app.schemas.prospect_batch import (
    ProspectBatchCompanyListResponse,
    ProspectBatchCompanyResponse,
    ProspectBatchCreateRequest,
    ProspectBatchCreateResponse,
    ProspectBatchExecutionResponse,
    ProspectBatchResponse,
    ProspectBatchResumeRequest,
    ProspectBatchRetryRequest,
    ProspectBatchStartRequest,
    ProspectBatchStartResponse,
    ProspectCompanyBlockersResponse,
)
from app.shared.exceptions import ResourceNotFoundError
from app.workflows.prospect_batch import (
    CreateProspectBatchCommand,
    ResumeProspectCompanyCommand,
    RetryProspectCompanyCommand,
    StartRoutingProspectBatchCommand,
)

router = APIRouter(tags=["prospect-batches"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    503: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "/discovery-tasks/{discovery_task_id}/batch-process",
    response_model=ProspectBatchCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def create_prospect_batch(
    discovery_task_id: UUID,
    payload: ProspectBatchCreateRequest,
    workflow: ProspectBatchSubmissionDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ProspectBatchCreateResponse:
    submission = await workflow.submit(
        discovery_task_id,
        CreateProspectBatchCommand(
            company_ids=tuple(payload.company_ids),
            limit=payload.limit,
            sender=payload.sender.to_domain() if payload.sender else None,
        ),
        idempotency_key=idempotency_key,
    )
    return ProspectBatchCreateResponse(
        batch_id=submission.batch.id,
        job_id=submission.job.id,
        status=submission.job.status.value,
        reused=submission.reused,
    )


@router.post(
    "/prospect-batches/{batch_id}/start",
    response_model=ProspectBatchStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def start_routing_prospect_batch(
    batch_id: UUID,
    payload: ProspectBatchStartRequest,
    workflow: ProspectBatchSubmissionDep,
) -> ProspectBatchStartResponse:
    submission = await workflow.start_routing_batch(
        batch_id,
        StartRoutingProspectBatchCommand(
            confirmation=payload.confirmation,
            provider_mode=payload.provider_mode,
            note=payload.note,
            sender=payload.sender.to_domain() if payload.sender else None,
        ),
    )
    return ProspectBatchStartResponse(
        batch_id=submission.batch.id,
        job_id=submission.job.id,
        status=submission.job.status.value,
        reused=submission.reused,
        processing_started=True,
    )


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
    "/prospect-batches/{batch_id}/execution",
    response_model=ProspectBatchExecutionResponse | None,
    responses=ERRORS,
)
async def get_prospect_batch_execution(
    batch_id: UUID,
    workflow: ProspectJobQueryDep,
    batch_workflow: ProspectBatchQueryDep,
) -> ProspectBatchExecutionResponse | None:
    job = await workflow.latest_for_batch(batch_id)
    if job is None:
        batch = await batch_workflow.get(batch_id)
        if batch is None:
            raise ResourceNotFoundError(f"prospect batch not found: {batch_id}")
        return None
    return ProspectBatchExecutionResponse.from_domain(job)


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
    response_model=ProspectBatchCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def retry_prospect_batch_company(
    batch_id: UUID,
    company_id: UUID,
    payload: ProspectBatchRetryRequest,
    workflow: ProspectBatchSubmissionDep,
) -> ProspectBatchCreateResponse:
    submission = await workflow.retry_company(
        batch_id,
        company_id,
        RetryProspectCompanyCommand(sender=payload.sender.to_domain() if payload.sender else None),
    )
    return ProspectBatchCreateResponse(
        batch_id=submission.batch.id,
        job_id=submission.job.id,
        status=submission.job.status.value,
        reused=submission.reused,
    )


@router.post(
    "/prospect-batches/{batch_id}/companies/{company_id}/resume",
    response_model=ProspectBatchCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def resume_prospect_batch_company(
    batch_id: UUID,
    company_id: UUID,
    payload: ProspectBatchResumeRequest,
    workflow: ProspectBatchSubmissionDep,
) -> ProspectBatchCreateResponse:
    submission = await workflow.resume_company(
        batch_id,
        company_id,
        ResumeProspectCompanyCommand(
            sender=payload.sender.to_domain() if payload.sender else None
        ),
    )
    return ProspectBatchCreateResponse(
        batch_id=submission.batch.id,
        job_id=submission.job.id,
        status=submission.job.status.value,
        reused=submission.reused,
    )
