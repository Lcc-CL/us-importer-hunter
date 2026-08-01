"""Persistent execution aggregate for the lightweight PostgreSQL worker."""

from app.domain.prospect_job.aggregate import (
    ACTIVE_JOB_STATUSES,
    ProspectJob,
    ProspectJobStatus,
)

__all__ = ["ACTIVE_JOB_STATUSES", "ProspectJob", "ProspectJobStatus"]
