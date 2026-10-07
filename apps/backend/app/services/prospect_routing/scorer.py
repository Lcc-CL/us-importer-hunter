"""Deterministic, provider-free feature projection and pre-score policy."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.domain.prospect_routing import (
    ProspectRoute,
    ProspectRoutingCriteria,
    ProspectTier,
    RoutingFeatureInput,
    RoutingSourceCompany,
)
from app.services.prospect_routing.taxonomy import (
    TargetTaxonomyConfig,
    fitness_equipment_v1,
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "product_or_hs_match": 30.0,
    "import_recency": 20.0,
    "import_frequency": 15.0,
    "origin_country_match": 10.0,
    "port_match": 10.0,
    "contact_quality": 10.0,
    "data_completeness": 5.0,
}

PREFERRED_ROLES = frozenset(
    {
        "owner_founder",
        "executive",
        "procurement",
        "supply_chain",
        "logistics",
        "operations",
        "import_export",
    }
)

ASIA_COUNTRIES = frozenset(
    {
        "china",
        "cn",
        "hong kong",
        "taiwan",
        "vietnam",
        "thailand",
        "malaysia",
        "indonesia",
        "india",
        "japan",
        "south korea",
        "korea",
        "singapore",
        "philippines",
        "中国",
        "香港",
        "台湾",
        "越南",
        "泰国",
        "马来西亚",
        "印度尼西亚",
        "印度",
        "日本",
        "韩国",
        "新加坡",
        "菲律宾",
    }
)

ROUTING_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "country": (
        "country",
        "company_country",
        "国家",
        "国家/地区",
        "地区",
        "公司国家",
    ),
    "product_description": (
        "product_description",
        "product",
        "products",
        "commodity",
        "description",
        "产品",
        "产品描述",
        "商品描述",
        "品名",
    ),
    "hs_code": ("hs_code", "hscode", "hs code", "海关编码", "hs编码"),
    "origin_country": (
        "origin_country",
        "country_of_origin",
        "supplier_country",
        "supplier",
        "来源国",
        "原产国",
        "供应商国家",
        "供应商",
    ),
    "shipment_date": (
        "shipment_date",
        "arrival_date",
        "import_date",
        "date",
        "进口日期",
        "到港日期",
        "提单日期",
    ),
    "pol": ("pol", "port_of_loading", "loading_port", "起运港", "装货港"),
    "pod": ("pod", "port_of_discharge", "destination_port", "目的港", "卸货港"),
    "company_type": ("company_type", "公司类型", "企业类型", "客户类型"),
}

_SPLIT_VALUES = re.compile(r"[;,|\n]+")
_HS_CLEAN = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True)
class RoutingScoreResult:
    pre_score: float
    recommended_tier: ProspectTier | None
    feature_snapshot: dict[str, Any]
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    blocked: bool
    contact_count: int
    has_usable_contact: bool
    has_usable_email: bool
    preferred_role_category: str | None


class RoutingFeatureProjector:
    """Project source rows into typed, deterministic scoring inputs."""

    def project(
        self,
        company: RoutingSourceCompany,
        *,
        mapping: Mapping[str, str],
    ) -> RoutingFeatureInput:
        products: list[str] = []
        hs_codes: list[str] = []
        shipment_dates: list[date] = []
        importer_countries: list[str] = []
        origins: list[str] = []
        pols: list[str] = []
        pods: list[str] = []
        company_types: list[str] = []
        suppliers: list[str] = []
        last_import_at: str | None = None
        import_amount_raw: str | None = None
        for row in company.rows:
            fields = _fields(row.raw_payload)
            products.extend(_split(_value(fields, mapping, "product_description")))
            hs_codes.extend(_split(_value(fields, mapping, "hs_code")))
            importer_countries.extend(_split(_value(fields, mapping, "country")))
            origins.extend(_split(_value(fields, mapping, "origin_country")))
            pols.extend(_split(_value(fields, mapping, "pol")))
            pods.extend(_split(_value(fields, mapping, "pod")))
            company_types.extend(_split(_value(fields, mapping, "company_type")))
            if "supplier" in mapping:
                suppliers.extend(_split(_value(fields, mapping, "supplier")))
            if last_import_at is None and "last_import_at" in mapping:
                last_import_at = _value(fields, mapping, "last_import_at") or None
            if import_amount_raw is None and "amount" in mapping:
                import_amount_raw = _value(fields, mapping, "amount") or None
            parsed_date = _parse_date(_value(fields, mapping, "shipment_date"))
            if parsed_date is not None:
                shipment_dates.append(parsed_date)

        intermediary_signals = _intermediary_signals(
            company.company_name,
            company.profile_company_type,
            tuple(company_types),
        )
        explicit_type = _explicit_intermediary_type(
            company.profile_company_type,
            tuple(company_types),
        )
        return RoutingFeatureInput(
            company_id=company.company_id,
            company_name=company.company_name,
            website=company.website,
            profile_domain=company.profile_domain,
            profile_address=company.profile_address,
            profile_company_type=company.profile_company_type,
            product_descriptions=_dedupe(products),
            hs_codes=_dedupe(hs_codes),
            shipment_dates=tuple(shipment_dates),
            origin_countries=_dedupe(origins),
            importer_country=_dedupe(importer_countries),
            pols=_dedupe(pols),
            pods=_dedupe(pods),
            source_row_count=len(company.rows),
            contacts=company.contacts,
            intermediary_signals=intermediary_signals,
            strong_exclusion=explicit_type or len(intermediary_signals) >= 2,
            unresolved_company_conflict=company.unresolved_company_conflict,
            import_amount_raw=import_amount_raw,
            last_import_at=last_import_at,
            supplier=_dedupe(suppliers),
        )


class DeterministicProspectRoutingScorer:
    """Versioned, explainable policy using only persisted facts."""

    def score(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        criteria: ProspectRoutingCriteria,
        features: RoutingFeatureInput,
        today: date | None = None,
    ) -> ProspectRoute:
        result = self.evaluate(criteria=criteria, features=features, today=today)
        return ProspectRoute.create(
            routing_run_id=routing_run_id,
            execution_generation=execution_generation,
            company_id=features.company_id,
            company_name=features.company_name,
            pre_score=result.pre_score,
            recommended_tier=result.recommended_tier,
            feature_snapshot_json=result.feature_snapshot,
            reason_codes=result.reason_codes,
            warning_codes=result.warning_codes,
            blocked=result.blocked,
            contact_count=result.contact_count,
            has_usable_contact=result.has_usable_contact,
            has_usable_email=result.has_usable_email,
            preferred_role_category=result.preferred_role_category,
        )

    def evaluate(
        self,
        *,
        criteria: ProspectRoutingCriteria,
        features: RoutingFeatureInput,
        today: date | None = None,
    ) -> RoutingScoreResult:
        evaluation_date = today or datetime.now(UTC).date()
        reasons: list[str] = []
        warnings: list[str] = []

        product_ratio = _keyword_match_ratio(
            criteria.target_product_keywords,
            features.product_descriptions,
        )
        hs_ratio = _hs_match_ratio(criteria.target_hs_codes, features.hs_codes)
        relevance_ratio = _relevance_ratio(criteria, product_ratio, hs_ratio)
        relevance_points = 30.0 * relevance_ratio
        reasons.append(_band_reason("PRODUCT_HS_MATCH", relevance_ratio))
        if criteria.target_product_keywords and not features.product_descriptions:
            warnings.append("PRODUCT_DATA_MISSING")
        if criteria.target_hs_codes and not features.hs_codes:
            warnings.append("HS_CODE_DATA_MISSING")

        recency_ratio, days_since_last = _recency_ratio(
            features.shipment_dates,
            evaluation_date,
        )
        recency_points = 20.0 * recency_ratio
        reasons.append(_band_reason("IMPORT_RECENCY", recency_ratio))
        if days_since_last is None:
            warnings.append("SHIPMENT_DATE_MISSING")

        active_months = len({(value.year, value.month) for value in features.shipment_dates})
        frequency_ratio = min(features.source_row_count / 12, 1.0) * 0.6 + min(
            active_months / 6, 1.0
        ) * 0.4
        frequency_points = 15.0 * frequency_ratio
        reasons.append(_band_reason("IMPORT_FREQUENCY", frequency_ratio))

        origin_targets = (
            frozenset(_normalize(value) for value in criteria.preferred_origin_countries)
            if criteria.preferred_origin_countries
            else ASIA_COUNTRIES
        )
        origin_ratio = _value_match_ratio(origin_targets, features.origin_countries)
        origin_points = 10.0 * origin_ratio
        reasons.append(_band_reason("ORIGIN_MATCH", origin_ratio))
        if not features.origin_countries:
            warnings.append("ORIGIN_DATA_MISSING")

        pol_ratio = _value_match_ratio(
            frozenset(_normalize(value) for value in criteria.preferred_pol),
            features.pols,
        )
        pod_ratio = _value_match_ratio(
            frozenset(_normalize(value) for value in criteria.preferred_pod),
            features.pods,
        )
        configured_port_dimensions = int(bool(criteria.preferred_pol)) + int(
            bool(criteria.preferred_pod)
        )
        port_ratio = (
            (
                pol_ratio * int(bool(criteria.preferred_pol))
                + pod_ratio * int(bool(criteria.preferred_pod))
            )
            / configured_port_dimensions
            if configured_port_dimensions
            else 0.0
        )
        port_points = 10.0 * port_ratio
        reasons.append(
            "PORT_PREFERENCE_NOT_SET"
            if not configured_port_dimensions
            else _band_reason("PORT_MATCH", port_ratio)
        )
        if configured_port_dimensions and not features.pols and not features.pods:
            warnings.append("PORT_DATA_MISSING")

        eligible_contacts = tuple(
            contact
            for contact in features.contacts
            if contact.status == "active" and contact.has_usable_channel
        )
        usable_emails = tuple(contact for contact in eligible_contacts if contact.has_usable_email)
        preferred_contacts = tuple(
            contact for contact in eligible_contacts if contact.role_category in PREFERRED_ROLES
        )
        contact_coverage_ratio = min(len(eligible_contacts) / 2, 1.0)
        preferred_role_ratio = 1.0 if preferred_contacts else 0.0
        contact_ratio = 0.4 * contact_coverage_ratio + 0.6 * preferred_role_ratio
        contact_points = 10.0 * contact_ratio
        reasons.append(_band_reason("CONTACT_COVERAGE", contact_coverage_ratio))
        reasons.append(_band_reason("PREFERRED_ROLE_CONTACT", preferred_role_ratio))
        if not eligible_contacts:
            warnings.append("USABLE_CONTACT_MISSING")
        elif not preferred_contacts:
            warnings.append("PREFERRED_ROLE_CONTACT_MISSING")
        if not usable_emails:
            warnings.append("USABLE_EMAIL_MISSING")

        completeness_flags = {
            "product_or_hs": bool(features.product_descriptions or features.hs_codes),
            "shipment_date": bool(features.shipment_dates),
            "origin": bool(features.origin_countries),
            "port": bool(features.pols or features.pods),
            "company_profile": bool(
                features.website
                or features.profile_domain
                or features.profile_address
                or features.profile_company_type
            ),
            "contact": bool(features.contacts),
        }
        completeness_ratio = sum(completeness_flags.values()) / len(completeness_flags)
        completeness_points = 5.0 * completeness_ratio
        reasons.append(_band_reason("DATA_COMPLETENESS", completeness_ratio))

        intermediary_penalty = 0.0
        if features.intermediary_signals:
            warnings.append("POSSIBLE_INTERMEDIARY")
            if not features.strong_exclusion:
                intermediary_penalty = 5.0
                reasons.append("POSSIBLE_INTERMEDIARY_WEAK_PENALTY")
        if features.strong_exclusion:
            reasons.append("STRONG_INTERMEDIARY_EXCLUSION")

        total = max(
            0.0,
            min(
                100.0,
                relevance_points
                + recency_points
                + frequency_points
                + origin_points
                + port_points
                + contact_points
                + completeness_points
                - intermediary_penalty,
            ),
        )
        pre_score = round(total, 2)
        explicit_mismatch = _explicit_mismatch(criteria, features, product_ratio, hs_ratio)
        blocked = features.unresolved_company_conflict
        recommended_tier = recommend_prospect_tier(
            pre_score=pre_score,
            has_usable_contact=bool(eligible_contacts),
            has_preferred_role_contact=bool(preferred_contacts),
            has_usable_email=bool(usable_emails),
            strong_exclusion=features.strong_exclusion,
            explicit_mismatch=explicit_mismatch,
            blocked=blocked,
        )
        if blocked:
            reasons.append("UNRESOLVED_COMPANY_CONFLICT_BLOCKED")
        elif explicit_mismatch:
            reasons.append("EXPLICIT_TARGET_MISMATCH")
        reasons.append(
            "ROUTED_BLOCKED" if recommended_tier is None else f"ROUTED_{recommended_tier.value}"
        )

        preferred_role = preferred_contacts[0].role_category if preferred_contacts else None
        snapshot: dict[str, Any] = {
            "product_match_score": round(product_ratio * 100, 2),
            "hs_code_match_score": round(hs_ratio * 100, 2),
            "product_hs_component": round(relevance_points, 2),
            "import_recency_score": round(recency_ratio * 100, 2),
            "import_recency_component": round(recency_points, 2),
            "days_since_last_import": days_since_last,
            "import_frequency_score": round(frequency_ratio * 100, 2),
            "import_frequency_component": round(frequency_points, 2),
            "source_row_count": features.source_row_count,
            "active_import_months": active_months,
            "origin_country_match_score": round(origin_ratio * 100, 2),
            "origin_country_component": round(origin_points, 2),
            "port_match_score": round(port_ratio * 100, 2),
            "port_component": round(port_points, 2),
            "contact_coverage_score": round(contact_coverage_ratio * 100, 2),
            "preferred_role_contact_score": round(preferred_role_ratio * 100, 2),
            "contact_component": round(contact_points, 2),
            "data_completeness_score": round(completeness_ratio * 100, 2),
            "data_completeness_component": round(completeness_points, 2),
            "data_completeness_flags": completeness_flags,
            "intermediary_penalty": intermediary_penalty,
            "intermediary_signals": list(features.intermediary_signals),
            "unresolved_entity_penalty": "blocked" if blocked else None,
            "observed_products": list(features.product_descriptions),
            "observed_hs_codes": list(features.hs_codes),
            "observed_origin_countries": list(features.origin_countries),
            "observed_pol": list(features.pols),
            "observed_pod": list(features.pods),
            "contact_count": len(features.contacts),
            "usable_contact_count": len(eligible_contacts),
            "usable_email_contact_count": len(usable_emails),
            "preferred_role_contact_count": len(preferred_contacts),
            "preferred_role_category": preferred_role,
            "strong_exclusion": features.strong_exclusion,
            "explicit_target_mismatch": explicit_mismatch,
            "calculation_total": pre_score,
        }
        return RoutingScoreResult(
            pre_score=pre_score,
            recommended_tier=recommended_tier,
            feature_snapshot=snapshot,
            reason_codes=tuple(dict.fromkeys(reasons)),
            warning_codes=tuple(dict.fromkeys(warnings)),
            blocked=blocked,
            contact_count=len(features.contacts),
            has_usable_contact=bool(eligible_contacts),
            has_usable_email=bool(usable_emails),
            preferred_role_category=preferred_role,
        )


def _fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("fields")
    return dict(raw) if isinstance(raw, dict) else {}


def recommend_prospect_tier(
    *,
    pre_score: float,
    has_usable_contact: bool,
    has_preferred_role_contact: bool,
    has_usable_email: bool,
    strong_exclusion: bool,
    explicit_mismatch: bool,
    blocked: bool,
) -> ProspectTier | None:
    if blocked:
        return None
    if strong_exclusion or explicit_mismatch:
        return ProspectTier.D
    if pre_score >= 75 and has_usable_contact and has_preferred_role_contact:
        return ProspectTier.A
    if pre_score >= 50 and has_usable_email:
        return ProspectTier.B
    if pre_score >= 30:
        return ProspectTier.C
    return ProspectTier.D


def _value(fields: Mapping[str, Any], mapping: Mapping[str, str], logical: str) -> str | None:
    mapped = mapping.get(logical)
    raw: object | None = fields.get(mapped) if mapped else None
    if raw is None:
        lowered = {str(key).strip().lower(): value for key, value in fields.items()}
        for alias in ROUTING_FIELD_ALIASES[logical]:
            if alias.lower() in lowered:
                raw = lowered[alias.lower()]
                break
    if raw is None:
        return None
    clean = str(raw).strip()
    return clean or None


def _split(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in _SPLIT_VALUES.split(value) if part.strip()]


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_hs(value: str) -> str:
    return _HS_CLEAN.sub("", value.casefold())


# ---------------------------------------------------------------------------
# real-routing-v1.1 — additive scoring, missing == unknown (0), D = explicit
# exclusion only. Original real-routing-v1 semantics are untouched above.
# ---------------------------------------------------------------------------

V11_RULES_VERSION = "real-routing-v1.1"
V11_WEIGHTS: dict[str, float] = {
    "importer_source_confidence": 20.0,
    "product_hs_relevance": 25.0,
    "import_value_signal": 15.0,
    "website_legitimacy": 10.0,
    "contact_coverage": 15.0,
    "person_contact_quality": 10.0,
    "data_completeness": 5.0,
}
V11_TIER_A = 70.0
V11_TIER_B = 45.0
V11_TIER_C = 20.0

_FITNESS_KEYWORDS = (
    "fitness",
    "gym",
    "exercise",
    "treadmill",
    "dumbbell",
    "elliptical",
    "weight",
    "yoga",
    "sport",
)
_FITNESS_HS_PREFIXES = ("9506", "950691", "950699")


class RoutingPolicyV11:
    """real-routing-v1.1 policy: additive, explainable, missing-safe."""

    rules_version = V11_RULES_VERSION

    def score_route(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        criteria: ProspectRoutingCriteria,
        features: RoutingFeatureInput,
        taxonomy: TargetTaxonomyConfig | None = None,
    ) -> ProspectRoute:
        """Single evaluator entry used by Routing Apply (persisted ProspectRoute).

        Identical decision to `evaluate()` (the same core RoutingPreview reads);
        this only wraps the result into a persisted route.
        """
        result = self.evaluate(
            criteria=criteria,
            features=features,
            taxonomy=taxonomy,
        )
        return ProspectRoute.create(
            routing_run_id=routing_run_id,
            execution_generation=execution_generation,
            company_id=features.company_id,
            company_name=features.company_name,
            pre_score=result.pre_score,
            recommended_tier=result.recommended_tier,
            feature_snapshot_json=result.feature_snapshot,
            reason_codes=result.reason_codes,
            warning_codes=result.warning_codes,
            blocked=result.blocked,
            contact_count=result.contact_count,
            has_usable_contact=result.has_usable_contact,
            has_usable_email=result.has_usable_email,
            preferred_role_category=result.preferred_role_category,
        )

    def evaluate(
        self,
        *,
        criteria: ProspectRoutingCriteria,
        features: RoutingFeatureInput,
        taxonomy: TargetTaxonomyConfig | None = None,
    ) -> RoutingScoreResult:
        taxonomy = taxonomy or fitness_equipment_v1()
        reasons: list[str] = []
        warnings: list[str] = []

        eligible = tuple(
            c for c in features.contacts if c.status == "active" and c.has_usable_channel
        )
        person_contacts = tuple(
            c for c in eligible if c.has_usable_email and not c.is_department_contact
        )
        department_contacts = tuple(
            c for c in eligible if c.has_usable_email and c.is_department_contact
        )
        preferred_person = tuple(
            c for c in person_contacts if c.role_category in PREFERRED_ROLES
        )
        preferred_role = (
            preferred_person[0].role_category
            if preferred_person
            else person_contacts[0].role_category
            if person_contacts
            else department_contacts[0].role_category
            if department_contacts
            else None
        )

        source_facts = [
            bool(features.product_descriptions),
            bool(features.hs_codes),
            bool(features.supplier),
            bool(features.import_amount_raw),
            bool(features.last_import_at),
            bool(features.origin_countries),
        ]
        source_ratio = sum(source_facts) / len(source_facts)
        source_points = V11_WEIGHTS["importer_source_confidence"] * source_ratio
        reasons.append(f"SOURCE_FACT_CONFIDENCE_{_band_name(source_ratio)}")
        if not features.product_descriptions:
            warnings.append("PRODUCT_DATA_MISSING")
        if not features.hs_codes:
            warnings.append("HS_CODE_DATA_MISSING")
        if not features.last_import_at:
            warnings.append("IMPORT_RECENCY_UNKNOWN")
        if not features.import_amount_raw:
            warnings.append("IMPORT_VALUE_UNKNOWN")
        if not features.importer_country:
            warnings.append("IMPORTER_COUNTRY_UNKNOWN")

        product_ratio = _keyword_match_ratio(
            criteria.target_product_keywords,
            features.product_descriptions,
        )
        hs_ratio = _hs_match_ratio(criteria.target_hs_codes, features.hs_codes)
        taxonomy_target_product = taxonomy.target_product_match(
            features.product_descriptions
        )
        taxonomy_target_hs = taxonomy.target_hs_match(features.hs_codes)
        explicit_non_target_product = taxonomy.explicit_non_target_product(
            features.product_descriptions
        )
        explicit_non_target_hs = taxonomy.explicit_non_target_hs(features.hs_codes)
        taxonomy_target = taxonomy_target_product or taxonomy_target_hs
        explicit_non_target = explicit_non_target_product or explicit_non_target_hs
        relevance_ratio = max(
            product_ratio,
            hs_ratio,
            1.0 if taxonomy_target else 0.0,
        )
        relevance_points = V11_WEIGHTS["product_hs_relevance"] * min(
            relevance_ratio, 1.0
        )
        reasons.append(_band_reason("PRODUCT_HS_MATCH", relevance_ratio))
        if taxonomy_target_product:
            reasons.append("TARGET_PRODUCT_MATCH")
        if taxonomy_target_hs:
            reasons.append("TARGET_HS_MATCH")
        fitness_signal = taxonomy_target
        if fitness_signal:
            reasons.append("FITNESS_EQUIPMENT_SIGNAL")
        if explicit_non_target_product:
            reasons.append("EXPLICIT_NON_TARGET_PRODUCT")
        if explicit_non_target_hs:
            reasons.append("EXPLICIT_NON_TARGET_HS")
        if not taxonomy_target and not explicit_non_target:
            warnings.append("TARGET_RELEVANCE_UNKNOWN")
            if features.product_descriptions:
                warnings.append("PRODUCT_TAXONOMY_UNMATCHED")
            if features.hs_codes:
                warnings.append("HS_TAXONOMY_UNMATCHED")

        value_points = self._value_points(features.import_amount_raw)
        if value_points > 0:
            reasons.append("IMPORT_VALUE_SIGNAL")

        website_points = (
            8.0 if (features.website or features.profile_domain) else 0.0
        ) + (2.0 if features.profile_company_type else 0.0)
        if website_points > 0:
            reasons.append("WEBSITE_LEGITIMACY")
        else:
            warnings.append("WEBSITE_MISSING")

        coverage_ratio = min(len(eligible) / 2, 1.0)
        coverage_points = V11_WEIGHTS["contact_coverage"] * coverage_ratio
        reasons.append(_band_reason("CONTACT_COVERAGE", coverage_ratio))
        if not eligible:
            warnings.append("USABLE_CONTACT_MISSING")

        person_quality = 0.0
        if preferred_person:
            person_quality = 10.0
            reasons.append("PERSON_CONTACT_PREFERRED_ROLE")
        elif person_contacts:
            person_quality = 5.0
            reasons.append("PERSON_CONTACT_SIGNAL")
        elif department_contacts:
            person_quality = 2.0
            reasons.append("DEPARTMENT_REACHABILITY_ONLY")
        if not person_contacts and not department_contacts:
            warnings.append("PERSON_CONTACT_MISSING")

        completeness_flags = [
            bool(features.product_descriptions or features.hs_codes),
            bool(features.origin_countries),
            bool(features.import_amount_raw),
            bool(features.supplier),
            bool(features.last_import_at),
            bool(features.website or features.profile_domain),
            bool(eligible),
        ]
        completeness_ratio = sum(completeness_flags) / len(completeness_flags)
        completeness_points = V11_WEIGHTS["data_completeness"] * completeness_ratio
        reasons.append(_band_reason("DATA_COMPLETENESS", completeness_ratio))

        pre_score = round(
            min(
                100.0,
                source_points
                + relevance_points
                + value_points
                + website_points
                + coverage_points
                + person_quality
                + completeness_points,
            ),
            2,
        )

        exclusion = self._hard_exclusion(
            features,
            criteria,
            explicit_non_target=explicit_non_target,
        )
        blocked = features.unresolved_company_conflict
        if blocked:
            reasons.append("UNRESOLVED_COMPANY_CONFLICT_BLOCKED")
        elif exclusion is not None:
            reasons.append(exclusion)
        elif not taxonomy_target:
            # No target match and no explicit non-target evidence: evidence is
            # insufficient for high-cost development -> C, never D (and never
            # promoted to A/B by unrelated signals).
            reasons.append("TARGET_RELEVANCE_UNKNOWN")
        elif pre_score >= V11_TIER_A:
            reasons.append("TARGET_A_CANDIDATE")
        elif pre_score >= V11_TIER_B:
            reasons.append("TARGET_B_CANDIDATE")
        else:
            reasons.append(
                "TARGET_C_CANDIDATE" if pre_score >= V11_TIER_C else "INFO_INSUFFICIENT"
            )

        snapshot: dict[str, Any] = {
            "rules_version": self.rules_version,
            "source_confidence": round(source_points, 2),
            "product_hs_relevance": round(relevance_points, 2),
            "import_value_signal": round(value_points, 2),
            "website_legitimacy": round(website_points, 2),
            "contact_coverage": round(coverage_points, 2),
            "person_contact_quality": round(person_quality, 2),
            "data_completeness": round(completeness_points, 2),
            "product_match_score": round(product_ratio * 100, 2),
            "hs_code_match_score": round(hs_ratio * 100, 2),
            "fitness_signal": fitness_signal,
            "importer_country": list(features.importer_country),
            "observed_origin_countries": list(features.origin_countries),
            "import_amount_raw": features.import_amount_raw,
            "last_import_at": features.last_import_at,
            "contact_count": len(features.contacts),
            "person_contact_count": len(person_contacts),
            "department_contact_count": len(department_contacts),
            "preferred_role_category": preferred_role,
            "missing_signals": tuple(warnings),
            "calculation_total": pre_score,
        }
        return RoutingScoreResult(
            pre_score=pre_score,
            recommended_tier=(
                None
                if blocked
                else ProspectTier.D
                if exclusion is not None
                else ProspectTier.C
                if not taxonomy_target
                else ProspectTier.A
                if pre_score >= V11_TIER_A
                else ProspectTier.B
                if pre_score >= V11_TIER_B
                else ProspectTier.C
            ),
            feature_snapshot=snapshot,
            reason_codes=tuple(dict.fromkeys(reasons)),
            warning_codes=tuple(dict.fromkeys(warnings)),
            blocked=blocked,
            contact_count=len(eligible),
            has_usable_contact=bool(eligible),
            has_usable_email=bool(person_contacts or department_contacts),
            preferred_role_category=preferred_role,
        )

    @staticmethod
    def _hard_exclusion(
        features: RoutingFeatureInput,
        criteria: ProspectRoutingCriteria,
        *,
        explicit_non_target: bool,
    ) -> str | None:
        if features.strong_exclusion:
            joined = " ".join(features.intermediary_signals).lower()
            if "forwarder" in joined or "货代" in joined:
                return "FREIGHT_FORWARDER"
            if "broker" in joined or "报关" in joined:
                return "CUSTOMS_BROKER"
            return "LOGISTICS_PROVIDER"
        # NON_US_TARGET is an importer-identity judgment and may only come from
        # the importer company country, never from shipment/supplier origin.
        if features.importer_country:
            normalized = {_normalize(value) for value in features.importer_country}
            if not any(
                token in normalized
                for token in ("us", "usa", "united states", "美国")
            ):
                return "NON_US_TARGET"
        if explicit_non_target:
            return "NON_TARGET_INDUSTRY"
        return None

    @staticmethod
    def _value_points(raw: str | None) -> float:
        if not raw:
            return 0.0
        digits = "".join(char for char in raw if char.isdigit() or char == ".")
        try:
            value = float(digits)
        except ValueError:
            return 0.0
        if value >= 250_000:
            return 15.0
        if value >= 50_000:
            return 10.0
        if value > 0:
            return 5.0
        return 0.0


def _band_name(ratio: float) -> str:
    if ratio >= 0.8:
        return "HIGH"
    if ratio >= 0.4:
        return "PARTIAL"
    if ratio > 0:
        return "LOW"
    return "NONE"


def _keyword_match_ratio(targets: tuple[str, ...], observations: tuple[str, ...]) -> float:
    if not targets:
        return 0.0
    haystack = " ".join(_normalize(value) for value in observations)
    matches = sum(_normalize(target) in haystack for target in targets)
    return matches / len(targets)


def _hs_match_ratio(targets: tuple[str, ...], observations: tuple[str, ...]) -> float:
    if not targets:
        return 0.0
    observed = tuple(_normalize_hs(value) for value in observations)
    matches = 0
    for target in targets:
        normalized_target = _normalize_hs(target)
        if normalized_target and any(
            value.startswith(normalized_target) or normalized_target.startswith(value)
            for value in observed
            if value
        ):
            matches += 1
    return matches / len(targets)


def _relevance_ratio(
    criteria: ProspectRoutingCriteria,
    product_ratio: float,
    hs_ratio: float,
) -> float:
    if criteria.target_product_keywords and criteria.target_hs_codes:
        return product_ratio * 0.6 + hs_ratio * 0.4
    return product_ratio if criteria.target_product_keywords else hs_ratio


def _recency_ratio(values: tuple[date, ...], today: date) -> tuple[float, int | None]:
    if not values:
        return 0.0, None
    days = max(0, (today - max(values)).days)
    if days <= 90:
        return 1.0, days
    if days <= 180:
        return 0.75, days
    if days <= 365:
        return 0.5, days
    if days <= 730:
        return 0.25, days
    return 0.0, days


def _value_match_ratio(targets: frozenset[str], observations: tuple[str, ...]) -> float:
    if not targets or not observations:
        return 0.0
    normalized_observations = tuple(_normalize(value) for value in observations)
    return 1.0 if any(
        target in observation or observation in target
        for target in targets
        for observation in normalized_observations
        if target and observation
    ) else 0.0


def _band_reason(prefix: str, ratio: float) -> str:
    if ratio >= 0.999:
        return f"{prefix}_FULL"
    if ratio > 0:
        return f"{prefix}_PARTIAL"
    return f"{prefix}_NONE"


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    candidate = value.strip()
    for format_string in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(candidate, format_string).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(candidate[:10])
    except ValueError:
        return None


def _explicit_mismatch(
    criteria: ProspectRoutingCriteria,
    features: RoutingFeatureInput,
    product_ratio: float,
    hs_ratio: float,
) -> bool:
    product_evaluable = bool(criteria.target_product_keywords and features.product_descriptions)
    hs_evaluable = bool(criteria.target_hs_codes and features.hs_codes)
    if not product_evaluable and not hs_evaluable:
        return False
    product_miss = not product_evaluable or product_ratio == 0
    hs_miss = not hs_evaluable or hs_ratio == 0
    return product_miss and hs_miss


def _intermediary_signals(
    company_name: str,
    profile_type: str | None,
    raw_types: tuple[str, ...],
) -> tuple[str, ...]:
    text = " ".join((company_name, profile_type or "", *raw_types)).casefold()
    categories = {
        "freight_forwarder": ("freight forward", "货代"),
        "customs_broker": ("customs broker", "报关"),
        "third_party_logistics": ("3pl", "third party logistics"),
        "warehouse_operator": ("warehouse", "warehousing", "仓储"),
    }
    return tuple(
        category
        for category, keywords in categories.items()
        if any(keyword in text for keyword in keywords)
    )


def _explicit_intermediary_type(profile_type: str | None, raw_types: tuple[str, ...]) -> bool:
    text = " ".join((profile_type or "", *raw_types)).casefold()
    return any(
        keyword in text
        for keyword in (
            "freight forwarder",
            "customs broker",
            "third party logistics",
            "3pl provider",
            "warehouse operator",
            "货代",
            "报关代理",
        )
    )
