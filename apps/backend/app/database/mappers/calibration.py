"""Calibration aggregate ↔ persistence mapping."""

from app.database.models.calibration import (
    CalibrationEvaluationModel,
    CalibrationRunModel,
)
from app.domain.calibration import (
    CalibrationEvaluation,
    CalibrationRun,
    ContactSourceMode,
    DraftProviderMode,
    ResearchProviderMode,
    WebsiteFetchMode,
)


class CalibrationRunMapper:
    @staticmethod
    def to_model(run: CalibrationRun) -> CalibrationRunModel:
        return CalibrationRunModel(
            id=run.id,
            discovery_task_id=run.discovery_task_id,
            prospect_batch_id=run.prospect_batch_id,
            sample_count=run.sample_count,
            website_fetch_mode=run.website_fetch_mode.value,
            research_provider_mode=run.research_provider_mode.value,
            draft_provider_mode=run.draft_provider_mode.value,
            contact_source_mode=run.contact_source_mode.value,
            created_at=run.created_at,
            updated_at=run.updated_at,
            evaluations=[
                CalibrationEvaluationModel(
                    calibration_id=run.id,
                    company_id=item.company_id,
                    research_accuracy=item.research_accuracy,
                    opportunity_reasonableness=item.opportunity_reasonableness,
                    contact_usability=item.contact_usability,
                    draft_personalization=item.draft_personalization,
                    draft_professionalism=item.draft_professionalism,
                    ready_for_real_outreach=item.ready_for_real_outreach,
                    reviewer_name=item.reviewer_name,
                    notes=item.notes,
                    reviewed_at=item.reviewed_at,
                )
                for item in run.evaluations
            ],
        )

    @staticmethod
    def to_domain(model: CalibrationRunModel) -> CalibrationRun:
        return CalibrationRun(
            id=model.id,
            discovery_task_id=model.discovery_task_id,
            prospect_batch_id=model.prospect_batch_id,
            sample_count=model.sample_count,
            website_fetch_mode=WebsiteFetchMode(model.website_fetch_mode),
            research_provider_mode=ResearchProviderMode(model.research_provider_mode),
            draft_provider_mode=DraftProviderMode(model.draft_provider_mode),
            contact_source_mode=ContactSourceMode(model.contact_source_mode),
            created_at=model.created_at,
            updated_at=model.updated_at,
            evaluations=[
                CalibrationEvaluation(
                    company_id=item.company_id,
                    research_accuracy=item.research_accuracy,
                    opportunity_reasonableness=item.opportunity_reasonableness,
                    contact_usability=item.contact_usability,
                    draft_personalization=item.draft_personalization,
                    draft_professionalism=item.draft_professionalism,
                    ready_for_real_outreach=item.ready_for_real_outreach,
                    reviewer_name=item.reviewer_name,
                    notes=item.notes,
                    reviewed_at=item.reviewed_at,
                )
                for item in model.evaluations
            ],
        )
