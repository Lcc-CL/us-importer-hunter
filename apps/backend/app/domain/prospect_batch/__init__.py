"""Persistent D2a prospect-batch aggregate."""

from app.domain.prospect_batch.aggregate import (
    PIPELINE_VERSION,
    ProspectBatch,
    ProspectBatchCompany,
    ProspectBatchCompanyStatus,
    ProspectBatchStage,
    ProspectBatchStatus,
    ProspectContactType,
    ProspectStageTiming,
)

__all__ = [
    "PIPELINE_VERSION",
    "ProspectBatch",
    "ProspectBatchCompany",
    "ProspectBatchCompanyStatus",
    "ProspectContactType",
    "ProspectBatchStage",
    "ProspectStageTiming",
    "ProspectBatchStatus",
]
