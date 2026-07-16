"""Value objects: construction validation, equality, immutability."""

import dataclasses
from datetime import UTC, datetime

import pytest

from app.domain.exceptions import (
    DomainError,
    InvalidCompanyName,
    InvalidConfidence,
    InvalidEmailAddress,
    InvalidOpportunityScore,
    InvalidWebsiteUrl,
    MissingEvidence,
)
from app.domain.values import (
    DEFAULT_SCORING_POLICY,
    CompanyName,
    Confidence,
    EmailAddress,
    Evidence,
    IdempotencyKey,
    OpportunityAssessment,
    OpportunityScore,
    Priority,
    ScoringPolicy,
    SourceReference,
    WebsiteUrl,
)
from tests.domain.conftest import make_assessment


class TestCompanyName:
    def test_valid_and_whitespace_collapsed(self) -> None:
        name = CompanyName("  Pacific   Home Goods Inc. ")
        assert name.value == "Pacific Home Goods Inc."
        assert name.normalized == "pacific home goods inc."

    @pytest.mark.parametrize("raw", ["", "   ", "\t\n", "x" * 201])
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(InvalidCompanyName):
            CompanyName(raw)

    def test_value_equality(self) -> None:
        assert CompanyName("Acme Corp") == CompanyName("Acme  Corp")
        assert CompanyName("Acme Corp") != CompanyName("Other Corp")

    def test_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            CompanyName("Acme").value = "Hacked"  # type: ignore[misc]


class TestWebsiteUrl:
    def test_valid_normalizes_host(self) -> None:
        url = WebsiteUrl("HTTPS://Example.COM/About")
        assert url.host == "example.com"
        assert url.value.startswith("https://example.com")

    @pytest.mark.parametrize("raw", ["ftp://example.com", "example.com", "https://", "https://nohost"])
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(InvalidWebsiteUrl):
            WebsiteUrl(raw)


class TestEmailAddress:
    def test_valid_lowercased(self) -> None:
        email = EmailAddress(" Maria.Chen@PacificHomeGoods.com ")
        assert email.value == "maria.chen@pacifichomegoods.com"
        assert email.domain == "pacifichomegoods.com"

    @pytest.mark.parametrize(
        "raw", ["", "not-an-email", "a@b", "a@b.", "@example.com", "a b@c.com"]
    )
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(InvalidEmailAddress):
            EmailAddress(raw)


class TestScoreAndConfidence:
    @pytest.mark.parametrize("value", [0.0, 50.5, 100.0])
    def test_valid_score(self, value: float) -> None:
        assert OpportunityScore(value).value == value

    @pytest.mark.parametrize("value", [-0.1, 100.1, 1000])
    def test_invalid_score(self, value: float) -> None:
        with pytest.raises(InvalidOpportunityScore):
            OpportunityScore(value)

    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_valid_confidence(self, value: float) -> None:
        assert Confidence(value).value == value

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_invalid_confidence(self, value: float) -> None:
        with pytest.raises(InvalidConfidence):
            Confidence(value)

    def test_score_equality(self) -> None:
        assert OpportunityScore(80.0) == OpportunityScore(80.0)


class TestScoringPolicy:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (85.0, Priority.HIGH),
            (70.0, Priority.HIGH),
            (55.0, Priority.MEDIUM),
            (10.0, Priority.LOW),
        ],
    )
    def test_default_policy_thresholds(self, score: float, expected: Priority) -> None:
        assert DEFAULT_SCORING_POLICY.priority_for(OpportunityScore(score)) is expected

    def test_custom_thresholds(self) -> None:
        strict = ScoringPolicy(version="policy-v2", high_threshold=90.0, medium_threshold=60.0)
        assert strict.priority_for(OpportunityScore(85.0)) is Priority.MEDIUM
        assert strict.priority_for(OpportunityScore(95.0)) is Priority.HIGH

    def test_requires_version(self) -> None:
        with pytest.raises(DomainError):
            ScoringPolicy(version="  ")

    @pytest.mark.parametrize(
        ("high", "medium"),
        [(40.0, 70.0), (70.0, 70.0), (101.0, 40.0), (50.0, 0.0)],
    )
    def test_invalid_thresholds(self, high: float, medium: float) -> None:
        with pytest.raises(DomainError):
            ScoringPolicy(version="v", high_threshold=high, medium_threshold=medium)


class TestSourceReference:
    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(DomainError, match="timezone-aware"):
            SourceReference(source="google", reference="url", retrieved_at=datetime(2026, 7, 1))

    @pytest.mark.parametrize(("source", "reference"), [("", "url"), ("google", " ")])
    def test_blank_fields_rejected(self, source: str, reference: str) -> None:
        with pytest.raises(DomainError):
            SourceReference(source=source, reference=reference, retrieved_at=datetime.now(UTC))


class TestEvidence:
    def test_requires_sources(self) -> None:
        with pytest.raises(MissingEvidence):
            Evidence(claim="ships a lot", sources=())

    def test_requires_claim(self, source_ref: SourceReference) -> None:
        with pytest.raises(MissingEvidence):
            Evidence(claim="  ", sources=(source_ref,))


class TestOpportunityAssessment:
    def test_valid(self, evidence: Evidence) -> None:
        assessment = make_assessment(82.0, evidence=(evidence,))
        assert assessment.new_score == OpportunityScore(82.0)
        assert assessment.assessed_at.tzinfo is not None

    def test_requires_scoring_version(self) -> None:
        with pytest.raises(DomainError, match="scoring_version"):
            make_assessment(scoring_version="  ")

    def test_requires_reasons(self) -> None:
        with pytest.raises(MissingEvidence):
            OpportunityAssessment(
                new_score=OpportunityScore(50.0),
                confidence=Confidence(0.5),
                reasons=(),
                scoring_version="scorer-v1",
            )

    def test_immutable(self) -> None:
        assessment = make_assessment()
        with pytest.raises(dataclasses.FrozenInstanceError):
            assessment.scoring_version = "tampered"  # type: ignore[misc]


class TestIdempotencyKey:
    def test_from_parts_and_equality(self) -> None:
        key = IdempotencyKey.from_parts("hunt", "user-1", "2026-07-15")
        assert key == IdempotencyKey("hunt:user-1:2026-07-15")

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(DomainError):
            IdempotencyKey(raw)

    def test_from_parts_rejects_blank_parts(self) -> None:
        with pytest.raises(DomainError):
            IdempotencyKey.from_parts("hunt", " ")
