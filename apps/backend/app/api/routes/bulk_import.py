"""Thin HTTP adapter for raw NetEase CSV intake."""

import json
from pathlib import PurePath
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import BulkImportQueryDep, BulkImportWorkflowDep
from app.domain.bulk_import import RawImportRowStatus
from app.schemas.bulk_import import (
    ImportSessionCreateResponse,
    ImportSessionResponse,
    RawImportRowListResponse,
)
from app.schemas.mvp import ApiErrorResponse
from app.services.bulk_import import BulkCsvValidationError
from app.shared.exceptions import InvalidInputError, ResourceNotFoundError

router = APIRouter(prefix="/import-sessions", tags=["bulk-import"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
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
    response_model=ImportSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Create a traceable raw CSV import session",
    description=(
        "Streams a CSV into raw audit rows only. It does not create companies, contacts, "
        "opportunities, research runs, drafts, or email activity."
    ),
)
async def create_import_session(
    response: Response,
    workflow: BulkImportWorkflowDep,
    file: Annotated[UploadFile, File(description="CSV, maximum 20 MB / 20,000 rows")],
    source: Annotated[str, Form()] = "netease_foreign_trade",
    mapping: Annotated[str | None, Form()] = None,
) -> ImportSessionCreateResponse:
    filename = PurePath(file.filename or "").name
    if not filename.lower().endswith(".csv"):
        raise InvalidInputError(
            code="bulk_import_file_type_invalid",
            message="D5a1 only accepts .csv files",
        )
    if file.content_type and file.content_type.lower() not in CSV_CONTENT_TYPES:
        raise InvalidInputError(
            code="bulk_import_file_type_invalid",
            message="D5a1 only accepts CSV content types",
        )
    parsed_mapping = _parse_mapping(mapping)
    try:
        outcome = await workflow.upload(
            file=file.file,
            original_filename=filename,
            source=source,
            mapping=parsed_mapping,
        )
    except BulkCsvValidationError as exc:
        raise InvalidInputError(code=exc.code, message=str(exc)) from exc
    except ValueError as exc:
        raise InvalidInputError(code="bulk_import_invalid_input", message=str(exc)) from exc
    if outcome.reused_existing:
        response.status_code = status.HTTP_200_OK
    return ImportSessionCreateResponse.from_outcome(outcome)


@router.get(
    "/{session_id}",
    response_model=ImportSessionResponse,
    responses=ERROR_RESPONSES,
)
async def get_import_session(
    session_id: UUID,
    workflow: BulkImportQueryDep,
) -> ImportSessionResponse:
    session = await workflow.get_session(session_id)
    if session is None:
        raise ResourceNotFoundError(f"import session not found: {session_id}")
    return ImportSessionResponse.from_domain(session)


@router.get(
    "/{session_id}/rows",
    response_model=RawImportRowListResponse,
    responses=ERROR_RESPONSES,
)
async def get_import_session_rows(
    session_id: UUID,
    workflow: BulkImportQueryDep,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    row_status: Annotated[RawImportRowStatus | None, Query(alias="status")] = None,
) -> RawImportRowListResponse:
    result = await workflow.list_rows(
        session_id=session_id,
        page=page,
        limit=limit,
        status=row_status,
    )
    if result is None:
        raise ResourceNotFoundError(f"import session not found: {session_id}")
    return RawImportRowListResponse.from_page(result)


def _parse_mapping(value: str | None) -> dict[str, str]:
    if value is None or not value.strip():
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise InvalidInputError(
            code="bulk_import_mapping_invalid",
            message="mapping must be a JSON object of logical_field to CSV column name",
        ) from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str)
        and isinstance(column, str)
        and key.strip()
        and column.strip()
        for key, column in decoded.items()
    ):
        raise InvalidInputError(
            code="bulk_import_mapping_invalid",
            message="mapping must contain non-empty string keys and column names",
        )
    return {key.strip(): column for key, column in decoded.items()}
