"""Thin, read-only HTTP adapter for D5e real-data preflight."""

import json
from dataclasses import replace
from pathlib import PurePath
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import (
    AcceptancePreflightDep,
    SettingsDep,
    UmailResultImportWorkflowDep,
)
from app.schemas.acceptance import NetEasePreflightResponse, UmailPreflightResponse
from app.schemas.mvp import ApiErrorResponse
from app.services.acceptance import AcceptancePreflightError
from app.services.umail_feedback import FeedbackCsvValidationError
from app.shared.exceptions import InvalidInputError

router = APIRouter(prefix="/acceptance", tags=["acceptance"])
ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "/netease-preflight",
    response_model=NetEasePreflightResponse,
    responses=ERRORS,
    summary="Inspect a NetEase CSV/XLSX without creating business data",
)
async def preflight_netease_file(
    service: AcceptancePreflightDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="NetEase CSV or XLSX")],
    mapping: Annotated[str | None, Form()] = None,
) -> NetEasePreflightResponse:
    filename = PurePath(file.filename or "").name
    try:
        report = service.preflight_netease(
            file.file,
            filename=filename,
            mapping=_parse_mapping(mapping),
        )
    except AcceptancePreflightError as exc:
        raise InvalidInputError(code=exc.code, message=str(exc)) from exc
    return NetEasePreflightResponse.from_report(
        report,
        gate_enabled=settings.real_data_acknowledged,
    )


@router.post(
    "/umail-result-preflight",
    response_model=UmailPreflightResponse,
    responses=ERRORS,
    summary="Inspect an offline Umail result CSV without creating feedback data",
)
async def preflight_umail_result_file(
    service: AcceptancePreflightDep,
    settings: SettingsDep,
    workflow: UmailResultImportWorkflowDep,
    file: Annotated[UploadFile, File(description="Offline Umail result CSV")],
    mapping: Annotated[str | None, Form()] = None,
) -> UmailPreflightResponse:
    filename = PurePath(file.filename or "").name
    try:
        report = service.preflight_umail(
            file.file,
            filename=filename,
            mapping=_parse_mapping(mapping),
        )
        if not report.missing_required_fields and not report.duplicate_columns:
            try:
                estimate = await workflow.estimate_matches(
                    file=file.file,
                    mapping=report.suggested_mapping,
                )
            except FeedbackCsvValidationError:
                pass
            else:
                report = replace(
                    report,
                    estimated_strong_id_matches=estimate.strong_id_matches,
                    estimated_email_fallback_matches=estimate.email_fallback_matches,
                    estimated_ambiguous_rows=estimate.ambiguous_rows,
                    match_estimate_basis="database_snapshot",
                )
    except AcceptancePreflightError as exc:
        raise InvalidInputError(code=exc.code, message=str(exc)) from exc
    return UmailPreflightResponse.from_report(
        report,
        gate_enabled=settings.real_data_acknowledged,
    )


def _parse_mapping(value: str | None) -> dict[str, str]:
    if value is None or not value.strip():
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise InvalidInputError(
            code="acceptance_mapping_invalid",
            message="mapping must be a JSON object of logical field to source column",
        ) from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str)
        and isinstance(column, str)
        and key.strip()
        and column.strip()
        for key, column in decoded.items()
    ):
        raise InvalidInputError(
            code="acceptance_mapping_invalid",
            message="mapping must contain non-empty string keys and column names",
        )
    return {key.strip(): column.strip() for key, column in decoded.items()}
