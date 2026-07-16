"""Opportunity workflow: the Company → Opportunity scoring seam (ADR-0020)."""

from app.workflows.opportunity.workflow import (
    OpportunityApplicationWorkflow,
    OpportunityProcessingAction,
    OpportunityProcessingOutcome,
)

__all__ = [
    "OpportunityApplicationWorkflow",
    "OpportunityProcessingAction",
    "OpportunityProcessingOutcome",
]
