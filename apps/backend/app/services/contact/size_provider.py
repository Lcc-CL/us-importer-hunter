"""Deterministic company size detection from signals — no LLM, no external API.

Company scale is inferred from structured signal content. Unknown / insufficient
evidence → "unknown" (not 0 — absence of data is not a penalty).
"""

from uuid import UUID

from app.services.contact.scorer import ContactSizeProvider


class DeterministicSizeProvider(ContactSizeProvider):
    """Reads company-size hints from signal strings.

    Signals are stored as "kind: detail" pairs on the Company aggregate.
    This provider scans them for employee counts, warehouse mentions and
    explicit scale markers. It never calls an LLM or external API.

    Use :meth:`populate` to register a batch of companies before scoring,
    then pass this instance to the SixFactorScorer.
    """

    def __init__(self) -> None:
        self._cache: dict[UUID, str] = {}

    def populate(self, company_id: UUID, signals: tuple[str, ...]) -> None:
        self._cache[company_id] = _infer(signals)

    def company_size_hint(self, company_id: UUID) -> str:
        return self._cache.get(company_id, "unknown")


def _infer(signals: tuple[str, ...]) -> str:
    evidence: list[str] = []
    combined = " ".join(s.lower() for s in signals)

    # Explicit size markers
    if any(w in combined for w in ("enterprise", "large enterprise", "1000+ employees",
                                     "500+ employees", "over 500 employees")):
        return "large"
    if any(w in combined for w in ("medium enterprise", "mid-size", "mid size",
                                     "50-250 employees", "100-250 employees")):
        return "medium"
    if any(w in combined for w in ("small business", "small company", "family-owned",
                                     "1-50 employees", "1-10 employees")):
        return "small"

    # Employee counts
    import re
    emp_match = re.search(r'(\d+)\s*\+?\s*employees?', combined)
    if emp_match:
        try:
            count = int(emp_match.group(1))
            if count >= 1000:
                return "large"
            if count >= 251:
                return "large"
            if count >= 51:
                return "medium"
            if count >= 11:
                return "small"
            return "micro"
        except ValueError:
            pass

    # Warehouse / facility counts as proxy
    warehouse_match = re.search(r'(\d+)\s*warehouses?', combined)
    dc_match = re.search(r'(\d+)\s*distribution\s*centers?', combined)
    facility_count = 0
    if warehouse_match:
        facility_count = max(facility_count, int(warehouse_match.group(1)))
    if dc_match:
        facility_count = max(facility_count, int(dc_match.group(1)))

    if facility_count >= 10:
        evidence.append(f"{facility_count} warehouses/dcs")
        return "large"
    if facility_count >= 3:
        evidence.append(f"{facility_count} warehouses/dcs")
        return "medium"
    if facility_count >= 1:
        evidence.append(f"{facility_count} warehouses/dcs")
        return "small"

    # Keyword-based fallback with lower confidence
    scale_signals = [s for s in signals if s.lower().startswith("company_scale")]
    if scale_signals:
        detail = " ".join(s.lower() for s in scale_signals)
        if any(w in detail for w in ("warehouse", "employees", "multi-location",
                                       "multiple locations")):
            return "medium"
        if any(w in detail for w in ("growing", "expanding", "facility")):
            return "small"

    return "unknown"
