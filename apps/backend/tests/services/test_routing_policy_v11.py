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
from app.services.prospect_routing.taxonomy import fitness_equipment_v1


def _features(
    *,
    products: tuple[str, ...] = (),
    hs: tuple[str, ...] = (),
    amount: str | None = None,
    website: str | None = "acme.example",
    contacts: tuple[RoutingContactSnapshot, ...] = (),
    strong_exclusion: bool = False,
    origins: tuple[str, ...] = ("United States",),
    importer: tuple[str, ...] = ("United States",),
    unresolved: bool = False,
    last_import_at: str | None = None,
    company_name: str = "Acme Fitness",
) -> RoutingFeatureInput:
    return RoutingFeatureInput(
        company_id=uuid4(),
        company_name=company_name,
        website=website,
        profile_domain="acme.example",
        profile_address=None,
        profile_company_type="importer",
        product_descriptions=products,
        hs_codes=hs,
        shipment_dates=(),
        origin_countries=origins,
        importer_country=importer,
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


def test_us_importer_with_china_origin_is_never_non_us_target() -> None:
    # An American importer buying from China must stay routable; the shipment
    # origin must never drive the NON_US_TARGET exclusion.
    features = _features(
        products=("fitness equipment",),
        hs=("950691",),
        contacts=(_person(),),
        origins=("China",),
        importer=("United States",),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is not ProspectTier.D
    assert "NON_US_TARGET" not in result.reason_codes
    assert "TARGET_B_CANDIDATE" in result.reason_codes or (
        "TARGET_C_CANDIDATE" in result.reason_codes
    )


def test_china_origin_without_importer_country_is_not_d() -> None:
    # Unknown importer country + China shipment origin: UNKNOWN, not D.
    features = _features(
        products=("fitness equipment",),
        hs=("950691",),
        contacts=(_person(),),
        origins=("China",),
        importer=(),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is not ProspectTier.D
    assert "NON_US_TARGET" not in result.reason_codes
    assert "IMPORTER_COUNTRY_UNKNOWN" in result.warning_codes


def test_explicit_non_us_importer_is_d() -> None:
    features = _features(
        products=("fitness equipment",),
        hs=("950691",),
        contacts=(_person(),),
        importer=("Canada",),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is ProspectTier.D
    assert "NON_US_TARGET" in result.reason_codes


def test_unknown_importer_country_is_c_not_d() -> None:
    features = _features(
        products=("fitness equipment",),
        hs=("950691",),
        contacts=(_person(),),
        importer=(),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is not ProspectTier.D
    assert "IMPORTER_COUNTRY_UNKNOWN" in result.warning_codes


def test_department_mailbox_does_not_change_country_judgment() -> None:
    us_features = _features(
        products=("fitness equipment",),
        contacts=(_department(),),
        origins=("China",),
        importer=("United States",),
    )
    canada_features = _features(
        products=("fitness equipment",),
        contacts=(_department(),),
        origins=("China",),
        importer=("Canada",),
    )
    us_result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=us_features)
    canada_result = RoutingPolicyV11().evaluate(
        criteria=_criteria(), features=canada_features
    )

    assert "NON_US_TARGET" not in us_result.reason_codes
    assert us_result.recommended_tier is not ProspectTier.D
    assert canada_result.recommended_tier is ProspectTier.D
    assert "NON_US_TARGET" in canada_result.reason_codes


def test_no_target_match_is_not_d() -> None:
    # Real products that simply do not match the fitness target, with no
    # explicit other-industry evidence, must NOT be excluded to D.
    features = _features(
        products=("hydraulic pumps",),
        hs=("8413",),
        contacts=(_person(),),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is not ProspectTier.D
    assert result.recommended_tier is ProspectTier.C
    assert "TARGET_RELEVANCE_UNKNOWN" in result.warning_codes
    assert "PRODUCT_TAXONOMY_UNMATCHED" in result.warning_codes
    assert "NON_TARGET_INDUSTRY" not in result.reason_codes


def test_unknown_taxonomy_is_c_not_d() -> None:
    features = _features(
        products=("specialty hardware",),
        contacts=(_person(),),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is ProspectTier.C


def test_explicit_non_target_product_is_d() -> None:
    features = _features(
        products=("food beverage packaging",),
        contacts=(_person(),),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is ProspectTier.D
    assert "NON_TARGET_INDUSTRY" in result.reason_codes
    assert "EXPLICIT_NON_TARGET_PRODUCT" in result.reason_codes


def test_explicit_non_target_hs_is_d() -> None:
    features = _features(
        hs=("9404",),
        contacts=(_person(),),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is ProspectTier.D
    assert "NON_TARGET_INDUSTRY" in result.reason_codes
    assert "EXPLICIT_NON_TARGET_HS" in result.reason_codes


def test_missing_hs_or_product_is_not_d() -> None:
    for products, hs in ((("fitness equipment",), ()), ((), ("950691",))):
        result = RoutingPolicyV11().evaluate(
            criteria=_criteria(),
            features=_features(products=products, hs=hs, contacts=(_person(),)),
        )
        assert result.recommended_tier is not ProspectTier.D


def test_b_tier_is_not_company_name_hardcoded() -> None:
    first = RoutingPolicyV11().evaluate(
        criteria=_criteria(),
        features=_features(
            company_name="PURSUE MOVEMENT INC.",
            products=("fitness equipment",),
            hs=("950691",),
            amount="$118,000",
            contacts=(_person("logistics"),),
            last_import_at="2026-07-01",
        ),
    )
    second = RoutingPolicyV11().evaluate(
        criteria=_criteria(),
        features=_features(
            company_name="Totally Different Co.",
            products=("fitness equipment",),
            hs=("950691",),
            amount="$118,000",
            contacts=(_person("logistics"),),
            last_import_at="2026-07-01",
        ),
    )
    assert first.recommended_tier == second.recommended_tier
    assert first.pre_score == second.pre_score


def test_blocked_entity_stays_blocked() -> None:
    result = RoutingPolicyV11().evaluate(
        criteria=_criteria(),
        features=_features(products=("fitness equipment",), unresolved=True),
    )
    assert result.blocked is True
    assert result.recommended_tier is None
    assert "UNRESOLVED_COMPANY_CONFLICT_BLOCKED" in result.reason_codes


def test_taxonomy_rules_version() -> None:
    assert fitness_equipment_v1().rules_version == "fitness_equipment_v1"


def test_unknown_relevance_is_capped_at_c_even_with_high_other_signals() -> None:
    # Strong source/value/contact signals must not promote an unknown-relevance
    # company to A/B: without target match the tier is C by definition.
    features = _features(
        products=("specialty hardware",),
        amount="$1,000,000",
        contacts=(_person("logistics"), _person("executive"), _person("procurement")),
    )
    result = RoutingPolicyV11().evaluate(criteria=_criteria(), features=features)

    assert result.recommended_tier is ProspectTier.C
    assert result.pre_score >= 45
    assert "TARGET_RELEVANCE_UNKNOWN" in result.reason_codes
