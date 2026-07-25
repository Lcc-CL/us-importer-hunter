"""Deterministic importer entity resolution — no LLM, no embeddings.

Normalizes company names, domains, addresses, phones; computes match scores
from strong/composite/fuzzy evidence; assigns auto_match / needs_review /
separate status. Manual confirmations are never overwritten.
"""

import re
from dataclasses import dataclass, field

from app.domain.import_evidence.values import (
    EntityMatchMethod,
    EntityMatchStatus,
)
from app.shared.normalization import normalize_company_name

# -- thresholds (named, not magic) ---------------------------------------------

AUTO_MATCH_THRESHOLD: float = 92.0
REVIEW_THRESHOLD: float = 80.0
FUZZY_ONLY_MAX_SCORE: float = 85.0  # fuzzy-only caps below auto_match


# Roles that disqualify a record as importer evidence
NON_IMPORTER_ROLES = ("broker", "notify_party", "forwarder", "carrier", "agent")


# -- normalization ------------------------------------------------------------


def normalize_domain(raw: str) -> str:
    """Lowercase, remove www, protocol, trailing slash."""
    if not raw:
        return ""
    d = raw.lower().strip()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0]
    return d.strip().rstrip(".")


def normalize_phone(raw: str) -> str:
    """Digits only, international format collapse."""
    if not raw:
        return ""
    return re.sub(r"[^\d]", "", raw)


def normalize_address(raw: str) -> str:
    """Lowercase, collapse spaces, remove punctuation."""
    if not raw:
        return ""
    n = raw.lower().strip()
    n = re.sub(r"[.,;:\-–—]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_city(raw: str) -> str:
    return normalize_address(raw)


def normalize_state(raw: str) -> str:
    """Two-letter uppercase code."""
    if not raw:
        return ""
    n = raw.strip().upper()
    return n[:2] if len(n) >= 2 else n


def normalize_postal_code(raw: str) -> str:
    """Digits and letters only, uppercase, first 6 chars."""
    if not raw:
        return ""
    n = re.sub(r"[^\w]", "", raw).upper()
    return n[:6]


def normalize_country(raw: str) -> str:
    """Two-letter uppercase code."""
    if not raw:
        return ""
    return raw.strip().upper()[:2]


# -- matching logic -----------------------------------------------------------


@dataclass(frozen=True)
class ResolutionResult:
    """Output of entity resolution for one shipment against one candidate company."""

    match_status: EntityMatchStatus
    match_score: float
    match_method: EntityMatchMethod
    match_reasons: tuple[str, ...]
    positive_evidence: tuple[str, ...] = ()
    negative_evidence: tuple[str, ...] = ()
    resolver_version: str = "entity-resolver-v1"


class DeterministicEntityResolver:
    """Scores and classifies a shipment-to-company match."""

    def resolve(
        self,
        shipment_name: str,
        shipment_domain: str = "",
        shipment_address: str = "",
        shipment_city: str = "",
        shipment_state: str = "",
        shipment_postal: str = "",
        shipment_country: str = "",
        shipment_phone: str = "",
        shipment_role: str = "",  # importer / consignee / broker / notify_party
        *,
        candidate_name: str = "",
        candidate_domain: str = "",
        candidate_address: str = "",
        candidate_city: str = "",
        candidate_state: str = "",
        candidate_postal: str = "",
        candidate_country: str = "",
        candidate_phone: str = "",
        shipment_provider_company_id: str = "",
        candidate_provider_company_id: str = "",
        existing_match_status: EntityMatchStatus | None = None,
    ) -> ResolutionResult:
        # Manual decisions are final
        if existing_match_status in (
            EntityMatchStatus.MANUALLY_CONFIRMED,
            EntityMatchStatus.MANUALLY_REJECTED,
        ):
            return ResolutionResult(
                match_status=existing_match_status,
                match_score=(
                    100.0 if existing_match_status == EntityMatchStatus.MANUALLY_CONFIRMED else 0.0
                ),
                match_method=EntityMatchMethod.MANUAL,
                match_reasons=("manual decision preserved",),
            )

        # Disqualify non-importer roles
        if shipment_role.lower() in NON_IMPORTER_ROLES:
            return ResolutionResult(
                match_status=EntityMatchStatus.SEPARATE,
                match_score=0.0,
                match_method=EntityMatchMethod.STRONG,
                match_reasons=(f"shipment role is {shipment_role}, not importer",),
                negative_evidence=(f"role:{shipment_role}",),
            )

        evidence = _gather_evidence(
            shipment_name,
            shipment_domain,
            shipment_address,
            shipment_city,
            shipment_state,
            shipment_postal,
            shipment_country,
            shipment_phone,
            candidate_name,
            candidate_domain,
            candidate_address,
            candidate_city,
            candidate_state,
            candidate_postal,
            candidate_country,
            candidate_phone,
            shipment_provider_company_id,
            candidate_provider_company_id,
        )
        return _classify(evidence)


def _gather_evidence(  # type: ignore[no-untyped-def]
    sn,
    sd,
    sa,
    sci,
    sst,
    spc,
    sco,
    sph,
    cn,
    cd,
    ca,
    cci,
    cst,
    cpc,
    cco,
    cph,
    shipment_provider_id,
    candidate_provider_id,
) -> "_Evidence":
    e = _Evidence()

    # Strong evidence
    if (
        shipment_provider_id
        and candidate_provider_id
        and shipment_provider_id == candidate_provider_id
    ):
        e.strong.append("provider_company_id_match")
        e.score += 40.0

    norm_sd = normalize_domain(sd)
    norm_cd = normalize_domain(cd)
    if norm_sd and norm_cd and norm_sd == norm_cd:
        e.strong.append("domain_match")
        e.score += 35.0
    elif norm_sd and norm_cd:
        e.negative.append("domain_mismatch")

    norm_sph = normalize_phone(sph)
    norm_cph = normalize_phone(cph)
    if norm_sph and norm_cph and norm_sph == norm_cph:
        e.strong.append("phone_match")
        e.score += 30.0

    norm_saddr = normalize_address(sa)
    norm_caddr = normalize_address(ca)
    if norm_saddr and norm_caddr and norm_saddr == norm_caddr:
        e.strong.append("address_match")
        e.score += 30.0

    # Composite evidence: name
    norm_sn = normalize_company_name(sn)
    norm_cn = normalize_company_name(cn)
    if norm_sn and norm_cn:
        if norm_sn == norm_cn:
            e.composite.append("exact_name_match")
            e.score += 25.0
        else:
            sim = _token_set_similarity(norm_sn, norm_cn)
            if sim >= 90:
                e.composite.append(f"name_similarity:{sim:.0f}")
                e.score += 15.0
            elif sim >= 70:
                e.fuzzy.append(f"name_similarity:{sim:.0f}")
                e.score += sim * 0.1

    # City / state / postal
    norm_scity = normalize_city(sci)
    norm_ccity = normalize_city(cci)
    if norm_scity and norm_ccity and norm_scity == norm_ccity:
        e.composite.append("city_match")
        e.score += 8.0

    norm_sst = normalize_state(sst)
    norm_cst = normalize_state(cst)
    if norm_sst and norm_cst and norm_sst == norm_cst:
        e.composite.append("state_match")
        e.score += 5.0

    norm_spc = normalize_postal_code(spc)
    norm_cpc = normalize_postal_code(cpc)
    if norm_spc and norm_cpc and norm_spc == norm_cpc:
        e.composite.append("postal_match")
        e.score += 5.0

    norm_sco = normalize_country(sco)
    norm_cco = normalize_country(cco)
    if norm_sco and norm_cco:
        if norm_sco == norm_cco:
            e.composite.append("country_match")
            e.score += 3.0
        else:
            e.negative.append("country_mismatch")

    # Negative evidence: name similar but geo conflict
    if norm_sn and norm_cn and norm_sn == norm_cn:
        if norm_sst and norm_cst and norm_sst != norm_cst:
            if norm_scity and norm_ccity and norm_scity != norm_ccity:
                e.negative.append("same_name_different_geo")
                e.score -= 20.0

    return e


@dataclass
class _Evidence:
    strong: list[str] = field(default_factory=list)
    composite: list[str] = field(default_factory=list)
    fuzzy: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    score: float = 0.0


def _classify(e: _Evidence) -> ResolutionResult:
    score = max(0.0, min(e.score, 100.0))
    reasons: list[str] = []

    if e.strong:
        reasons.append(f"strong:{','.join(e.strong)}")
    if e.composite:
        reasons.append(f"composite:{','.join(e.composite)}")
    if e.fuzzy:
        reasons.append(f"fuzzy:{','.join(e.fuzzy)}")
    if e.negative:
        reasons.append(f"negative:{','.join(e.negative)}")

    has_strong = len(e.strong) > 0

    if score >= AUTO_MATCH_THRESHOLD and has_strong:
        method = EntityMatchMethod.STRONG if len(e.strong) >= 1 else EntityMatchMethod.COMPOSITE
        return ResolutionResult(
            match_status=EntityMatchStatus.AUTO_MATCH,
            match_score=score,
            match_method=method,
            match_reasons=tuple(reasons),
            positive_evidence=tuple(e.strong + e.composite),
            negative_evidence=tuple(e.negative),
        )

    if score >= REVIEW_THRESHOLD:
        return ResolutionResult(
            match_status=EntityMatchStatus.NEEDS_REVIEW,
            match_score=score,
            match_method=EntityMatchMethod.COMPOSITE if e.composite else EntityMatchMethod.FUZZY,
            match_reasons=tuple(reasons),
            positive_evidence=tuple(e.strong + e.composite),
            negative_evidence=tuple(e.negative),
        )

    return ResolutionResult(
        match_status=EntityMatchStatus.SEPARATE,
        match_score=score,
        match_method=EntityMatchMethod.FUZZY,
        match_reasons=tuple(reasons + ["score_below_threshold"]),
        positive_evidence=tuple(e.strong + e.composite),
        negative_evidence=tuple(e.negative),
    )


def _token_set_similarity(a: str, b: str) -> float:
    """Simple Jaccard-like token set similarity (no RapidFuzz dependency)."""
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) * 100.0
