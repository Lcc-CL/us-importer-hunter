"""Contact services: normalization, deduplication, decision-maker policy."""
from app.services.contact.decision_maker import (
    POLICY_VERSION,
    DeterministicDecisionMakerSelectionService,
)
from app.services.contact.deduplicator import RepositoryContactDeduplicator
from app.services.contact.normalizer import ContactNormalizer, NormalizedContactCandidate
from app.services.contact.role_matcher import (
    DeterministicRoleMatcher,
    RoleClassification,
    RoleMatcher,
    classify_title,
)
from app.services.contact.scorer import (
    POLICY_VERSION_V2,
    CandidateScore,
    DecisionMakerSelectionResult,
    RejectionReason,
    SelectionStatus,
    SixFactorScorer,
)
from app.services.contact.selector import select
from app.services.contact.title_normalizer import NormalizedTitle, normalize_title

__all__ = [
    "DeterministicRoleMatcher",
    "NormalizedTitle",
    "RoleClassification",
    "RoleMatcher",
    "classify_title",
    "normalize_title",
    "POLICY_VERSION",
    "POLICY_VERSION_V2",
    "CandidateScore",
    "ContactNormalizer",
    "DecisionMakerSelectionResult",
    "DeterministicDecisionMakerSelectionService",
    "NormalizedContactCandidate",
    "RejectionReason",
    "RepositoryContactDeduplicator",
    "SelectionStatus",
    "SixFactorScorer",
    "select",
]
