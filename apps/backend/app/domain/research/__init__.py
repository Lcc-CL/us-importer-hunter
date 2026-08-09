"""Research domain (v0.2): what a website claimed, before it becomes fact.

Produces claims for human review only — never Company or Opportunity state
(ADR-0025).
"""

from app.domain.research.aggregate import ResearchRun
from app.domain.research.document import (
    MAX_RESEARCH_DOCUMENT_CHARS,
    ResearchDocument,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
    research_document_content_hash,
)
from app.domain.research.values import (
    ALLOWED_CLAIM_KINDS,
    TERMINAL_RUN_STATUSES,
    ClaimRejectionReason,
    ExtractionResult,
    ExtractorIdentity,
    OutputLanguage,
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
    "OutputLanguage",
    "MAX_RESEARCH_DOCUMENT_CHARS",
    "ALLOWED_CLAIM_KINDS",
    "TERMINAL_RUN_STATUSES",
    "ClaimRejectionReason",
    "ExtractionResult",
    "ExtractorIdentity",
    "PromotionDecision",
    "ProposedClaim",
    "RejectedClaim",
    "ResearchClaim",
    "ResearchDocument",
    "ResearchDocumentSourceType",
    "ResearchDocumentStatus",
    "ResearchDocumentTrustLevel",
    "ResearchFailureCode",
    "ResearchPage",
    "ResearchProfile",
    "ResearchPromotion",
    "ResearchRun",
    "ResearchRunStatus",
    "research_document_content_hash",
]
