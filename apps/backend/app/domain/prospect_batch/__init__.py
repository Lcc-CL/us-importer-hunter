"""Persistent D2a prospect-batch aggregate."""

from app.domain.prospect_batch.aggregate import (
    PIPELINE_VERSION,
    DiscoveryBatchCompanySourceContext,
    DiscoveryProspectBatchSourceContext,
    ProspectBatch,
    ProspectBatchCompany,
    ProspectBatchCompanyStatus,
    ProspectBatchSourceContext,
    ProspectBatchSourceKind,
    ProspectBatchStage,
    ProspectBatchStatus,
    ProspectContactType,
    ProspectStageTiming,
    RoutingBatchCompanySourceContext,
    RoutingProspectBatchSourceContext,
)

__all__ = [
    "PIPELINE_VERSION",
    "DiscoveryBatchCompanySourceContext",
    "DiscoveryProspectBatchSourceContext",
    "ProspectBatch",
    "ProspectBatchCompany",
    "ProspectBatchCompanyStatus",
    "ProspectContactType",
    "ProspectBatchSourceContext",
    "ProspectBatchSourceKind",
    "ProspectBatchStage",
    "ProspectStageTiming",
    "ProspectBatchStatus",
    "RoutingBatchCompanySourceContext",
    "RoutingProspectBatchSourceContext",
]
