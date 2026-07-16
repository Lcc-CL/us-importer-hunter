"""Scoring service: prioritization of importers as logistics opportunities.

Current implementation is the explainable deterministic placeholder
mvp-explainable-scoring-v1 (NOT for real sales decisions) behind the
replaceable OpportunityScoringService protocol.
"""

from app.services.scoring.deterministic import (
    SCORING_VERSION,
    DeterministicConfidenceWeights,
    DeterministicOpportunityScoringService,
)

__all__ = [
    "SCORING_VERSION",
    "DeterministicConfidenceWeights",
    "DeterministicOpportunityScoringService",
]
