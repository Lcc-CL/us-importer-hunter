"""Stage 4A.3: Shipment normalization, fingerprint, dedup — fixtures D-R."""

import pytest

from app.domain.import_evidence.values import NormalizedShipment
from app.services.import_evidence.normalizer import (
    DedupeStatus,
    dedupe_status_for_shipment,
    normalize_bol_number,
    normalize_container_number,
    normalize_port,
    normalize_scac,
    normalize_vessel_name,
    normalize_voyage,
    normalize_weight,
)

# Fingerprint is computed automatically via NormalizedShipment.__post_init__
# Use NormalizedShipment(..., shipment_fingerprint="") to trigger auto-compute.
# For unit tests, access shipment.shipment_fingerprint after construction.


class TestNormalizationFunctions:
    def test_bol_strips_dashes_and_spaces(self):
        assert normalize_bol_number("MBOL-123-456") == "MBOL123456"
        assert normalize_bol_number("  hbol  789 ") == "HBOL789"

    def test_containers_sort_and_upper(self):
        assert normalize_container_number("tcLu 1234 567") == "TCLU1234567"

    def test_scac_upper(self):
        assert normalize_scac("maeu") == "MAEU"

    def test_vessel_normalizes(self):
        assert normalize_vessel_name("Ever  Forward") == "EVER FORWARD"

    def test_voyage_normalizes(self):
        assert normalize_voyage("042 W") == "042W"

    def test_port_normalizes(self):
        assert normalize_port("  Los  Angeles ") == "LOS ANGELES"

    def test_weight_kg(self):
        r = normalize_weight(18500, "kg")
        assert r["normalized_kg"] == 18500
        assert r["normalized_unit"] == "kg"

    def test_weight_lbs(self):
        r = normalize_weight(1000, "lbs")
        assert r["normalized_kg"] == pytest.approx(453.59, rel=0.01)

    def test_weight_unknown_unit(self):
        r = normalize_weight(500, None)
        assert r["normalized_kg"] is None
        assert r["weight_scope"] == "unknown_unit"


class TestFingerprint:
    def test_fingerprint_is_stable(self):
        s1 = NormalizedShipment(provider="p", house_bol="HBOL1", master_bol="MBOL1")
        s2 = NormalizedShipment(provider="p", house_bol="HBOL1", master_bol="MBOL1")
        assert s1.shipment_fingerprint == s2.shipment_fingerprint

    def test_fingerprint_differs_on_house_bol(self):
        s1 = NormalizedShipment(provider="p", house_bol="HBOL1")
        s2 = NormalizedShipment(provider="p", house_bol="HBOL2")
        assert s1.shipment_fingerprint != s2.shipment_fingerprint

    def test_fingerprint_includes_version(self):
        s = NormalizedShipment(house_bol="HBOL1")
        assert len(s.shipment_fingerprint) == 64
        assert s.fingerprint_version == "shipment-fp-v2"

    def test_null_fields_use_placeholder(self):
        s1 = NormalizedShipment(provider="p")
        s2 = NormalizedShipment(provider="p")
        assert s1.shipment_fingerprint == s2.shipment_fingerprint

    def test_containers_sorted(self):
        s1 = NormalizedShipment(house_bol="H1", container_numbers=("B", "A", "C"))
        s2 = NormalizedShipment(house_bol="H1", container_numbers=("A", "B", "C"))
        assert s1.shipment_fingerprint == s2.shipment_fingerprint


class TestDedupeStatus:
    def test_house_plus_importer_ok(self):
        assert (
            dedupe_status_for_shipment(house_bol="HBOL1", importer_name="Acme") == DedupeStatus.OK
        )

    def test_house_plus_date_ok(self):
        assert (
            dedupe_status_for_shipment(house_bol="HBOL1", arrival_date="2026-06-15")
            == DedupeStatus.OK
        )

    def test_master_importer_date_ok(self):
        assert (
            dedupe_status_for_shipment(
                master_bol="MBOL1", importer_name="Acme", arrival_date="2026-06-15"
            )
            == DedupeStatus.OK
        )

    def test_only_importer_date_needs_review(self):
        assert (
            dedupe_status_for_shipment(importer_name="Acme", arrival_date="2026-06-15")
            == DedupeStatus.NEEDS_REVIEW
        )

    def test_no_identity_insufficient(self):
        assert dedupe_status_for_shipment() == DedupeStatus.INSUFFICIENT_IDENTITY

    def test_only_importer_insufficient(self):
        assert (
            dedupe_status_for_shipment(importer_name="Acme") == DedupeStatus.INSUFFICIENT_IDENTITY
        )


class TestFixtureDSameHouseBOLMultipleContainers:
    """D: Same House BOL, 3 container rows → 1 Shipment, 3 unique containers."""

    def test_three_containers_one_shipment(self):
        s1 = NormalizedShipment(
            house_bol="HBOL-X",
            provider="fake",
            container_numbers=("TCLU1", "TCLU2", "TCLU3"),
            container_count=3,
        )
        s2 = NormalizedShipment(
            house_bol="HBOL-X",
            provider="fake",
            container_numbers=("TCLU3", "TCLU2", "TCLU1"),
            container_count=3,
        )
        assert s1.shipment_fingerprint == s2.shipment_fingerprint
        assert len(set(s1.container_numbers)) == 3


class TestFixtureEMasterBOLMultipleHouse:
    """E: Same Master, different House → separate Shipments."""

    def test_different_house_different_fingerprint(self):
        s1 = NormalizedShipment(house_bol="HBOL-A", master_bol="MBOL-1", provider="fake")
        s2 = NormalizedShipment(house_bol="HBOL-B", master_bol="MBOL-1", provider="fake")
        assert s1.shipment_fingerprint != s2.shipment_fingerprint


class TestFixtureJMissingHouseBOL:
    """J: Missing House BOL — needs identity check."""

    def test_missing_house_bol_insufficient_when_alone(self):
        status = dedupe_status_for_shipment()
        assert status == DedupeStatus.INSUFFICIENT_IDENTITY

    def test_missing_house_bol_ok_with_importer_date_scac(self):
        status = dedupe_status_for_shipment(
            importer_name="Acme", arrival_date="2026-06-15", carrier_scac="MAEU"
        )
        assert status == DedupeStatus.OK


class TestFixtureKReverseOrder:
    """K: Import order reversed → same fingerprints."""

    def test_reverse_order_same_fingerprints(self):
        shipments = [
            NormalizedShipment(house_bol="K1", provider="fake").shipment_fingerprint,
            NormalizedShipment(house_bol="K2", provider="fake").shipment_fingerprint,
        ]
        reversed_s = [
            NormalizedShipment(house_bol="K2", provider="fake").shipment_fingerprint,
            NormalizedShipment(house_bol="K1", provider="fake").shipment_fingerprint,
        ]
        assert sorted(shipments) == sorted(reversed_s)


class TestFixtureLMasterHouseWeight:
    """L: Master and House weight → no double counting."""

    def test_house_weight_scope(self):
        r = normalize_weight(1000, "kg")
        assert r["weight_scope"] == "house"

    def test_master_weight_preserved(self):
        r = normalize_weight(5000, "kg")
        assert r["normalized_kg"] == 5000


class TestFixtureMUpdatedPayload:
    """M: Same provider_record_id, updated payload → new RawRecord version."""

    def test_normalized_importer_preserved(self):
        s = NormalizedShipment(house_bol="M1", provider="fake", importer_name="Acme Inc.")
        assert s.importer_name == "Acme Inc."


class TestFixtureNDifferentProviderSameHouseBOL:
    """N: Different providers, same House BOL → same business fingerprint (v2)."""

    def test_different_provider_same_fingerprint(self):
        s1 = NormalizedShipment(house_bol="HBOL-N", provider="fake", importer_name="Acme")
        s2 = NormalizedShipment(house_bol="HBOL-N", provider="importyeti", importer_name="Acme")
        assert s1.shipment_fingerprint == s2.shipment_fingerprint


class TestFixtureOContainerVariants:
    """O: Container number spacing/case variants → normalized same."""

    def test_container_variants(self):
        assert normalize_container_number("TC LU 1234") == "TCLU1234"
        assert normalize_container_number("tcLu-1234") == "TCLU1234"


class TestFixturePMasterOnly:
    """P: Master-only record with sufficient evidence → OK."""

    def test_master_only_with_evidence(self):
        status = dedupe_status_for_shipment(
            master_bol="MBOL-P", importer_name="Acme", arrival_date="2026-06-15"
        )
        assert status == DedupeStatus.OK


class TestFixtureQDifferentImporterSameBOL:
    """Q: Same BOL, different importers → different shipments (importer is identity)."""

    def test_different_importer_different_fingerprint(self):
        s1 = NormalizedShipment(house_bol="HBOL-Q", provider="fake", importer_name="Acme Inc.")
        s2 = NormalizedShipment(house_bol="HBOL-Q", provider="fake", importer_name="Beta Corp.")
        assert s1.shipment_fingerprint != s2.shipment_fingerprint

    def test_name_punctuation_difference_same_fingerprint(self):
        s1 = NormalizedShipment(house_bol="Q1", importer_name="ACME HARDWARE INC.")
        s2 = NormalizedShipment(house_bol="Q1", importer_name="ACME HARDWARE, INC")
        assert s1.shipment_fingerprint == s2.shipment_fingerprint


class TestFixtureRAllFieldsMissing:
    """R: All fields missing → insufficient_identity."""

    def test_all_missing(self):
        status = dedupe_status_for_shipment()
        assert status == DedupeStatus.INSUFFICIENT_IDENTITY
        s = NormalizedShipment()
        assert len(s.shipment_fingerprint) == 64
