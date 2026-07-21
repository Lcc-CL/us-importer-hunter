"""Deterministic evidence quality scorer — five dimensions, versioned, idempotent."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.domain.import_evidence.models import (
    QualityAssessment,
    QualityStatus,
    stable_fingerprint,
)

ASSESSMENT_VERSION = "import-evidence-quality-v1"

__all__ = [
    "ASSESSMENT_VERSION",
    "EvidenceQualityScorer",
    "ProviderQualityProfile",
    "QualityAssessment",
    "QualityStatus",
]


@dataclass(frozen=True)
class ProviderQualityProfile:
    provider_name: str
    base_reliability: float  # 0-20
    data_origin: str
    freshness_capable: bool = False
    identity_fields_supported: tuple[str, ...] = ()


PROVIDER_PROFILES: dict[str, ProviderQualityProfile] = {
    "fake": ProviderQualityProfile("fake", 14.0, "test_fixture"),
    "csv": ProviderQualityProfile(
        "csv", 15.0, "file_import", identity_fields_supported=("house_bol", "importer")
    ),
    "importyeti": ProviderQualityProfile(
        "importyeti",
        17.0,
        "web_platform",
        freshness_capable=True,
        identity_fields_supported=(
            "house_bol",
            "master_bol",
            "importer",
            "carrier_scac",
            "arrival_date",
            "containers",
        ),
    ),
}


class EvidenceQualityScorer:
    """Scores one NormalizedShipment's evidence quality deterministically."""

    def assess(
        self,
        *,
        provider_names: tuple[str, ...],
        normalized_shipment_id: UUID | None = None,
        shipment_fingerprint: str = "",
        entity_match_status: str = "needs_review",
        has_house_bol: bool = False,
        has_master_bol: bool = False,
        has_importer: bool = False,
        has_arrival_date: bool = False,
        has_carrier_scac: bool = False,
        has_containers: bool = False,
        cross_source_agreement: float = 0.5,
        cross_source_conflicts: tuple[str, ...] = (),
        arrival_date_value: date | None = None,
        now: date | None = None,
        assessed_at: datetime | None = None,
    ) -> QualityAssessment:
        reasons: list[str] = []
        penalties: list[str] = []
        blockers: list[str] = []

        # 1. Source reliability (0-20)
        sr = _source_reliability(provider_names)
        reasons.append(f"source_reliability={sr:.0f}/20")

        # 2. Entity resolution (0-25)
        er = _entity_resolution_score(entity_match_status)
        reasons.append(f"entity_resolution={er:.0f}/25")
        status_caps: list[str] = []
        if entity_match_status in ("separate", "manually_rejected"):
            blockers.append("unresolved_importer")
        if entity_match_status == "needs_review":
            status_caps.append("entity_needs_review")

        # 3. Identity completeness (0-25)
        ic = _identity_completeness(
            has_house_bol,
            has_master_bol,
            has_importer,
            has_arrival_date,
            has_carrier_scac,
            has_containers,
        )
        reasons.append(f"identity_completeness={ic:.0f}/25")
        if not has_house_bol and not has_master_bol and not has_importer:
            blockers.append("insufficient_identity")

        # 4. Cross-source consistency (0-20)
        cs = _cross_source_consistency(
            len(set(provider_names)), cross_source_agreement, cross_source_conflicts
        )
        reasons.append(f"cross_source_consistency={cs:.0f}/20")
        for c in cross_source_conflicts:
            if "importer" in c:
                penalties.append("critical_importer_conflict:-30")
                blockers.append("critical_importer_conflict")
            elif "bol" in c:
                penalties.append("bol_identity_conflict:-25")

        # 5. Freshness (0-10)
        reference_date = now or date.today()
        fr = _freshness(arrival_date_value, reference_date)
        reasons.append(f"freshness={fr:.0f}/10")
        if arrival_date_value and arrival_date_value > reference_date:
            blockers.append("impossible_future_date")

        penalty_total = 0.0
        for p in penalties:
            if ":-30" in p:
                penalty_total -= 30
            elif ":-25" in p:
                penalty_total -= 25
            elif ":-20" in p:
                penalty_total -= 20
            elif ":-15" in p:
                penalty_total -= 15
            elif ":-10" in p:
                penalty_total -= 10
            elif ":-5" in p:
                penalty_total -= 5

        total = max(0.0, min(sr + er + ic + cs + fr + penalty_total, 100.0))
        blockers_t = tuple(blockers)
        caps_t = tuple(status_caps)
        status = _quality_status(total, blockers_t, caps_t)
        assessed = assessed_at or datetime.now(UTC)
        fingerprint = stable_fingerprint(
            {
                "assessment_version": ASSESSMENT_VERSION,
                "shipment_fingerprint": shipment_fingerprint or "__MISSING__",
                "source_provider_count": len(set(provider_names)),
                "status": status.value,
                "scores": {
                    "total": total,
                    "source_reliability": sr,
                    "entity_resolution": er,
                    "identity_completeness": ic,
                    "cross_source_consistency": cs,
                    "freshness": fr,
                },
                "hard_blockers": sorted(blockers_t),
                "penalties": sorted(penalties),
                "reference_date": reference_date.isoformat(),
            }
        )
        return QualityAssessment(
            normalized_shipment_id=normalized_shipment_id,
            assessment_version=ASSESSMENT_VERSION,
            total_score=total,
            quality_status=status,
            source_reliability_score=sr,
            entity_resolution_score=er,
            identity_completeness_score=ic,
            cross_source_consistency_score=cs,
            freshness_score=fr,
            penalties=tuple(penalties),
            hard_blockers=blockers_t,
            reasons=tuple(reasons),
            input_fingerprint=fingerprint,
            assessed_at=assessed,
            created_at=assessed,
        )


def _source_reliability(provider_names: tuple[str, ...]) -> float:
    if not provider_names:
        return 0.0
    unique = set(provider_names)
    scores: list[float] = []
    for p in unique:
        pp = PROVIDER_PROFILES.get(p)
        if pp is not None:
            scores.append(pp.base_reliability)
    if not scores:
        return 5.0
    # Best provider + multi-source bonus (max +2 for 2+ independent sources)
    base = max(scores)
    bonus = min(len(unique) - 1, 2) * 2 if len(unique) >= 2 else 0
    return min(base + bonus, 20.0)


def _entity_resolution_score(status: str) -> float:
    mapping = {
        "manually_confirmed": 25.0,
        "auto_match": 22.0,
        "needs_review": 12.0,
        "separate": 0.0,
        "manually_rejected": 0.0,
    }
    return mapping.get(status, 5.0)


def _identity_completeness(
    house: bool,
    master: bool,
    importer: bool,
    arrival: bool,
    scac: bool,
    containers: bool,
) -> float:
    score = 0.0
    if house:
        score += 10.0
    elif master:
        score += 6.0
    if importer:
        score += 8.0
    if arrival:
        score += 4.0
    if scac:
        score += 2.0
    if containers:
        score += 1.0
    return min(score, 25.0)


def _cross_source_consistency(
    unique_providers: int,
    agreement: float,
    conflicts: tuple[str, ...],
) -> float:
    if unique_providers <= 1:
        return 12.0  # neutral — one source isn't "wrong"
    if conflicts:
        critical = sum(1 for c in conflicts if "importer" in c or "bol" in c)
        return max(0.0, 15.0 - critical * 7.0)
    # Two+ providers agree → significant bonus
    bonus = min((unique_providers - 1) * 3, 8)
    return 12.0 + bonus


def _freshness(arrival: date | None, now: date | None) -> float:
    if arrival is None:
        return 0.0
    ref = now or date.today()
    months = (ref.year - arrival.year) * 12 + (ref.month - arrival.month)
    if months <= 12:
        return 10.0
    if months <= 24:
        return 8.0
    if months <= 36:
        return 5.0
    return 2.0


def _quality_status(
    total: float, blockers: tuple[str, ...], caps: tuple[str, ...] = ()
) -> QualityStatus:
    if "impossible_future_date" in blockers:
        return QualityStatus.REJECTED
    if blockers:
        return QualityStatus.REVIEW
    if total >= 85 and "entity_needs_review" not in caps:
        return QualityStatus.VERIFIED
    if total >= 70 and "entity_needs_review" not in caps:
        return QualityStatus.USABLE
    if total >= 70:
        return QualityStatus.REVIEW  # capped by entity_needs_review
    if total >= 45:
        return QualityStatus.REVIEW
    return QualityStatus.REJECTED
