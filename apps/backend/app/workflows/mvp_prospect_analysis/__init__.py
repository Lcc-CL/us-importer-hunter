"""Minimal synchronous MVP prospect facade and supporting read/approval workflows."""

from app.workflows.mvp_prospect_analysis.approval import (
    ApproveEmailDraftWorkflow,
    DraftApprovalOutcome,
)
from app.workflows.mvp_prospect_analysis.query import (
    MvpProspectQueryWorkflow,
    ProspectQueryResult,
)
from app.workflows.mvp_prospect_analysis.workflow import (
    MVP_SYSTEM_USER_ID,
    CompanyStageResult,
    ContactStageResult,
    DecisionMakerStageResult,
    EmailDraftStageResult,
    MvpProspectAnalysisCommand,
    MvpProspectAnalysisOutcome,
    MvpProspectAnalysisWorkflow,
    OpportunityStageResult,
    OverallStatus,
    ProspectCompanyInput,
    ProspectContactInput,
    ProspectSignalInput,
    ProspectSourceInput,
    StageStatus,
    UowFactory,
)

__all__ = [
    "MVP_SYSTEM_USER_ID",
    "ApproveEmailDraftWorkflow",
    "CompanyStageResult",
    "ContactStageResult",
    "DecisionMakerStageResult",
    "DraftApprovalOutcome",
    "EmailDraftStageResult",
    "MvpProspectAnalysisCommand",
    "MvpProspectAnalysisOutcome",
    "MvpProspectAnalysisWorkflow",
    "MvpProspectQueryWorkflow",
    "OpportunityStageResult",
    "OverallStatus",
    "ProspectCompanyInput",
    "ProspectContactInput",
    "ProspectQueryResult",
    "ProspectSignalInput",
    "ProspectSourceInput",
    "StageStatus",
    "UowFactory",
]
