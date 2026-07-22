"""Internal small-file Import Evidence upload surface."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import EvidenceToDraftDep
from app.domain.services import SenderProfile
from app.schemas.import_evidence import EvidenceUploadResponse
from app.services.import_evidence.upload import MAX_CSV_BYTES
from app.workflows.import_evidence import EvidenceUploadError

router = APIRouter(tags=["import-evidence"])


@router.post(
    "/companies/{company_id}/import-evidence/upload",
    response_model=EvidenceUploadResponse,
    summary="上传 CSV 并重新评估单个公司",
)
async def upload_company_import_evidence(
    company_id: UUID,
    workflow: EvidenceToDraftDep,
    file: Annotated[UploadFile, File(description="UTF-8 CSV，最大 5MB / 5000 行")],
    provider: Annotated[str, Form()] = "csv",
    as_of_date: Annotated[date | None, Form()] = None,
    sender_name: Annotated[str | None, Form()] = None,
    sender_company: Annotated[str | None, Form()] = None,
    sender_value_proposition: Annotated[str | None, Form()] = None,
) -> EvidenceUploadResponse:
    if file.content_type not in ("text/csv", "application/csv", "application/vnd.ms-excel"):
        raise HTTPException(status_code=422, detail="csv_parse: 仅支持 CSV 文件")
    content = await file.read(MAX_CSV_BYTES + 1)
    sender_values = (sender_name, sender_company, sender_value_proposition)
    sender = (
        SenderProfile(
            name=sender_name.strip(),
            company=sender_company.strip(),
            value_proposition=sender_value_proposition.strip(),
        )
        if all(value and value.strip() for value in sender_values)
        and sender_name is not None
        and sender_company is not None
        and sender_value_proposition is not None
        else None
    )
    try:
        outcome = await workflow.upload(
            company_id=company_id,
            content=content,
            provider_name=provider.strip() or "csv",
            as_of_date=as_of_date,
            sender=sender,
        )
    except EvidenceUploadError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.stage == "company" else 422
        raise HTTPException(status_code=code, detail=f"{exc.stage}: {exc}") from exc
    return EvidenceUploadResponse.from_outcome(outcome)


@router.get(
    "/companies/{company_id}/import-evidence",
    response_model=EvidenceUploadResponse,
    summary="读取当前 Import Evidence 结果",
)
async def get_company_import_evidence(
    company_id: UUID,
    workflow: EvidenceToDraftDep,
) -> EvidenceUploadResponse:
    try:
        outcome = await workflow.get_current(company_id)
    except EvidenceUploadError as exc:
        raise HTTPException(status_code=404, detail=f"{exc.stage}: {exc}") from exc
    if outcome is None:
        raise HTTPException(status_code=404, detail="当前公司尚无 Import Evidence")
    return EvidenceUploadResponse.from_outcome(outcome)
