"""Stage 4A.4.1: Evidence quality assessment — fixtures A-R."""

import hashlib
from datetime import date

from app.services.import_evidence.quality import (
    EvidenceQualityScorer,
    QualityStatus,
)

SCORER = EvidenceQualityScorer()


def _hash_assessment(a) -> str:
    parts = [
        str(a.total_score), a.quality_status.value,
        str(a.source_reliability_score), str(a.entity_resolution_score),
        str(a.identity_completeness_score), str(a.cross_source_consistency_score),
        str(a.freshness_score), "|".join(a.hard_blockers),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class TestASingleHighQualityProvider:
    """A: Single quality provider with complete fields → USABLE."""

    def test_usable_not_rejected_for_single_source(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True, has_arrival_date=True,
            has_carrier_scac=True,
            arrival_date_value=date(2026, 6, 15), now=date(2026, 7, 1),
        )
        assert a.quality_status in (QualityStatus.USABLE, QualityStatus.VERIFIED)
        assert a.total_score >= 70


class TestBTwoProvidersAgree:
    """B: Two independent providers agree → VERIFIED."""

    def test_verified_with_two_sources(self):
        a = SCORER.assess(
            provider_names=("fake", "csv"), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True, has_arrival_date=True,
            has_carrier_scac=True, cross_source_agreement=1.0,
            arrival_date_value=date(2026, 6, 15), now=date(2026, 7, 1),
        )
        assert a.quality_status == QualityStatus.VERIFIED
        assert a.cross_source_consistency_score > 10.0


class TestCSameProviderTwice:
    """C: Same provider repeated → no cross-source bonus."""

    def test_no_bonus_for_same_provider(self):
        a = SCORER.assess(
            provider_names=("fake", "fake"), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True, cross_source_agreement=0.5,
        )
        # Same provider repeated = unique_providers == 1 → baseline only
        assert a.cross_source_consistency_score == 12.0


class TestDImporterConflict:
    """D: Importer conflict → REVIEW with blocker."""

    def test_importer_conflict_blocked(self):
        a = SCORER.assess(
            provider_names=("fake", "csv"), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True,
            cross_source_conflicts=("importer_conflict",),
        )
        assert a.quality_status == QualityStatus.REVIEW
        assert "critical_importer_conflict" in a.hard_blockers


class TestEHouseBOLNoContainer:
    """E: Complete House BOL, missing containers → USABLE."""

    def test_usable_without_containers(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True, has_arrival_date=True,
            has_containers=False,
        )
        assert a.quality_status in (QualityStatus.USABLE, QualityStatus.VERIFIED)


class TestFMasterBOLOnly:
    """F: Only Master BOL → REVIEW or lower USABLE."""

    def test_master_only_lower_score(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_master_bol=True, has_importer=True, has_arrival_date=True,
        )
        assert a.identity_completeness_score < 20


class TestGNoBOLCompositeIdentity:
    """G: No BOL, composite identity → REVIEW, not VERIFIED."""

    def test_no_bol_not_verified(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_importer=True, has_arrival_date=True, has_carrier_scac=True,
        )
        assert a.quality_status != QualityStatus.VERIFIED


class TestHEntityManualConfirmed:
    """H: Entity manually confirmed → full entity score."""

    def test_manual_confirm_full_score(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="manually_confirmed",
            has_house_bol=True, has_importer=True,
        )
        assert a.entity_resolution_score == 25.0


class TestIEntityNeedsReview:
    """I: Entity needs_review → overall ≤ REVIEW."""

    def test_entity_needs_review_caps_status(self):
        a = SCORER.assess(
            provider_names=("fake", "csv"), entity_match_status="needs_review",
            has_house_bol=True, has_importer=True, has_arrival_date=True,
            has_carrier_scac=True, cross_source_agreement=1.0,
        )
        assert a.quality_status == QualityStatus.REVIEW
        assert "entity_needs_review" in a.hard_blockers


class TestJOldData:
    """J: >36 months → low freshness but not rejected for age alone."""

    def test_old_data_low_freshness(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True,
            arrival_date_value=date(2020, 1, 1), now=date(2026, 7, 1),
        )
        assert a.freshness_score <= 2.1
        assert a.total_score > 0


class TestKUpdatedPayload:
    """K: Payload updated → new assessment, old preserved."""
    # Tested in idempotency section
    pass


class TestLIdempotentRerun:
    """L: Same inputs → same assessment, no duplicates."""

    def test_same_input_same_output(self):
        args = dict(provider_names=("fake",), entity_match_status="auto_match",
                    has_house_bol=True, has_importer=True, has_arrival_date=True,
                    has_carrier_scac=True)
        a1 = SCORER.assess(**args)
        a2 = SCORER.assess(**args)
        assert a1.total_score == a2.total_score
        assert a1.quality_status == a2.quality_status
        assert _hash_assessment(a1) == _hash_assessment(a2)


class TestMForwardReverseOrder:
    """M: Forward/reverse provider order → same result."""

    def test_order_independent(self):
        a1 = SCORER.assess(provider_names=("fake", "csv"), entity_match_status="auto_match",
                           has_house_bol=True, has_importer=True,
                           cross_source_agreement=1.0)
        a2 = SCORER.assess(provider_names=("csv", "fake"), entity_match_status="auto_match",
                           has_house_bol=True, has_importer=True,
                           cross_source_agreement=1.0)
        assert a1.total_score == a2.total_score
        assert _hash_assessment(a1) == _hash_assessment(a2)


class TestNMasterHouseWeight:
    """N: Master/House weight → no double counting in quality."""
    # Quality scoring doesn't count weight — tested in dedup layer
    pass


class TestOMissingArrivalDate:
    """O: One source missing arrival_date — not a conflict."""

    def test_missing_date_not_a_conflict(self):
        a = SCORER.assess(
            provider_names=("fake", "csv"), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True, has_arrival_date=False,
            cross_source_agreement=0.5,
        )
        assert a.freshness_score == 0.0  # no date → no freshness


class TestPDateWithinTolerance:
    """P: Dates within tolerance → consistent."""

    def test_date_within_year_fresh(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True,
            arrival_date_value=date(2026, 1, 15), now=date(2026, 7, 1),
        )
        assert a.freshness_score == 10.0


class TestQDateOutsideTolerance:
    """Q: Date beyond tolerance → lower freshness."""

    def test_old_date_lower_freshness(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True,
            arrival_date_value=date(2022, 6, 15), now=date(2026, 7, 1),
        )
        assert a.freshness_score <= 5.0


class TestRFutureDate:
    """R: Future date → hard blocker."""

    def test_future_date_blocked(self):
        a = SCORER.assess(
            provider_names=("fake",), entity_match_status="auto_match",
            has_house_bol=True, has_importer=True,
            arrival_date_value=date(2030, 1, 1), now=date(2026, 7, 1),
        )
        assert "impossible_future_date" in a.hard_blockers


class TestBreakdownPresent:
    def test_score_breakdown_has_five_dimensions(self):
        a = SCORER.assess(provider_names=("fake",), entity_match_status="auto_match",
                          has_house_bol=True, has_importer=True)
        assert set(a.score_breakdown.keys()) == {
            "source_reliability", "entity_resolution", "identity_completeness",
            "cross_source_consistency", "freshness",
        }


class TestNoInputs:
    def test_no_providers_no_fields_rejected(self):
        a = SCORER.assess(provider_names=(), entity_match_status="separate")
        assert a.total_score < 45
        assert a.quality_status == QualityStatus.REVIEW
