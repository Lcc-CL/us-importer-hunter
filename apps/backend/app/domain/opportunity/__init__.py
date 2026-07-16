"""Opportunity domain (Intelligence context): the central value aggregate."""

from app.domain.opportunity.aggregate import CLOSED_STAGES, Opportunity, OpportunityStage

__all__ = ["CLOSED_STAGES", "Opportunity", "OpportunityStage"]
