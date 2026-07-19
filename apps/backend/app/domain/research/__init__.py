"""Research domain (v0.2): what a website claimed, before it becomes fact.

Produces claims for human review only — never Company or Opportunity state
(ADR-0025).
"""

from app.domain.research.aggregate import ResearchRun
from app.domain.research.values import (
    ALLOWED_CLAIM_KINDS,
    TERMINAL_RUN_STATUSES,
    ClaimRejectionReason,
    ExtractionResult,
    ExtractorIdentity,
    PromotionDecision,
    ProposedClaim,
    RejectedClaim,
    ResearchClaim,
    ResearchFailureCode,
    ResearchPage,
    ResearchProfile,
    ResearchPromotion,
    ResearchRunStatus,
)

__all__ = [
    "ALLOWED_CLAIM_KINDS",
    "TERMINAL_RUN_STATUSES",
    "ClaimRejectionReason",
    "ExtractionResult",
    "ExtractorIdentity",
    "PromotionDecision",
    "ProposedClaim",
    "RejectedClaim",
    "ResearchClaim",
    "ResearchFailureCode",
    "ResearchPage",
    "ResearchProfile",
    "ResearchPromotion",
    "ResearchRun",
    "ResearchRunStatus",
]
