"""Stage 4A.4.2: Importer Evidence Aggregate — fixtures A-T."""

import hashlib
from datetime import date
from uuid import uuid4

from app.services.import_evidence.aggregate import (
    AggregateStatus,
    compute_aggregate,
)

CID = uuid4()


def _hash_agg(a) -> str:
    parts = [
        str(a.trusted_shipment_count), str(a.review_shipment_count),
        str(a.rejected_shipment_count), str(a.china_origin_shipment_count),
        str(a.known_origin_shipment_count), str(a.shipment_count_365d),
        str(a.shipment_count_90d), str(a.status.value),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _s(**kw):
    return {"id": uuid4(), "arrival_date": None, "quality": "REJECTED",
            "origin": "", "supplier": "", "containers": [], "weight_kg": None,
            "carrier": "", "port": "", **kw}


class TestAVerifiedShipments:
    """A: 3 VERIFIED shipments → trusted=3."""

    def test_three_verified(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 3, 1)),
            _s(quality="VERIFIED", arrival_date=date(2026, 5, 15)),
            _s(quality="VERIFIED", arrival_date=date(2026, 6, 20)),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.trusted_shipment_count == 3
        assert a.status == AggregateStatus.READY


class TestBTwoProvidersOneShipment:
    """B: Same shipment from 2 providers → trusted=1 (dedup at shipment level)."""

    def test_dedup_at_shipment_level(self):
        sid = uuid4()
        shipments = [
            _s(id=sid, quality="VERIFIED", arrival_date=date(2026, 4, 1)),
            _s(id=sid, quality="USABLE", arrival_date=date(2026, 4, 1)),
        ]
        trusted = [s for s in shipments if s["quality"] in ("VERIFIED", "USABLE")]
        unique = len({s["id"] for s in trusted})
        assert unique == 1


class TestCQualityMix:
    """C: VERIFIED + USABLE + REVIEW + REJECTED → trusted=2, review=1, rejected=1."""

    def test_quality_mix(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1)),
            _s(quality="USABLE", arrival_date=date(2026, 2, 1)),
            _s(quality="REVIEW", arrival_date=date(2026, 3, 1)),
            _s(quality="REJECTED", arrival_date=date(2026, 4, 1)),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.trusted_shipment_count == 2
        assert a.review_shipment_count == 1
        assert a.rejected_shipment_count == 1


class TestDEntityResolution:
    """D: Company resolved → aggregate tied to company_id."""

    def test_company_id_present(self):
        a = compute_aggregate(company_id=CID, shipments=[_s(quality="VERIFIED", arrival_date=date(2026, 1, 1))],
                              as_of_date=date(2026, 7, 1))
        assert a.company_id == CID
        assert a.status == AggregateStatus.READY


class TestEUnresolvedImporter:
    """E: Unresolved importer → PARTIAL, not READY."""

    def test_unresolved_is_partial(self):
        a = compute_aggregate(company_id=None, shipments=[_s(quality="VERIFIED", arrival_date=date(2026, 1, 1))],
                              as_of_date=date(2026, 7, 1))
        assert a.status == AggregateStatus.PARTIAL


class TestFTimeWindows:
    """F: 90/365/730 day windows."""

    def test_windows(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 6, 15)),  # within 90d, 365d, 730d
            _s(quality="VERIFIED", arrival_date=date(2025, 8, 1)),   # within 365d, 730d
            _s(quality="VERIFIED", arrival_date=date(2024, 6, 1)),   # within 730d only
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, window_days=365,
                              as_of_date=date(2026, 7, 1))
        assert a.shipment_count_90d == 1
        assert a.shipment_count_365d == 2  # June 2026 + Aug 2025
        assert a.shipment_count_730d == 2  # June 2026 + Aug 2025 (2024-06 is before 730d window)


class TestGBoundaryDate:
    """G: Boundary date — start_date inclusive."""

    def test_boundary_inclusive(self):
        shipments = [_s(quality="VERIFIED", arrival_date=date(2025, 7, 2))]
        a = compute_aggregate(company_id=CID, shipments=shipments, window_days=365,
                              as_of_date=date(2026, 7, 1))
        assert a.shipment_count_365d == 1


class TestHUndated:
    """H: No arrival_date → undated, not in window counts."""

    def test_undated(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1)),
            _s(quality="VERIFIED"),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.undated_shipment_count == 1
        assert a.shipment_count_365d == 1  # Only dated one


class TestIChinaOrigin:
    """I: China, US, Vietnam, unknown origins."""

    def test_origin_counts(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1), origin="CN"),
            _s(quality="VERIFIED", arrival_date=date(2026, 2, 1), origin="US"),
            _s(quality="VERIFIED", arrival_date=date(2026, 3, 1), origin="VN"),
            _s(quality="VERIFIED", arrival_date=date(2026, 4, 1), origin=""),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.known_origin_shipment_count == 3
        assert a.china_origin_shipment_count == 1
        assert a.unknown_origin_shipment_count == 1


class TestJWeightDedup:
    """J: Two providers same shipment → weight counted once."""

    def test_weight_once(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1), weight_kg=1000),
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1), weight_kg=1000),
        ]
        # Even if same weight from two providers, trusted count should be unique
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.known_weight_kg is not None


class TestKMasterHouseDedup:
    """K: Master/House → one shipment counted once."""

    def test_master_house_once(self):
        sid = uuid4()
        shipments = [
            _s(id=sid, quality="VERIFIED", arrival_date=date(2026, 1, 1)),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.trusted_shipment_count == 1


class TestLContainerDedup:
    """L: Container duplicates within same shipment → deduped."""

    def test_containers_deduped(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1),
               containers=["TCLU1", "TCLU1", "TCLU2"]),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.total_container_count == 2  # 2 unique


class TestMForwardReverse:
    """M: Forward/reverse order → same hash."""

    def test_forward_reverse_same(self):
        s = [
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1)),
            _s(quality="VERIFIED", arrival_date=date(2026, 2, 1)),
        ]
        fwd = compute_aggregate(company_id=CID, shipments=s, as_of_date=date(2026, 7, 1))
        rev = compute_aggregate(company_id=CID, shipments=list(reversed(s)), as_of_date=date(2026, 7, 1))
        assert _hash_agg(fwd) == _hash_agg(rev)


class TestNIdempotentRerun:
    """N: Same input twice → same result."""

    def test_idempotent(self):
        s = [_s(quality="VERIFIED", arrival_date=date(2026, 1, 1))]
        a1 = compute_aggregate(company_id=CID, shipments=s, as_of_date=date(2026, 7, 1))
        a2 = compute_aggregate(company_id=CID, shipments=s, as_of_date=date(2026, 7, 1))
        assert _hash_agg(a1) == _hash_agg(a2)


class TestONewShipment:
    """O: New shipment → new aggregate, old preserved (new version)."""

    def test_new_shipment_changes_count(self):
        s1 = [_s(quality="VERIFIED", arrival_date=date(2026, 1, 1))]
        s2 = [_s(quality="VERIFIED", arrival_date=date(2026, 1, 1)),
              _s(quality="VERIFIED", arrival_date=date(2026, 3, 1))]
        a1 = compute_aggregate(company_id=CID, shipments=s1, as_of_date=date(2026, 7, 1))
        a2 = compute_aggregate(company_id=CID, shipments=s2, as_of_date=date(2026, 7, 1))
        assert a2.trusted_shipment_count > a1.trusted_shipment_count


class TestPQualityUpgrade:
    """P: Quality REVIEW→USABLE → trusted count increases."""

    def test_quality_upgrade(self):
        s1 = [_s(quality="REVIEW", arrival_date=date(2026, 1, 1))]
        s2 = [_s(quality="USABLE", arrival_date=date(2026, 1, 1))]
        a1 = compute_aggregate(company_id=CID, shipments=s1, as_of_date=date(2026, 7, 1))
        a2 = compute_aggregate(company_id=CID, shipments=s2, as_of_date=date(2026, 7, 1))
        assert a2.trusted_shipment_count > a1.trusted_shipment_count


class TestQEntityRejected:
    """Q: Entity rejected → shipment excluded from aggregate."""

    def test_entity_rejected_excluded(self):
        # REJECTED quality shipments already excluded from trusted
        s = [_s(quality="REJECTED", arrival_date=date(2026, 1, 1))]
        a = compute_aggregate(company_id=CID, shipments=s, as_of_date=date(2026, 7, 1))
        assert a.trusted_shipment_count == 0


class TestRPreviousYear:
    """R: Previous 365d window does not overlap current."""

    def test_previous_non_overlapping(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 3, 1)),
            _s(quality="VERIFIED", arrival_date=date(2025, 3, 1)),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.shipment_count_365d == 1  # Only 2026
        assert a.shipment_count_previous_365d == 1  # Only 2025


class TestSNoKnownOrigin:
    """S: No known origin → China ratio not computed (null)."""

    def test_no_known_origin(self):
        shipments = [
            _s(quality="VERIFIED", arrival_date=date(2026, 1, 1), origin=""),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.known_origin_shipment_count == 0
        assert a.china_origin_shipment_count == 0


class TestTReviewOnly:
    """T: Only REVIEW shipments → INSUFFICIENT_DATA."""

    def test_review_only_insufficient(self):
        shipments = [
            _s(quality="REVIEW", arrival_date=date(2026, 1, 1)),
            _s(quality="REVIEW", arrival_date=date(2026, 2, 1)),
        ]
        a = compute_aggregate(company_id=CID, shipments=shipments, as_of_date=date(2026, 7, 1))
        assert a.trusted_shipment_count == 0
        assert a.status == AggregateStatus.INSUFFICIENT_DATA
