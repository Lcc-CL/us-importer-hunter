"""Deterministic evidence quality scorer — five dimensions, versioned, idempotent."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

ASSESSMENT_VERSION = "import-evidence-quality-v1"


class QualityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    USABLE = "USABLE"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ProviderQualityProfile:
    provider_name: str
    base_reliability: float  # 0-20
    data_origin: str
    freshness_capable: bool = False
    identity_fields_supported: tuple[str, ...] = ()


PROVIDER_PROFILES: dict[str, ProviderQualityProfile] = {
    "fake": ProviderQualityProfile("fake", 14.0, "test_fixture"),
    "csv": ProviderQualityProfile("csv", 15.0, "file_import", identity_fields_supported=("house_bol", "importer")),
    "importyeti": ProviderQualityProfile("importyeti", 17.0, "web_platform", freshness_capable=True,
                                          identity_fields_supported=("house_bol", "master_bol", "importer", "carrier_scac", "arrival_date", "containers")),
}


@dataclass(frozen=True)
class QualityAssessment:
    id: UUID = field(default_factory=uuid4)
    shipment_id: UUID | None = None
    assessment_version: str = ASSESSMENT_VERSION
    total_score: float = 0.0
    quality_status: QualityStatus = QualityStatus.REJECTED
    source_reliability_score: float = 0.0
    entity_resolution_score: float = 0.0
    identity_completeness_score: float = 0.0
    cross_source_consistency_score: float = 0.0
    freshness_score: float = 0.0
    penalties: tuple[str, ...] = ()
    hard_blockers: tuple[str, ...] = ()
    score_breakdown: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    input_fingerprint: str = ""
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True

    def __post_init__(self) -> None:
        if not self.score_breakdown:
            bd = {
                "source_reliability": self.source_reliability_score,
                "entity_resolution": self.entity_resolution_score,
                "identity_completeness": self.identity_completeness_score,
                "cross_source_consistency": self.cross_source_consistency_score,
                "freshness": self.freshness_score,
            }
            object.__setattr__(self, "score_breakdown", bd)


class EvidenceQualityScorer:
    """Scores one NormalizedShipment's evidence quality deterministically."""

    def assess(
        self,
        *,
        provider_names: tuple[str, ...],
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
        if entity_match_status in ("separate", "manually_rejected"):
            blockers.append("unresolved_importer")
        if entity_match_status == "needs_review":
            blockers.append("entity_needs_review")

        # 3. Identity completeness (0-25)
        ic = _identity_completeness(has_house_bol, has_master_bol, has_importer,
                                     has_arrival_date, has_carrier_scac, has_containers)
        reasons.append(f"identity_completeness={ic:.0f}/25")
        if not has_house_bol and not has_master_bol and not has_importer:
            blockers.append("insufficient_identity")

        # 4. Cross-source consistency (0-20)
        cs = _cross_source_consistency(len(set(provider_names)), cross_source_agreement,
                                        cross_source_conflicts)
        reasons.append(f"cross_source_consistency={cs:.0f}/20")
        for c in cross_source_conflicts:
            if "importer" in c:
                penalties.append(f"critical_importer_conflict:-30")
                blockers.append("critical_importer_conflict")
            elif "bol" in c:
                penalties.append(f"bol_identity_conflict:-25")

        # 5. Freshness (0-10)
        fr = _freshness(arrival_date_value, now)
        reasons.append(f"freshness={fr:.0f}/10")
        if arrival_date_value and now and arrival_date_value > now:
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
        status = _quality_status(total, blockers_t)
        return QualityAssessment(
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
    house: bool, master: bool, importer: bool,
    arrival: bool, scac: bool, containers: bool,
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
    unique_providers: int, agreement: float, conflicts: tuple[str, ...],
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


def _quality_status(total: float, blockers: tuple[str, ...]) -> QualityStatus:
    if blockers:
        return QualityStatus.REVIEW
    if total >= 85:
        return QualityStatus.VERIFIED
    if total >= 70:
        return QualityStatus.USABLE
    if total >= 45:
        return QualityStatus.REVIEW
    return QualityStatus.REJECTED
