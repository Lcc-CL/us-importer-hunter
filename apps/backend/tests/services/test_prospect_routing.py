"""D5c deterministic feature, scoring and route-review policy tests."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.domain.exceptions import InvalidStateTransition
from app.domain.prospect_routing import (
    ProspectRouteReviewStatus,
    ProspectRoutingCriteria,
    ProspectTier,
    RoutingContactSnapshot,
    RoutingFeatureInput,
    RoutingSourceCompany,
    RoutingSourceRow,
)
from app.services.prospect_routing import (
    DeterministicProspectRoutingScorer,
    RoutingFeatureProjector,
    recommend_prospect_tier,
)

TODAY = date(2026, 8, 2)


def criteria() -> ProspectRoutingCriteria:
    return ProspectRoutingCriteria(
        target_product_keywords=("hardware",),
        target_hs_codes=("8205",),
        preferred_origin_countries=("China",),
        preferred_pol=("Shanghai",),
        preferred_pod=("Los Angeles",),
        campaign_name="Hardware August",
        notes=None,
    )


def contact(
    *, role: str = "logistics", has_email: bool = True
) -> RoutingContactSnapshot:
    return RoutingContactSnapshot(
        contact_id=uuid4(),
        role_category=role,
        seniority="director",
        status="active",
        has_usable_channel=True,
        has_usable_email=has_email,
    )


def features(**overrides: object) -> RoutingFeatureInput:
    values: dict[str, object] = {
        "company_id": uuid4(),
        "company_name": "Atlas Hardware",
        "website": "https://atlas.example",
        "profile_domain": "atlas.example",
        "profile_address": "100 main st",
        "profile_company_type": "importer",
        "product_descriptions": ("industrial hardware tools",),
        "hs_codes": ("8205.40",),
        "shipment_dates": (
            date(2026, 7, 1),
            date(2026, 6, 1),
            date(2026, 5, 1),
            date(2026, 4, 1),
            date(2026, 3, 1),
            date(2026, 2, 1),
        ),
        "origin_countries": ("China",),
        "pols": ("Shanghai",),
        "pods": ("Los Angeles",),
        "source_row_count": 12,
        "contacts": (contact(),),
        "intermediary_signals": (),
        "strong_exclusion": False,
        "unresolved_company_conflict": False,
    }
    values.update(overrides)
    return RoutingFeatureInput(**values)  # type: ignore[arg-type]


def test_product_hs_recency_frequency_contact_and_snapshot_are_explainable() -> None:
    result = DeterministicProspectRoutingScorer().evaluate(
        criteria=criteria(),
        features=features(),
        today=TODAY,
    )
    assert result.recommended_tier is ProspectTier.A
    assert result.pre_score == 98
    assert result.feature_snapshot["product_match_score"] == 100
    assert result.feature_snapshot["hs_code_match_score"] == 100
    assert result.feature_snapshot["import_recency_score"] == 100
    assert result.feature_snapshot["import_frequency_score"] == 100
    assert result.feature_snapshot["preferred_role_contact_score"] == 100
    assert result.feature_snapshot["calculation_total"] == result.pre_score
    assert "PRODUCT_HS_MATCH_FULL" in result.reason_codes
    assert "ROUTED_A" in result.reason_codes


def test_possible_intermediary_weak_warning_penalizes_but_does_not_force_d() -> None:
    result = DeterministicProspectRoutingScorer().evaluate(
        criteria=criteria(),
        features=features(
            intermediary_signals=("warehouse_operator",),
            strong_exclusion=False,
        ),
        today=TODAY,
    )
    assert result.recommended_tier is ProspectTier.A
    assert result.pre_score == 93
    assert "POSSIBLE_INTERMEDIARY" in result.warning_codes
    assert result.feature_snapshot["intermediary_penalty"] == 5


def test_strong_exclusion_and_explicit_mismatch_route_to_d() -> None:
    strong = DeterministicProspectRoutingScorer().evaluate(
        criteria=criteria(),
        features=features(
            intermediary_signals=("freight_forwarder", "customs_broker"),
            strong_exclusion=True,
        ),
        today=TODAY,
    )
    mismatch = DeterministicProspectRoutingScorer().evaluate(
        criteria=criteria(),
        features=features(
            product_descriptions=("upholstered furniture",),
            hs_codes=("9401",),
        ),
        today=TODAY,
    )
    assert strong.recommended_tier is ProspectTier.D
    assert "STRONG_INTERMEDIARY_EXCLUSION" in strong.reason_codes
    assert mismatch.recommended_tier is ProspectTier.D
    assert "EXPLICIT_TARGET_MISMATCH" in mismatch.reason_codes


def test_unresolved_company_conflict_is_blocked_without_hiding_features() -> None:
    result = DeterministicProspectRoutingScorer().evaluate(
        criteria=criteria(),
        features=features(unresolved_company_conflict=True),
        today=TODAY,
    )
    assert result.blocked is True
    assert result.recommended_tier is None
    assert result.feature_snapshot["unresolved_entity_penalty"] == "blocked"
    assert "UNRESOLVED_COMPANY_CONFLICT_BLOCKED" in result.reason_codes


@pytest.mark.parametrize(
    ("score", "contact_ok", "preferred", "email", "expected"),
    [
        (75, True, True, False, ProspectTier.A),
        (74.99, True, True, True, ProspectTier.B),
        (50, True, False, True, ProspectTier.B),
        (49.99, True, False, True, ProspectTier.C),
        (30, False, False, False, ProspectTier.C),
        (29.99, True, True, True, ProspectTier.D),
    ],
)
def test_abcd_threshold_boundaries(
    score: float,
    contact_ok: bool,
    preferred: bool,
    email: bool,
    expected: ProspectTier,
) -> None:
    assert (
        recommend_prospect_tier(
            pre_score=score,
            has_usable_contact=contact_ok,
            has_preferred_role_contact=preferred,
            has_usable_email=email,
            strong_exclusion=False,
            explicit_mismatch=False,
            blocked=False,
        )
        is expected
    )


def test_raw_projector_extracts_mapped_logistics_fields_and_strong_type() -> None:
    source = RoutingSourceCompany(
        company_id=uuid4(),
        company_name="Atlas Logistics",
        website=None,
        profile_domain=None,
        profile_address=None,
        profile_company_type="freight forwarder",
        rows=(
            RoutingSourceRow(
                import_entity_decision_id=uuid4(),
                raw_import_row_id=uuid4(),
                row_number=2,
                raw_payload={
                    "fields": {
                        "产品": "Hardware; Power tools",
                        "编码": "8205.40",
                        "日期": "2026-07-15",
                        "来源": "China",
                        "起运": "Shanghai",
                        "目的": "Los Angeles",
                    }
                },
                created_at=datetime(2026, 8, 1, tzinfo=UTC),
            ),
        ),
        contacts=(),
        unresolved_company_conflict=False,
    )
    projected = RoutingFeatureProjector().project(
        source,
        mapping={
            "product_description": "产品",
            "hs_code": "编码",
            "shipment_date": "日期",
            "origin_country": "来源",
            "pol": "起运",
            "pod": "目的",
        },
    )
    assert projected.product_descriptions == ("Hardware", "Power tools")
    assert projected.hs_codes == ("8205.40",)
    assert projected.shipment_dates == (date(2026, 7, 15),)
    assert projected.strong_exclusion is True


def test_route_review_confirm_override_exclude_and_conflicts_are_idempotent() -> None:
    scorer = DeterministicProspectRoutingScorer()
    route = scorer.score(
        routing_run_id=uuid4(),
        execution_generation=1,
        criteria=criteria(),
        features=features(),
        today=TODAY,
    )
    confirmed = route.confirm(reviewed_by="reviewer")
    assert confirmed.review_status is ProspectRouteReviewStatus.CONFIRMED
    assert confirmed.confirm(reviewed_by="reviewer") is confirmed
    with pytest.raises(InvalidStateTransition):
        confirmed.confirm(reviewed_by="different-reviewer")
    with pytest.raises(InvalidStateTransition):
        confirmed.override(
            effective_tier=ProspectTier.B,
            override_reason="different judgment",
            reviewed_by="reviewer",
        )

    overridden = route.override(
        effective_tier=ProspectTier.B,
        override_reason="smaller account",
        reviewed_by="reviewer",
    )
    assert overridden.review_status is ProspectRouteReviewStatus.OVERRIDDEN
    assert overridden.effective_tier is ProspectTier.B
    assert (
        overridden.override(
            effective_tier=ProspectTier.B,
            override_reason="smaller account",
            reviewed_by="reviewer",
        )
        is overridden
    )
    with pytest.raises(InvalidStateTransition):
        overridden.override(
            effective_tier=ProspectTier.B,
            override_reason="smaller account",
            reviewed_by="different-reviewer",
        )

    excluded = route.override(
        effective_tier=ProspectTier.D,
        override_reason="human exclusion",
        reviewed_by="reviewer",
    )
    assert excluded.effective_tier is ProspectTier.D
