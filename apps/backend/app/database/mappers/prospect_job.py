"""ProspectJob aggregate ↔ persistence mapping."""

from app.database.models.prospect_batch import ProspectBatchJobModel
from app.domain.prospect_job import ProspectJob, ProspectJobStatus
from app.domain.services import SenderProfile


class ProspectJobMapper:
    @staticmethod
    def to_model(job: ProspectJob) -> ProspectBatchJobModel:
        sender = job.sender
        return ProspectBatchJobModel(
            id=job.id,
            batch_id=job.batch_id,
            status=job.status.value,
            business_key=job.business_key,
            request_key_hash=job.request_key_hash,
            sender_name=sender.name if sender else None,
            sender_company=sender.company if sender else None,
            sender_value_proposition=sender.value_proposition if sender else None,
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
    def to_domain(model: ProspectBatchJobModel) -> ProspectJob:
        sender = None
        if (
            model.sender_name is not None
            and model.sender_company is not None
            and model.sender_value_proposition is not None
        ):
            sender = SenderProfile(
                name=model.sender_name,
                company=model.sender_company,
                value_proposition=model.sender_value_proposition,
            )
        return ProspectJob(
            id=model.id,
            batch_id=model.batch_id,
            status=ProspectJobStatus(model.status),
            business_key=model.business_key,
            request_key_hash=model.request_key_hash,
            sender=sender,
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
