"""Scoring service: prioritization of importers as logistics opportunities.

Current implementation is the deterministic placeholder
mvp-deterministic-v1 (NOT for real sales decisions) behind the
replaceable OpportunityScoringService protocol.
"""

from app.services.scoring.deterministic import (
    SCORING_VERSION,
    DeterministicOpportunityScoringService,
    DeterministicScoringWeights,
)

__all__ = [
    "SCORING_VERSION",
    "DeterministicOpportunityScoringService",
    "DeterministicScoringWeights",
]
