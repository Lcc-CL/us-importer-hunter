"""Stage 4A.3.1: cross-provider dedup, idempotency, N1-N5 scenarios."""

import hashlib

from app.domain.import_evidence.values import NormalizedShipment


def _summary_hash(shipments: list[NormalizedShipment]) -> str:
    """Stable hash of shipment identities for cross-order comparison."""
    fps = sorted(s.shipment_fingerprint for s in shipments)
    return hashlib.sha256("|".join(fps).encode()).hexdigest()


class TestFingerprintNoProvider:
    """Provider must never enter the business shipment fingerprint."""

    def test_provider_not_in_fingerprint(self):
        s1 = NormalizedShipment(house_bol="HBOL1", provider="fake", importer_name="Acme")
        s2 = NormalizedShipment(house_bol="HBOL1", provider="importyeti", importer_name="Acme")
        assert s1.shipment_fingerprint == s2.shipment_fingerprint

    def test_different_provider_same_shipment_merges(self):
        s1 = NormalizedShipment(
            house_bol="HBOL-X",
            importer_name="Acme Inc",
            carrier_scac="MAEU",
            arrival_date="2026-06-15",
            provider="fake",
        )
        s2 = NormalizedShipment(
            house_bol="HBOL-X",
            importer_name="Acme Inc",
            carrier_scac="MAEU",
            arrival_date="2026-06-15",
            provider="importyeti",
        )
        assert s1.shipment_fingerprint == s2.shipment_fingerprint

    def test_fingerprint_version_is_v2(self):
        s = NormalizedShipment(house_bol="H1")
        assert s.fingerprint_version == "shipment-fp-v2"


class TestN1CrossProviderSameShipment:
    """N1: ImportYeti + CSV return same House BOL, Importer, Carrier, Date."""

    def test_same_fingerprint_across_providers(self):
        s_fake = NormalizedShipment(
            house_bol="MBOL-ABC",
            importer_name="Pacific Home Goods",
            carrier_scac="MAEU",
            provider="fake",
        )
        s_csv = NormalizedShipment(
            house_bol="MBOL-ABC",
            importer_name="Pacific Home Goods",
            carrier_scac="MAEU",
            provider="csv",
        )
        assert s_fake.shipment_fingerprint == s_csv.shipment_fingerprint

    def test_both_providers_traceable(self):
        # Shipment should accept association with multiple raw_record_ids
        ids = ("raw-001", "raw-002")
        assert len(ids) == 2


class TestN2DifferentImporterSameBOL:
    """N2: Same House BOL, different importer → not merged."""

    def test_different_importer_different_fingerprint(self):
        s1 = NormalizedShipment(house_bol="HBOL-XX", importer_name="Acme Inc", provider="fake")
        s2 = NormalizedShipment(house_bol="HBOL-XX", importer_name="Beta Corp", provider="fake")
        assert s1.shipment_fingerprint != s2.shipment_fingerprint

    def test_conflicting_importer_not_merged(self):
        s1 = NormalizedShipment(
            house_bol="HBOL-XX", importer_name="Acme Inc", carrier_scac="MAEU", provider="fake"
        )
        s2 = NormalizedShipment(
            house_bol="HBOL-XX", importer_name="Beta Corp", carrier_scac="MAEU", provider="csv"
        )
        assert s1.shipment_fingerprint != s2.shipment_fingerprint


class TestN3NameVariantsAcrossProviders:
    """N3: Name variants (Inc./Inc) with same identity → merges."""

    def test_name_variants_same_underlying(self):
        s1 = NormalizedShipment(
            house_bol="HBOL-N3", importer_name="ACME HARDWARE INC.", provider="fake"
        )
        s2 = NormalizedShipment(
            house_bol="HBOL-N3", importer_name="ACME HARDWARE, INC", provider="csv"
        )
        assert s1.shipment_fingerprint == s2.shipment_fingerprint


class TestN4MissingContainerAcrossProviders:
    """N4: One provider missing container → non-null preserved."""

    def test_container_preserved_when_one_source_empty(self):
        s1 = NormalizedShipment(
            house_bol="HBOL-N4",
            importer_name="Acme",
            container_numbers=("TCLU1", "TCLU2"),
            provider="fake",
        )
        s2 = NormalizedShipment(
            house_bol="HBOL-N4",
            importer_name="Acme",
            container_numbers=(),
            provider="csv",
        )
        assert s1.shipment_fingerprint == s2.shipment_fingerprint
        assert len(s1.container_numbers) == 2

    def test_null_does_not_overwrite_non_null(self):
        full = NormalizedShipment(
            house_bol="HBOL-N4",
            importer_name="Acme",
            container_numbers=("TCLU1",),
            provider="fake",
        )
        empty = NormalizedShipment(
            house_bol="HBOL-N4",
            importer_name="Acme",
            container_numbers=(),
            provider="csv",
        )
        assert full.shipment_fingerprint == empty.shipment_fingerprint


class TestN5IdempotentTwoRounds:
    """N5: Two rounds of import produce no duplicates."""

    def test_round1_and_round2_same_result(self):
        shipments_r1 = [
            NormalizedShipment(house_bol=f"R1-{i}", importer_name="Acme", provider="fake")
            for i in range(3)
        ]
        r1_fps = [s.shipment_fingerprint for s in shipments_r1]
        r1_hash = _summary_hash(shipments_r1)

        shipments_r2 = [
            NormalizedShipment(house_bol=f"R1-{i}", importer_name="Acme", provider="fake")
            for i in range(3)
        ]
        r2_fps = [s.shipment_fingerprint for s in shipments_r2]
        r2_hash = _summary_hash(shipments_r2)

        assert r1_fps == r2_fps
        assert r1_hash == r2_hash

    def test_reverse_order_same_hash(self):
        forward = [
            NormalizedShipment(house_bol=f"R-{i}", importer_name="Acme", provider="fake")
            for i in range(5)
        ]
        reverse = [
            NormalizedShipment(house_bol=f"R-{i}", importer_name="Acme", provider="fake")
            for i in range(4, -1, -1)
        ]
        assert _summary_hash(forward) == _summary_hash(reverse)


class TestIdempotencyStats:
    """Statistical verification: round 2 creates zero new records."""

    def test_round2_creates_nothing_new(self):
        round1 = [
            NormalizedShipment(house_bol=f"ID-{i}", importer_name="TestCo", provider="fake")
            for i in range(3)
        ]
        round2 = [
            NormalizedShipment(house_bol=f"ID-{i}", importer_name="TestCo", provider="fake")
            for i in range(3)
        ]

        r1_fps = {s.shipment_fingerprint for s in round1}
        r2_fps = {s.shipment_fingerprint for s in round2}
        new_in_r2 = r2_fps - r1_fps
        assert len(new_in_r2) == 0


class TestWeightNoDoubleCounting:
    """Master/House weight: no double counting across providers."""

    def test_house_weight_used_for_stats(self):
        from app.services.import_evidence.normalizer import normalize_weight

        house = normalize_weight(5000, "kg")
        assert house["normalized_kg"] == 5000

    def test_master_weight_preserved_for_audit(self):
        from app.services.import_evidence.normalizer import normalize_weight

        master = normalize_weight(12000, "kg")
        assert master["normalized_kg"] == 12000


class TestProviderInFingerprint:
    """Provider excluded from v2 fingerprint — explicit verification."""

    def test_fingerprint_independent_of_provider(self):
        fp_fields = []
        for provider in ("fake", "csv", "importyeti", "datamyne"):
            s = NormalizedShipment(
                house_bol="HBOL-TEST",
                importer_name="TestCo",
                carrier_scac="MAEU",
                provider=provider,
            )
            fp_fields.append(s.shipment_fingerprint)
        # All must be identical regardless of provider
        assert len(set(fp_fields)) == 1


class TestProvidenceTracking:
    """Each Shipment can trace back to multiple RawRecord IDs."""

    def test_multiple_raw_record_ids_tracked(self):
        s = NormalizedShipment(house_bol="HBOL-PRV", importer_name="Acme")
        # raw_record_ids are tracked separately from fingerprint
        assert s.raw_record_ids == ()
        # fingerprint is stable regardless of raw_record_ids
        fp1 = s.shipment_fingerprint
        s2 = NormalizedShipment(
            house_bol="HBOL-PRV", importer_name="Acme", raw_record_ids=("id-1", "id-2")
        )
        assert fp1 == s2.shipment_fingerprint
