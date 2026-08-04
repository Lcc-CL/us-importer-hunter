"""Thin HTTP adapter for offline Umail result feedback."""

import json
from pathlib import PurePath
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import UmailResultImportWorkflowDep
from app.domain.umail_feedback import ContactEngagementEventType, UmailResultMatchStatus
from app.schemas.mvp import ApiErrorResponse
from app.schemas.umail_feedback import (
    UmailFeedbackStatisticsResponse,
    UmailResultApplyRequest,
    UmailResultImportResponse,
    UmailResultRowListResponse,
)
from app.services.umail_feedback import FeedbackCsvValidationError
from app.shared.exceptions import InvalidInputError

router = APIRouter(prefix="/umail-result-imports", tags=["umail-feedback"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}
CSV_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
    "application/octet-stream",
}


@router.post(
    "",
    response_model=UmailResultImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def upload_umail_result_import(
    response: Response,
    workflow: UmailResultImportWorkflowDep,
    file: Annotated[UploadFile, File(description="Offline Umail result CSV")],
    mapping: Annotated[str | None, Form()] = None,
    created_by: Annotated[str, Form()] = "local_reviewer",
) -> UmailResultImportResponse:
    filename = PurePath(file.filename or "").name
    if not filename.lower().endswith(".csv"):
        raise InvalidInputError(
            code="umail_result_file_type_invalid",
            message="Umail result feedback only accepts .csv files",
        )
    if file.content_type and file.content_type.lower() not in CSV_CONTENT_TYPES:
        raise InvalidInputError(
            code="umail_result_file_type_invalid",
            message="Umail result feedback only accepts CSV content types",
        )
    try:
        submission = await workflow.upload(
            file=file.file,
            source_filename=filename,
            mapping=_parse_mapping(mapping),
            created_by=created_by,
        )
    except FeedbackCsvValidationError as exc:
        raise InvalidInputError(code=exc.code, message=str(exc)) from exc
    if submission.reused:
        response.status_code = status.HTTP_200_OK
    return UmailResultImportResponse.from_submission(submission)


@router.get(
    "/{result_import_id}",
    response_model=UmailResultImportResponse,
    responses=ERRORS,
)
async def get_umail_result_import(
    result_import_id: UUID,
    workflow: UmailResultImportWorkflowDep,
) -> UmailResultImportResponse:
    value = await workflow.get(result_import_id)
    return UmailResultImportResponse.from_domain(value, reused=True)


@router.get(
    "/{result_import_id}/rows",
    response_model=UmailResultRowListResponse,
    responses=ERRORS,
)
async def list_umail_result_rows(
    result_import_id: UUID,
    workflow: UmailResultImportWorkflowDep,
    match_status: Annotated[UmailResultMatchStatus | None, Query(alias="match_status")] = None,
    event_type: Annotated[ContactEngagementEventType | None, Query()] = None,
    campaign: Annotated[str | None, Query(max_length=200)] = None,
    suppression_impact: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> UmailResultRowListResponse:
    result = await workflow.list_rows(
        result_import_id=result_import_id,
        match_status=match_status,
        event_type=event_type,
        campaign=campaign,
        suppression_impact=suppression_impact,
        page=page,
        limit=limit,
    )
    return UmailResultRowListResponse.from_page(result_import_id, result)


@router.post(
    "/{result_import_id}/apply",
    response_model=UmailResultImportResponse,
    responses=ERRORS,
)
async def apply_umail_result_import(
    result_import_id: UUID,
    _payload: UmailResultApplyRequest,
    workflow: UmailResultImportWorkflowDep,
) -> UmailResultImportResponse:
    outcome = await workflow.apply(result_import_id)
    return UmailResultImportResponse.from_apply(outcome)


@router.get(
    "/{result_import_id}/statistics",
    response_model=UmailFeedbackStatisticsResponse,
    responses=ERRORS,
)
async def get_umail_feedback_statistics(
    result_import_id: UUID,
    workflow: UmailResultImportWorkflowDep,
) -> UmailFeedbackStatisticsResponse:
    statistics = await workflow.statistics(result_import_id)
    return UmailFeedbackStatisticsResponse.from_domain(statistics)


def _parse_mapping(value: str | None) -> dict[str, str]:
    if value is None or not value.strip():
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise InvalidInputError(
            code="umail_result_mapping_invalid",
            message="mapping must be a JSON object of logical field to CSV column",
        ) from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str)
        and isinstance(column, str)
        and key.strip()
        and column.strip()
        for key, column in decoded.items()
    ):
        raise InvalidInputError(
            code="umail_result_mapping_invalid",
            message="mapping must contain non-empty string keys and column names",
        )
    return {key.strip(): column.strip() for key, column in decoded.items()}
