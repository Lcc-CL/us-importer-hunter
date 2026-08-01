"""Thin HTTP adapters for D4a calibration selection, review and export."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Response, status

from app.api.deps import (
    CalibrationCreateDep,
    CalibrationEvaluationDep,
    CalibrationReportDep,
)
from app.schemas.calibration import (
    CalibrationCreateRequest,
    CalibrationCreateResponse,
    CalibrationEvaluationRequest,
    CalibrationEvaluationResponse,
    CalibrationReportResponse,
)
from app.schemas.mvp import ApiErrorResponse
from app.services.calibration_exports import (
    calibration_report_json,
    calibration_summary_csv,
)
from app.workflows.calibration import (
    CalibrationCreateCommand,
    CalibrationEvaluationCommand,
    CalibrationEvaluationView,
)

router = APIRouter(tags=["calibrations"])
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "/discovery-tasks/{discovery_task_id}/calibrations",
    response_model=CalibrationCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def create_calibration_run(
    discovery_task_id: UUID,
    payload: CalibrationCreateRequest,
    workflow: CalibrationCreateDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CalibrationCreateResponse:
    submission = await workflow.handle(
        discovery_task_id,
        CalibrationCreateCommand(
            company_ids=tuple(payload.company_ids),
            sender=payload.sender.to_domain() if payload.sender else None,
        ),
        idempotency_key=idempotency_key,
    )
    return CalibrationCreateResponse(
        calibration_id=submission.run.id,
        batch_id=submission.batch_submission.batch.id,
        job_id=submission.batch_submission.job.id,
        status=submission.batch_submission.job.status.value,
        reused=submission.reused,
    )


@router.get(
    "/calibrations/{calibration_id}",
    response_model=CalibrationReportResponse,
    responses=ERRORS,
)
async def get_calibration_report(
    calibration_id: UUID,
    workflow: CalibrationReportDep,
) -> CalibrationReportResponse:
    return CalibrationReportResponse.from_workflow(await workflow.get(calibration_id))


@router.put(
    "/calibrations/{calibration_id}/companies/{company_id}/evaluation",
    response_model=CalibrationEvaluationResponse,
    responses=ERRORS,
)
async def save_calibration_evaluation(
    calibration_id: UUID,
    company_id: UUID,
    payload: CalibrationEvaluationRequest,
    workflow: CalibrationEvaluationDep,
) -> CalibrationEvaluationResponse:
    evaluation = await workflow.handle(
        calibration_id,
        company_id,
        CalibrationEvaluationCommand(**payload.model_dump()),
    )
    return CalibrationEvaluationResponse.from_view(
        CalibrationEvaluationView(
            research_accuracy=evaluation.research_accuracy,
            opportunity_reasonableness=evaluation.opportunity_reasonableness,
            contact_usability=evaluation.contact_usability,
            draft_personalization=evaluation.draft_personalization,
            draft_professionalism=evaluation.draft_professionalism,
            ready_for_real_outreach=evaluation.ready_for_real_outreach,
            reviewer_name=evaluation.reviewer_name,
            notes=evaluation.notes,
            reviewed_at=evaluation.reviewed_at,
        )
    )


@router.get("/calibrations/{calibration_id}/calibration-summary.csv", responses=ERRORS)
async def export_calibration_summary_csv(
    calibration_id: UUID,
    workflow: CalibrationReportDep,
) -> Response:
    report = CalibrationReportResponse.from_workflow(await workflow.get(calibration_id))
    return Response(
        content=calibration_summary_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="calibration-summary.csv"'
        },
    )


@router.get("/calibrations/{calibration_id}/calibration-report.json", responses=ERRORS)
async def export_calibration_report_json(
    calibration_id: UUID,
    workflow: CalibrationReportDep,
) -> Response:
    report = CalibrationReportResponse.from_workflow(await workflow.get(calibration_id))
    return Response(
        content=calibration_report_json(report),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="calibration-report.json"'
        },
    )
