"""Thin HTTP adapter for persistent importer discovery tasks."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import DiscoveryTaskQueryDep, DiscoveryTaskWorkflowDep
from app.schemas.discovery_task import (
    DiscoveryCompanyListResponse,
    DiscoveryCompanyResponse,
    DiscoveryTaskCreateRequest,
    DiscoveryTaskResponse,
)
from app.services.discovery import ManualCsvCompanyDiscoveryProvider
from app.workflows.discovery_task import CreateDiscoveryTaskCommand

router = APIRouter(prefix="/discovery-tasks", tags=["discovery-tasks"])


@router.post("", response_model=DiscoveryTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_discovery_task(
    payload: DiscoveryTaskCreateRequest,
    workflow: DiscoveryTaskWorkflowDep,
) -> DiscoveryTaskResponse:
    task = await workflow.handle(CreateDiscoveryTaskCommand(prompt=payload.prompt))
    return DiscoveryTaskResponse.from_domain(task)


@router.post(
    "/manual-csv",
    response_model=DiscoveryTaskResponse,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Development-only real CSV provider. Results are explicitly labelled manual_csv "
        "and are never presented as automatic ImportYeti discovery."
    ),
)
async def create_manual_csv_discovery_task(
    workflow: DiscoveryTaskWorkflowDep,
    prompt: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> DiscoveryTaskResponse:
    provider = ManualCsvCompanyDiscoveryProvider(await file.read())
    task = await workflow.handle(CreateDiscoveryTaskCommand(prompt=prompt), provider=provider)
    return DiscoveryTaskResponse.from_domain(task)


@router.get("/{task_id}", response_model=DiscoveryTaskResponse)
async def get_discovery_task(
    task_id: UUID,
    workflow: DiscoveryTaskQueryDep,
) -> DiscoveryTaskResponse:
    task = await workflow.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"discovery task not found: {task_id}")
    return DiscoveryTaskResponse.from_domain(task)


@router.get("/{task_id}/companies", response_model=DiscoveryCompanyListResponse)
async def get_discovery_task_companies(
    task_id: UUID,
    workflow: DiscoveryTaskQueryDep,
) -> DiscoveryCompanyListResponse:
    task = await workflow.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"discovery task not found: {task_id}")
    # Same-task duplicates are retained for audit/counting but not returned as
    # repeated company cards. Existing DB companies remain visible because
    # they carry company_id and no duplicate_of_id.
    visible = [item for item in task.candidates if item.duplicate_of_id is None]
    return DiscoveryCompanyListResponse(
        task_id=task.id,
        companies=[DiscoveryCompanyResponse.from_domain(item) for item in visible],
    )
