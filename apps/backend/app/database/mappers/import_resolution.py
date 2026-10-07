"""Domain ↔ persistence mapping for import entity resolution."""

from app.database.models.import_resolution import (
    CompanyContactModel,
    CompanyExternalIdentityModel,
    CompanyResolutionProfileModel,
    ImportEntityDecisionModel,
    ImportProcessingJobModel,
    ImportResolutionModel,
)
from app.domain.import_resolution import (
    CompanyContact,
    CompanyContactStatus,
    CompanyExternalIdentity,
    CompanyResolutionProfile,
    ImportEntityDecision,
    ImportEntityDecisionKind,
    ImportEntityReviewStatus,
    ImportEntityType,
    ImportJobStatus,
    ImportJobType,
    ImportProcessingJob,
    ImportResolution,
    ImportResolutionStatus,
    ImportRoleCategory,
)


class ImportResolutionMapper:
    @staticmethod
    def resolution_to_model(resolution: ImportResolution) -> ImportResolutionModel:
        return ImportResolutionModel(
            import_session_id=resolution.import_session_id,
            status=resolution.status.value,
            total_rows=resolution.total_rows,
            processed_rows=resolution.processed_rows,
            companies_created=resolution.companies_created,
            companies_reused=resolution.companies_reused,
            company_reviews_required=resolution.company_reviews_required,
            contacts_created=resolution.contacts_created,
            contacts_reused=resolution.contacts_reused,
            company_contacts_created=resolution.company_contacts_created,
            invalid_rows=resolution.invalid_rows,
            failed_rows=resolution.failed_rows,
            started_at=resolution.started_at,
            completed_at=resolution.completed_at,
            error_summary=resolution.error_summary,
            created_at=resolution.created_at,
            updated_at=resolution.updated_at,
        )

    @staticmethod
    def resolution_to_domain(model: ImportResolutionModel) -> ImportResolution:
        return ImportResolution(
            import_session_id=model.import_session_id,
            status=ImportResolutionStatus(model.status),
            total_rows=model.total_rows,
            processed_rows=model.processed_rows,
            companies_created=model.companies_created,
            companies_reused=model.companies_reused,
            company_reviews_required=model.company_reviews_required,
            contacts_created=model.contacts_created,
            contacts_reused=model.contacts_reused,
            company_contacts_created=model.company_contacts_created,
            invalid_rows=model.invalid_rows,
            failed_rows=model.failed_rows,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_summary=model.error_summary,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def decision_to_model(decision: ImportEntityDecision) -> ImportEntityDecisionModel:
        return ImportEntityDecisionModel(
            id=decision.id,
            import_session_id=decision.import_session_id,
            raw_import_row_id=decision.raw_import_row_id,
            entity_type=decision.entity_type.value,
            candidate_entity_id=decision.candidate_entity_id,
            decision=decision.decision.value,
            confidence=decision.confidence,
            reason_codes=list(decision.reason_codes),
            review_status=decision.review_status.value,
            reviewed_by=decision.reviewed_by,
            reviewed_at=decision.reviewed_at,
            created_at=decision.created_at,
            updated_at=decision.updated_at,
        )

    @staticmethod
    def decision_to_domain(model: ImportEntityDecisionModel) -> ImportEntityDecision:
        return ImportEntityDecision(
            id=model.id,
            import_session_id=model.import_session_id,
            raw_import_row_id=model.raw_import_row_id,
            entity_type=ImportEntityType(model.entity_type),
            candidate_entity_id=model.candidate_entity_id,
            decision=ImportEntityDecisionKind(model.decision),
            confidence=model.confidence,
            reason_codes=tuple(model.reason_codes),
            review_status=ImportEntityReviewStatus(model.review_status),
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def identity_to_model(identity: CompanyExternalIdentity) -> CompanyExternalIdentityModel:
        return CompanyExternalIdentityModel(
            id=identity.id,
            company_id=identity.company_id,
            source=identity.source,
            external_id=identity.external_id,
            first_seen_at=identity.first_seen_at,
            last_seen_at=identity.last_seen_at,
            created_at=identity.created_at,
            updated_at=identity.updated_at,
        )

    @staticmethod
    def identity_to_domain(model: CompanyExternalIdentityModel) -> CompanyExternalIdentity:
        return CompanyExternalIdentity(
            id=model.id,
            company_id=model.company_id,
            source=model.source,
            external_id=model.external_id,
            first_seen_at=model.first_seen_at,
            last_seen_at=model.last_seen_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def profile_to_model(profile: CompanyResolutionProfile) -> CompanyResolutionProfileModel:
        return CompanyResolutionProfileModel(
            company_id=profile.company_id,
            normalized_name=profile.normalized_name,
            normalized_domain=profile.normalized_domain,
            normalized_address=profile.normalized_address,
            company_type=profile.company_type,
            normalized_phone=profile.normalized_phone,
            first_seen_at=profile.first_seen_at,
            last_seen_at=profile.last_seen_at,
            source_import_row_id=profile.source_import_row_id,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def profile_to_domain(model: CompanyResolutionProfileModel) -> CompanyResolutionProfile:
        return CompanyResolutionProfile(
            company_id=model.company_id,
            normalized_name=model.normalized_name,
            normalized_domain=model.normalized_domain,
            normalized_address=model.normalized_address,
            company_type=model.company_type,
            normalized_phone=model.normalized_phone,
            first_seen_at=model.first_seen_at,
            last_seen_at=model.last_seen_at,
            source_import_row_id=model.source_import_row_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def company_contact_to_model(link: CompanyContact) -> CompanyContactModel:
        return CompanyContactModel(
            id=link.id,
            company_id=link.company_id,
            contact_id=link.contact_id,
            raw_title=link.raw_title,
            role_category=link.role_category.value,
            seniority=link.seniority,
            is_department_contact=link.is_department_contact,
            status=link.status.value,
            first_seen_at=link.first_seen_at,
            last_seen_at=link.last_seen_at,
            source_import_row_id=link.source_import_row_id,
            created_at=link.created_at,
            updated_at=link.updated_at,
        )

    @staticmethod
    def company_contact_to_domain(model: CompanyContactModel) -> CompanyContact:
        return CompanyContact(
            id=model.id,
            company_id=model.company_id,
            contact_id=model.contact_id,
            raw_title=model.raw_title,
            role_category=ImportRoleCategory(model.role_category),
            seniority=model.seniority,
            is_department_contact=model.is_department_contact,
            status=CompanyContactStatus(model.status),
            first_seen_at=model.first_seen_at,
            last_seen_at=model.last_seen_at,
            source_import_row_id=model.source_import_row_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def job_to_model(job: ImportProcessingJob) -> ImportProcessingJobModel:
        return ImportProcessingJobModel(
            id=job.id,
            import_session_id=job.import_session_id,
            routing_run_id=job.routing_run_id,
            job_type=job.job_type.value,
            status=job.status.value,
            business_key=job.business_key,
            available_at=job.available_at,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            lease_owner=job.lease_owner,
            lease_acquired_at=job.lease_acquired_at,
            lease_expires_at=job.lease_expires_at,
            heartbeat_at=job.heartbeat_at,
            last_error_code=job.last_error_code,
            last_error_summary=job.last_error_summary,
            recovery_count=job.recovery_count,
            last_recovered_at=job.last_recovered_at,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def job_to_domain(model: ImportProcessingJobModel) -> ImportProcessingJob:
        return ImportProcessingJob(
            id=model.id,
            import_session_id=model.import_session_id,
            routing_run_id=model.routing_run_id,
            job_type=ImportJobType(model.job_type),
            status=ImportJobStatus(model.status),
            business_key=model.business_key,
            available_at=model.available_at,
            attempt_count=model.attempt_count,
            max_attempts=model.max_attempts,
            lease_owner=model.lease_owner,
            lease_acquired_at=model.lease_acquired_at,
            lease_expires_at=model.lease_expires_at,
            heartbeat_at=model.heartbeat_at,
            last_error_code=model.last_error_code,
            last_error_summary=model.last_error_summary,
            recovery_count=model.recovery_count,
            last_recovered_at=model.last_recovered_at,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            updated_at=model.updated_at,
        )
