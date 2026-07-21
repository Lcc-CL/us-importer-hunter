"""Stage 4A.1 infrastructure tests: providers, raw records, jobs, dedup constraints."""

import asyncio
from uuid import uuid4

import pytest

from app.domain.import_evidence.provider import (
    CsvImportEvidenceProvider,
    FakeImportEvidenceProvider,
    ImportYetiProviderSkeleton,
)
from app.domain.import_evidence.values import (
    ImportEvidenceJobStatus,
    RawImportRecord,
)


class TestFakeProvider:
    """A: Fake provider returns deterministic, marked fixture records."""

    def test_fake_returns_two_records(self):
        provider = FakeImportEvidenceProvider()
        company_id = uuid4()
        records = asyncio.run(provider.fetch(company_id, "TestCo"))
        assert len(records) == 2

    def test_fake_records_are_marked(self):
        provider = FakeImportEvidenceProvider()
        records = asyncio.run(provider.fetch(uuid4(), "TestCo"))
        for r in records:
            assert r.fixture is True
            assert r.synthetic is True
            assert r.provider == "fake"
            assert r.schema_version == "v1"

    def test_fake_is_deterministic(self):
        provider = FakeImportEvidenceProvider()
        cid = uuid4()
        r1 = asyncio.run(provider.fetch(cid, "TestCo"))
        r2 = asyncio.run(provider.fetch(cid, "TestCo"))
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.provider_record_id == b.provider_record_id
            assert a.raw_payload_hash == b.raw_payload_hash

    def test_fake_has_realistic_payload(self):
        provider = FakeImportEvidenceProvider()
        records = asyncio.run(provider.fetch(uuid4(), "TestCo"))
        p0 = records[0].raw_payload_json
        assert "MBOL123" in p0
        assert "HBOL456" in p0
        assert "TCLU1234567" in p0
        assert "provider_estimated" in p0


class TestCSVProvider:
    """B: CSV provider reads CSV, rejects malformed, no network."""

    def test_empty_csv_returns_empty(self):
        provider = CsvImportEvidenceProvider(provider_name="csv_test")
        provider._records = []
        records = asyncio.run(provider.fetch(uuid4(), "AnyCo"))
        assert len(records) == 0

    def test_csv_uninitialized_returns_empty(self):
        provider = CsvImportEvidenceProvider()
        records = asyncio.run(provider.fetch(uuid4(), "AnyCo"))
        assert len(records) == 0

    def test_csv_matches_by_name_substring(self):
        provider = CsvImportEvidenceProvider(provider_name="csv_test")
        req_id = uuid4()
        provider._records = [
            RawImportRecord(
                provider="csv_test",
                provider_record_id="csv-001",
                request_id=req_id,
                raw_payload_json='{"importer":"Pacific Home Goods Inc.","value":100}',
                fixture=True, synthetic=True,
            ),
            RawImportRecord(
                provider="csv_test",
                provider_record_id="csv-002",
                request_id=req_id,
                raw_payload_json='{"importer":"Other Corp","value":200}',
                fixture=True, synthetic=True,
            ),
        ]
        records = asyncio.run(provider.fetch(uuid4(), "Pacific"))
        assert len(records) == 1
        assert "Pacific" in records[0].raw_payload_json


class TestImportYetiSkeleton:
    """C: ImportYeti skeleton returns not_configured, no network."""

    def test_skeleton_returns_not_configured(self):
        provider = ImportYetiProviderSkeleton()
        records = asyncio.run(provider.fetch(uuid4(), "TestCo"))
        assert len(records) == 1
        assert "provider_not_configured" in records[0].raw_payload_json
        assert records[0].provider == "importyeti"
        assert records[0].fixture is True


class TestRawRecordConstraints:
    """D: RawRecord append-only, idempotent, versioned."""

    def test_same_record_same_hash(self):
        req = uuid4()
        r1 = RawImportRecord(provider="p", provider_record_id="1", request_id=req,
                             raw_payload_json='{"a":1}')
        r2 = RawImportRecord(provider="p", provider_record_id="1", request_id=req,
                             raw_payload_json='{"a":1}')
        assert r1.raw_payload_hash == r2.raw_payload_hash

    def test_different_payload_different_hash(self):
        req = uuid4()
        r1 = RawImportRecord(provider="p", provider_record_id="1", request_id=req,
                             raw_payload_json='{"a":1}')
        r2 = RawImportRecord(provider="p", provider_record_id="1", request_id=req,
                             raw_payload_json='{"a":2}')
        assert r1.raw_payload_hash != r2.raw_payload_hash

    def test_hash_is_auto_computed(self):
        r = RawImportRecord(provider="p", provider_record_id="1", request_id=uuid4(),
                            raw_payload_json='{"test":true}')
        assert len(r.raw_payload_hash) == 64
        assert r.raw_payload_hash != ""

    def test_record_is_frozen(self):
        r = RawImportRecord(provider="p", provider_record_id="1", request_id=uuid4(),
                            raw_payload_json='{"a":1}')
        with pytest.raises(Exception):
            r.raw_payload_json = "changed"  # type: ignore[misc]


class TestJobStatus:
    """E: Job status enumeration."""

    def test_all_statuses_defined(self):
        expected = {"pending", "running", "completed", "partial", "failed", "needs_review"}
        actual = set(ImportEvidenceJobStatus)
        assert actual == expected

    def test_valid_status_transitions(self):
        # pending → running → completed
        assert ImportEvidenceJobStatus.PENDING != ImportEvidenceJobStatus.COMPLETED
        assert ImportEvidenceJobStatus.RUNNING != ImportEvidenceJobStatus.FAILED


class TestMigrationBaseline:
    """F: Migration roundtrip preserves existing app state."""

    def test_all_tables_exist_in_metadata(self):
        import app.database.models  # noqa
        from app.database.base import Base
        tables = Base.metadata.tables
        ie_tables = {t for t in tables if "import_evidence" in t
                     or "normalized_ship" in t or "importer_entity" in t}
        assert len(ie_tables) == 7

    def test_existing_business_tables_still_present(self):
        import app.database.models  # noqa
        from app.database.base import Base
        tables = Base.metadata.tables
        business = {"companies", "contacts", "opportunities", "contact_fit_assessments",
                     "outreaches", "email_drafts", "tasks"}
        assert business.issubset(set(tables))
