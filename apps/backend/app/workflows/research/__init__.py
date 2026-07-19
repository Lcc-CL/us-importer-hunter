"""Research workflow: deep-dive analysis of a single company on demand,
outside the full lead-generation pipeline.

v0.2: website → fetched pages → cleaned text → extracted claims → validated
claims persisted as a ResearchRun. Never writes Company or Opportunity state.
"""

from app.workflows.research.promotion import (
    ClaimDecision,
    ClaimPromotionWorkflow,
    CompanyNotFound,
    InvalidDecision,
    PromotionConflict,
    PromotionError,
    PromotionResult,
    ProspectFormPayload,
    ResearchRunNotFound,
    ReviewAction,
    ReviewOutcome,
    ReviewRequest,
)
from app.workflows.research.workflow import (
    ClientFactory,
    FetcherFactory,
    ReadPage,
    ResearchAction,
    ResearchInputError,
    ResearchLimits,
    ResearchOutcome,
    ResearchRequest,
    ResearchWorkflow,
)

__all__ = [
    "ClaimDecision",
    "ClaimPromotionWorkflow",
    "ClientFactory",
    "CompanyNotFound",
    "InvalidDecision",
    "PromotionConflict",
    "PromotionError",
    "PromotionResult",
    "ProspectFormPayload",
    "ResearchRunNotFound",
    "ReviewAction",
    "ReviewOutcome",
    "ReviewRequest",
    "FetcherFactory",
    "ReadPage",
    "ResearchAction",
    "ResearchInputError",
    "ResearchLimits",
    "ResearchOutcome",
    "ResearchRequest",
    "ResearchWorkflow",
]
