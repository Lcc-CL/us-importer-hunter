"""real-routing-v1.1: additive scoring, missing != negative, D = explicit exclusion."""

from uuid import uuid4

from app.domain.prospect_routing import (
    ProspectRoutingCriteria,
    ProspectTier,
    RoutingContactSnapshot,
    RoutingFeatureInput,
)
from app.services.prospect_routing.scorer import (
    V11_RULES_VERSION,
    RoutingPolicyV11,
)


def _features(
    *,
    products: tuple[str, ...] = (),
    hs: tuple[str, ...] = (),
    amount: str | None = None,
    website: str | None = "acme.example",
    contacts: tuple[RoutingContactSnapshot, ...] = (),
    strong_exclusion: bool = False,
    origins: tuple[str, ...] = ("United States",),
    unresolved: bool = False,
    last_import_at: str | None = None,
) -> RoutingFeatureInput:
    return RoutingFeatureInput(
        company_id=uuid4(),
        company_name="Acme Fitness",
        website=website,
        profile_domain="acme.example",
        profile_address=None,
        profile_company_type="importer",
        product_descriptions=products,
        hs_codes=hs,
        shipment_dates=(),
        origin_countries=origins,
        pols=(),
        pods=(),
        source_row_count=3,
        contacts=contacts,
        intermediary_signals=("freight forwarder",) if strong_exclusion else (),
        strong_exclusion=strong_exclusion,
        unresolved_company_conflict=unresolved,
        import_amount_raw=amount,
        last_import_at=last_import_at,
        supplier=("supplier-a",),
    )


def _criteria() -> ProspectRoutingCriteria:
    return ProspectRoutingCriteria(
        target_product_keywords=("fitness", "gym equipment"),
        target_hs_codes=("9506", "950691"),
        preferred_origin_countries=(),
        preferred_pol=(),
        preferred_pod=(),
        campaign_name=None,
        notes=None,
    )


def _person(role: str = "logistics") -> RoutingContactSnapshot:
    return RoutingContactSnapshot(
        contact_id=uuid4(),
        role_category=role,
        seniority="director",
        status="active",
        has_usable_channel=True,
        has_usable_email=True,
        is_department_contact=False,
    )


def _department() -> RoutingContactSnapshot:
    return RoutingContactSnapshot(
        contact_id=uuid4(),
        role_category="general",
        seniority="manager",
        status="active",
        has_usable_channel=True,
        has_usable_email=True,
        is_department_contact=True,
    )


def test_rules_version() -> None:
    assert V11_RULES_VERSION == "real-routing-v1.1"


def test_missing_recency_and_value_are_not_negative() -> None:
    features = _features(
        products=("fitness equipment",),
        hs=("950691",),
        contacts=(_person(),),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.blocked is False
    assert result.recommended_tier is not ProspectTier.D
    assert result.pre_score > 0
    assert "IMPORT_RECENCY_UNKNOWN" in result.warning_codes
    assert "IMPORT_VALUE_UNKNOWN" in result.warning_codes
    assert (
        "TARGET_C_CANDIDATE" in result.reason_codes
        or "TARGET_B_CANDIDATE" in result.reason_codes
    )


def test_valid_target_with_missing_recency_is_not_d() -> None:
    features = _features(
        products=("fitness equipment",),
        hs=("950691",),
        amount="$118,000",
        contacts=(_person("logistics"),),
        last_import_at="2026-07-01",
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is not ProspectTier.D
    assert result.pre_score >= 45
    assert "FITNESS_EQUIPMENT_SIGNAL" in result.reason_codes
    assert "IMPORT_VALUE_SIGNAL" in result.reason_codes


def test_explicit_intermediary_exclusion_is_d() -> None:
    features = _features(
        products=("fitness equipment",),
        strong_exclusion=True,
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is ProspectTier.D
    assert "FREIGHT_FORWARDER" in result.reason_codes


def test_department_contact_never_routes_to_d_or_decision_maker() -> None:
    features = _features(
        products=("fitness equipment",),
        hs=("950691",),
        contacts=(_department(),),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is not ProspectTier.D
    assert "DEPARTMENT_REACHABILITY_ONLY" in result.reason_codes
    assert result.preferred_role_category != "logistics"  # never a real DM


def test_preview_is_deterministic() -> None:
    features = _features(products=("fitness equipment",), hs=("950691",), contacts=(_person(),))
    first = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)
    second = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)
    assert first.pre_score == second.pre_score
    assert first.recommended_tier == second.recommended_tier
    assert first.reason_codes == second.reason_codes
