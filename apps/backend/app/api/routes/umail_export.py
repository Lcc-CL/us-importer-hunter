"""Thin HTTP adapter for Umail CSV export and suppression."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.deps import SuppressionWorkflowDep, UmailExportWorkflowDep
from app.schemas.mvp import ApiErrorResponse
from app.schemas.umail_export import (
    SuppressionCreateRequest,
    SuppressionDeactivateRequest,
    SuppressionEntryListResponse,
    SuppressionEntryResponse,
    UmailExportBatchResponse,
    UmailExportCreateRequest,
)

router = APIRouter(tags=["umail-export"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "/suppressions",
    response_model=SuppressionEntryResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def create_suppression(
    payload: SuppressionCreateRequest,
    workflow: SuppressionWorkflowDep,
) -> SuppressionEntryResponse:
    entry = await workflow.create(
        email=payload.email,
        domain=payload.domain,
        company=payload.company,
        reason=payload.reason,
        source=payload.source,
        created_by=payload.created_by,
    )
    return SuppressionEntryResponse.from_domain(entry)


@router.get(
    "/suppressions",
    response_model=SuppressionEntryListResponse,
    responses=ERRORS,
)
async def list_suppressions(
    workflow: SuppressionWorkflowDep,
    active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SuppressionEntryListResponse:
    result = await workflow.list(active=active, page=page, limit=limit)
    return SuppressionEntryListResponse.from_page(result)


@router.post(
    "/suppressions/{entry_id}/deactivate",
    response_model=SuppressionEntryResponse,
    responses=ERRORS,
)
async def deactivate_suppression(
    entry_id: UUID,
    payload: SuppressionDeactivateRequest,
    workflow: SuppressionWorkflowDep,
) -> SuppressionEntryResponse:
    entry = await workflow.deactivate(
        entry_id,
        deactivated_by=payload.deactivated_by,
    )
    return SuppressionEntryResponse.from_domain(entry)


@router.post(
    "/prospect-routing-runs/{routing_run_id}/umail-export-batches",
    response_model=UmailExportBatchResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def create_umail_export_batch(
    routing_run_id: UUID,
    payload: UmailExportCreateRequest,
    workflow: UmailExportWorkflowDep,
) -> UmailExportBatchResponse:
    submission = await workflow.prepare(
        routing_run_id=routing_run_id,
        company_ids=tuple(payload.company_ids),
        campaign=payload.campaign,
    )
    return UmailExportBatchResponse.from_submission(submission)


@router.get(
    "/umail-export-batches/{batch_id}",
    response_model=UmailExportBatchResponse,
    responses=ERRORS,
)
async def get_umail_export_batch(
    batch_id: UUID,
    workflow: UmailExportWorkflowDep,
) -> UmailExportBatchResponse:
    submission = await workflow.get(batch_id)
    return UmailExportBatchResponse.from_submission(submission)


@router.get(
    "/umail-export-batches/{batch_id}/download",
    responses=ERRORS,
)
async def download_umail_export_batch(
    batch_id: UUID,
    workflow: UmailExportWorkflowDep,
) -> Response:
    download = await workflow.download(batch_id)
    return Response(
        content=download.content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{download.filename}"',
            "X-Content-SHA256": download.batch.content_sha256,
            "X-Email-Sent": "false",
        },
    )
