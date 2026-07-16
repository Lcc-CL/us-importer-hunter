"""Contact services: normalization, deduplication, decision-maker policy."""

from app.services.contact.decision_maker import (
    POLICY_VERSION,
    DecisionMakerWeights,
    DeterministicDecisionMakerSelectionService,
)
from app.services.contact.deduplicator import RepositoryContactDeduplicator
from app.services.contact.normalizer import ContactNormalizer, NormalizedContactCandidate

__all__ = [
    "POLICY_VERSION",
    "ContactNormalizer",
    "DecisionMakerWeights",
    "DeterministicDecisionMakerSelectionService",
    "NormalizedContactCandidate",
    "RepositoryContactDeduplicator",
]
