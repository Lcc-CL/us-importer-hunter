"""ProspectBatch aggregate ↔ persistence mapping."""

from app.database.models.prospect_batch import ProspectBatchCompanyModel, ProspectBatchModel
from app.domain.prospect_batch import (
    ProspectBatch,
    ProspectBatchCompany,
    ProspectBatchCompanyStatus,
    ProspectBatchStage,
    ProspectBatchStatus,
)


class ProspectBatchMapper:
    @staticmethod
    def to_model(batch: ProspectBatch) -> ProspectBatchModel:
        return ProspectBatchModel(
            id=batch.id,
            discovery_task_id=batch.discovery_task_id,
            routing_run_id=batch.routing_run_id,
            routing_execution_generation=batch.routing_execution_generation,
            routing_selection_hash=batch.routing_selection_hash,
            requested_count=batch.requested_count,
            effective_count=batch.effective_count,
            status=batch.status.value,
            error_summary=batch.error_summary,
            created_at=batch.created_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            companies=[
                ProspectBatchCompanyModel(
                    batch_id=batch.id,
                    company_id=item.company_id,
                    company_name=item.company_name,
                    position=item.position,
                    pipeline_version=item.pipeline_version,
                    current_stage=item.current_stage.value,
                    status=item.status.value,
                    research_id=item.research_id,
                    opportunity_id=item.opportunity_id,
                    selected_contact_id=item.selected_contact_id,
                    outreach_id=item.outreach_id,
                    draft_version=item.draft_version,
                    score=item.score,
                    qualification_decision=item.qualification_decision,
                    reasons=list(item.reasons),
                    contact_name=item.contact_name,
                    contact_email=item.contact_email,
                    contact_source_url=item.contact_source_url,
                    draft_subject=item.draft_subject,
                    draft_status=item.draft_status,
                    error_code=item.error_code,
                    error_summary=item.error_summary,
                    started_at=item.started_at,
                    completed_at=item.completed_at,
                    blocking_claim_count=item.blocking_claim_count,
                    resumed_at=item.resumed_at,
                    resumed_from_stage=(
                        item.resumed_from_stage.value if item.resumed_from_stage else None
                    ),
                    resume_count=item.resume_count,
                )
                for item in batch.companies
            ],
        )

    @staticmethod
    def to_domain(model: ProspectBatchModel) -> ProspectBatch:
        batch = ProspectBatch(
            id=model.id,
            discovery_task_id=model.discovery_task_id,
            routing_run_id=model.routing_run_id,
            routing_execution_generation=model.routing_execution_generation,
            routing_selection_hash=model.routing_selection_hash,
            requested_count=model.requested_count,
            effective_count=model.effective_count,
            created_at=model.created_at,
            companies=[
                ProspectBatchCompany(
                    company_id=item.company_id,
                    company_name=item.company_name,
                    position=item.position,
                    pipeline_version=item.pipeline_version,
                    current_stage=ProspectBatchStage(item.current_stage),
                    status=ProspectBatchCompanyStatus(item.status),
                    research_id=item.research_id,
                    opportunity_id=item.opportunity_id,
                    selected_contact_id=item.selected_contact_id,
                    outreach_id=item.outreach_id,
                    draft_version=item.draft_version,
                    score=item.score,
                    qualification_decision=item.qualification_decision,
                    reasons=tuple(item.reasons),
                    contact_name=item.contact_name,
                    contact_email=item.contact_email,
                    contact_source_url=item.contact_source_url,
                    draft_subject=item.draft_subject,
                    draft_status=item.draft_status,
                    error_code=item.error_code,
                    error_summary=item.error_summary,
                    started_at=item.started_at,
                    completed_at=item.completed_at,
                    blocking_claim_count=item.blocking_claim_count,
                    resumed_at=item.resumed_at,
                    resumed_from_stage=(
                        ProspectBatchStage(item.resumed_from_stage)
                        if item.resumed_from_stage
                        else None
                    ),
                    resume_count=item.resume_count,
                )
                for item in model.companies
            ],
        )
        batch._status = ProspectBatchStatus(model.status)
        batch._started_at = model.started_at
        batch._completed_at = model.completed_at
        batch._error_summary = model.error_summary
        return batch
