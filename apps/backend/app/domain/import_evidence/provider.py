"""Import evidence provider protocol and implementations."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.domain.import_evidence.values import RawImportRecord


class ImportEvidenceProvider(Protocol):
    """Fetches raw import records for a company by name and optional country."""

    @property
    def provider_name(self) -> str: ...

    async def fetch(
        self, company_id: UUID, name: str, country: str | None = None
    ) -> Sequence[RawImportRecord]: ...


@dataclass
class FakeImportEvidenceProvider:
    """Returns deterministic fixture records. Never touches the network."""

    provider_name: str = "fake"

    async def fetch(
        self, company_id: UUID, name: str, country: str | None = None
    ) -> Sequence[RawImportRecord]:
        request_id = uuid4()
        now = datetime.now(timezone.utc)
        return (
            RawImportRecord(
                provider=self.provider_name,
                provider_record_id=f"fake-{name}-001",
                request_id=request_id,
                raw_payload_json=(
                    '{"importer":"' + name + '","shipper":"Shenzhen Factory Co.",'
                    '"origin_country":"CN","destination_country":"US",'
                    '"master_bol":"MBOL123","house_bol":"HBOL456",'
                    '"weight_kg":18500,"teu":2,"hs_codes":["9403.50"],'
                    '"goods_description":"Wooden furniture","value_usd":45000,'
                    '"value_type":"provider_estimated","arrival_date":"2026-06-15",'
                    '"carrier_scac":"MAEU","vessel":"Ever Forward","voyage":"042W",'
                    '"port_of_lading":"Yantian","port_of_discharge":"Los Angeles",'
                    '"container_numbers":["TCLU1234567","TCLU1234568"],'
                    '"fixture":true,"synthetic":true}'
                ),
                fetched_at=now,
                fixture=True,
                synthetic=True,
            ),
            RawImportRecord(
                provider=self.provider_name,
                provider_record_id=f"fake-{name}-002",
                request_id=request_id,
                raw_payload_json=(
                    '{"importer":"' + name + '","shipper":"Guangzhou Trading Ltd.",'
                    '"origin_country":"CN","destination_country":"US",'
                    '"master_bol":"MBOL789","house_bol":"HBOL012",'
                    '"weight_kg":12000,"teu":1,"hs_codes":["9401.80"],'
                    '"goods_description":"Office chairs","value_usd":null,'
                    '"value_type":"unknown","arrival_date":"2026-05-01",'
                    '"carrier_scac":"COSU","vessel":"CSCL Star","voyage":"018E",'
                    '"port_of_lading":"Shanghai","port_of_discharge":"Long Beach",'
                    '"container_numbers":["COSU9876543"],'
                    '"fixture":true,"synthetic":true}'
                ),
                fetched_at=now,
                fixture=True,
                synthetic=True,
            ),
        )


@dataclass
class CsvImportEvidenceProvider:
    """Reads import records from a CSV file. Production: CID data dumps."""

    provider_name: str = "csv"
    _records: list[RawImportRecord] | None = None

    async def fetch(
        self, company_id: UUID, name: str, country: str | None = None
    ) -> Sequence[RawImportRecord]:
        if self._records is None:
            return ()
        return tuple(r for r in self._records if name.lower() in r.raw_payload_json.lower())


@dataclass
class ImportYetiProviderSkeleton:
    """Skeleton: returns provider_not_configured. Real adapter in stage 4B."""

    provider_name: str = "importyeti"

    async def fetch(
        self, company_id: UUID, name: str, country: str | None = None
    ) -> Sequence[RawImportRecord]:
        return (
            RawImportRecord(
                provider=self.provider_name,
                provider_record_id=f"unconfigured-{name}",
                request_id=uuid4(),
                raw_payload_json='{"error":"provider_not_configured"}',
                fixture=True,
                synthetic=True,
            ),
        )
