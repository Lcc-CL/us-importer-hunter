"""Versioned deterministic target taxonomy for routing relevance.

No ML, no LLM. The taxonomy distinguishes:

- TARGET_MATCH: a real source fact clearly supports the target industry;
- EXPLICIT_NON_TARGET: a real source fact clearly proves another industry;
- TARGET_RELEVANCE_UNKNOWN: no match and no explicit counter-evidence.

"No match" is NEVER treated as explicit non-target evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_SPLIT = re.compile(r"[\s,;/|()\[\]_-]+")


@dataclass(frozen=True)
class TargetTaxonomyConfig:
    rules_version: str
    target_keywords: tuple[str, ...]
    target_aliases: tuple[str, ...]
    target_hs_prefixes: tuple[str, ...]
    explicit_non_target_keywords: tuple[str, ...]
    explicit_non_target_hs_prefixes: tuple[str, ...]

    def target_product_match(self, products: tuple[str, ...]) -> bool:
        normalized = [_normalize_tokens(value) for value in products]
        for value in normalized:
            for keyword in self._target_product_terms():
                if keyword in value:
                    return True
        return False

    def target_hs_match(self, hs_codes: tuple[str, ...]) -> bool:
        cleaned = [_normalize_hs(value) for value in hs_codes]
        return any(
            code.startswith(prefix)
            for code in cleaned
            for prefix in self.target_hs_prefixes
        )

    def explicit_non_target_product(self, products: tuple[str, ...]) -> bool:
        normalized = [_normalize_tokens(value) for value in products]
        return any(
            keyword in value
            for value in normalized
            for keyword in self.explicit_non_target_keywords
        )

    def explicit_non_target_hs(self, hs_codes: tuple[str, ...]) -> bool:
        cleaned = [_normalize_hs(value) for value in hs_codes]
        return any(
            code.startswith(prefix)
            for code in cleaned
            for prefix in self.explicit_non_target_hs_prefixes
        )

    def _target_product_terms(self) -> tuple[str, ...]:
        return self.target_keywords + self.target_aliases


def fitness_equipment_v1() -> TargetTaxonomyConfig:
    """fitness_equipment_v1: deterministic, manually curated, explainable."""
    return TargetTaxonomyConfig(
        rules_version="fitness_equipment_v1",
        target_keywords=(
            "fitness",
            "gym",
            "exercise",
            "treadmill",
            "dumbbell",
            "elliptical",
            "workout",
            "strength",
            "cardio",
            "yoga",
            "sport",
            "athlete",
            "weightlifting",
            "barbell",
            "kettlebell",
            "rowing",
            "stationary bike",
            "exercise bike",
            "home gym",
        ),
        target_aliases=(
            "健身",
            "运动",
            "器材",
            "跑步机",
            "哑铃",
            "瑜伽",
            "训练",
        ),
        target_hs_prefixes=(
            "9506",
            "950691",
            "950699",
        ),
        explicit_non_target_keywords=(
            # High-confidence, other-industry product facts (conservative list).
            "meat",
            "dairy",
            "bakery",
            "beverage",
            "coffee",
            "produce",
            "food",
            "pet food",
            "apparel",
            "clothing",
            "bedding",
            "fabric",
            "textile",
            "furniture",
            "sofa",
            "mattress",
            "concrete",
            "cement",
            "lumber",
            "tire",
            "brake",
            "pesticide",
            "fertilizer",
            "corrugated",
            "carton",
            "packaging",
            "solar panel",
            "semiconductor",
            "药品",
            "食品",
            "服装",
            "家具",
            "建材",
        ),
        explicit_non_target_hs_prefixes=(
            # Furniture, bedding, lamps.
            "9401",
            "9403",
            "9404",
            "9405",
            # Apparel.
            "6101",
            "6104",
            "6201",
            "6204",
            # Food / meat / dairy.
            "0201",
            "0401",
            "1601",
            "1905",
            # Auto parts.
            "8708",
            # Pesticides / fertilizers.
            "3808",
            "3102",
            # Corrugated / paper packaging.
            "4819",
        ),
    )


def _normalize_tokens(value: str) -> str:
    return value.strip().casefold()


def _normalize_hs(value: str) -> str:
    return re.sub(r"[^0-9a-z]", "", value.casefold())
