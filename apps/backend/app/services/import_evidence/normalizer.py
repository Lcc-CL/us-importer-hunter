"""Shipment normalization functions — deterministic, versioned, testable."""

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class DedupeStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_IDENTITY = "insufficient_identity"
    NEEDS_REVIEW = "needs_review"
    DUPLICATE = "duplicate"


def normalize_bol_number(raw: str | None) -> str:
    if not raw:
        return ""
    n = raw.upper().strip()
    n = re.sub(r"[-\s]+", "", n)
    return n


def normalize_container_number(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"[-\s]+", "", raw).upper()


def normalize_scac(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().upper()[:4]


def normalize_vessel_name(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw.strip().upper())


def normalize_voyage(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", "", raw.strip().upper())


def normalize_port(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw.strip().upper())


def normalize_arrival_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def normalize_weight(raw_value: float | None, raw_unit: str | None) -> dict[str, Any]:
    if raw_value is None:
        return {"raw_value": None, "raw_unit": raw_unit, "normalized_kg": None,
                "normalized_unit": "kg", "weight_scope": "unknown"}
    unit = (raw_unit or "").lower().strip()
    scope = "house" if unit else "unknown"
    if unit in ("kg", "kgs", "kilogram", "kilograms"):
        return {"raw_value": raw_value, "raw_unit": unit, "normalized_kg": raw_value,
                "normalized_unit": "kg", "weight_scope": scope}
    if unit in ("lb", "lbs", "pound", "pounds"):
        return {"raw_value": raw_value, "raw_unit": unit, "normalized_kg": round(raw_value * 0.453592, 2),
                "normalized_unit": "kg", "weight_scope": scope}
    if unit in ("t", "ton", "tons", "mt", "metric ton"):
        return {"raw_value": raw_value, "raw_unit": unit, "normalized_kg": raw_value * 1000,
                "normalized_unit": "kg", "weight_scope": scope}
    if raw_value > 0 and not unit:
        return {"raw_value": raw_value, "raw_unit": None, "normalized_kg": None,
                "normalized_unit": "kg", "weight_scope": "unknown_unit"}
    return {"raw_value": raw_value, "raw_unit": unit, "normalized_kg": None,
            "normalized_unit": "kg", "weight_scope": "unknown_unit"}


def dedupe_status_for_shipment(
    *,
    house_bol: str = "",
    master_bol: str = "",
    importer_name: str = "",
    arrival_date: str = "",
    carrier_scac: str = "",
) -> DedupeStatus:
    """Check if the shipment has enough identity to be deduped."""
    n_house = normalize_bol_number(house_bol)
    n_importer = importer_name.strip()
    has_house = bool(n_house)
    has_importer = bool(n_importer)
    has_date = bool(arrival_date)
    has_scac = bool(normalize_scac(carrier_scac))
    n_master = normalize_bol_number(master_bol)

    if has_house and has_importer:
        return DedupeStatus.OK
    if has_house and has_date:
        return DedupeStatus.OK
    if n_master and has_importer and has_date:
        return DedupeStatus.OK
    if has_importer and has_date and has_scac:
        return DedupeStatus.OK
    if has_importer and has_date:
        return DedupeStatus.NEEDS_REVIEW
    return DedupeStatus.INSUFFICIENT_IDENTITY
