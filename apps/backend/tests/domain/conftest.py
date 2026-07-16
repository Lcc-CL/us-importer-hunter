"""Shared builders for domain tests."""

from datetime import UTC, datetime

import pytest

from app.domain.values import (
    Confidence,
    Evidence,
    OpportunityAssessment,
    OpportunityScore,
    SourceReference,
)


@pytest.fixture
def source_ref() -> SourceReference:
    return SourceReference(
        source="importyeti",
        reference="https://example.com/bol/123",
        retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


@pytest.fixture
def evidence(source_ref: SourceReference) -> Evidence:
    return Evidence(claim="~40 FCL from CNSHA in Q2", sources=(source_ref,))


def make_assessment(
    score: float = 82.0,
    *,
    confidence: float = 0.9,
    evidence: tuple[Evidence, ...] = (),
    scoring_version: str = "scorer-v1",
) -> OpportunityAssessment:
    return OpportunityAssessment(
        new_score=OpportunityScore(score),
        confidence=Confidence(confidence),
        reasons=("high volume on CNSHA-USLAX",),
        evidence=evidence,
        scoring_version=scoring_version,
    )
