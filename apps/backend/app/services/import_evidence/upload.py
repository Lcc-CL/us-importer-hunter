"""Small-file CSV adapter for the synchronous MVP evidence workflow."""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time
from uuid import UUID

from app.domain.import_evidence.provider import CsvImportEvidenceProvider
from app.domain.import_evidence.values import NormalizedShipment, RawImportRecord, ValueType
from app.services.import_evidence.normalizer import (
    dedupe_status_for_shipment,
    normalize_arrival_date,
    normalize_bol_number,
    normalize_container_number,
    normalize_port,
    normalize_scac,
    normalize_vessel_name,
    normalize_voyage,
    normalize_weight,
)

MAX_CSV_ROWS = 5_000
MAX_CSV_BYTES = 5 * 1024 * 1024


class EvidenceCsvError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedEvidenceRow:
    raw_record: RawImportRecord
    shipment: NormalizedShipment
    importer_domain: str
    importer_country: str


@dataclass(frozen=True)
class ParsedEvidenceCsv:
    records_received: int
    rows: tuple[ParsedEvidenceRow, ...]
    warnings: tuple[str, ...] = ()


async def parse_company_csv(
    content: bytes,
    *,
    company_name: str,
    provider_name: str,
    request_id: UUID,
) -> ParsedEvidenceCsv:
    if not content:
        raise EvidenceCsvError("CSV 文件为空")
    if len(content) > MAX_CSV_BYTES:
        raise EvidenceCsvError("CSV 文件超过 5MB 上限")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceCsvError("CSV 必须使用 UTF-8 编码") from exc

    try:
        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames or "importer_name" not in reader.fieldnames:
            raise EvidenceCsvError("CSV 缺少必填列 importer_name")
        raw_rows = list(reader)
    except csv.Error as exc:
        raise EvidenceCsvError(f"CSV 格式错误：{exc}") from exc
    if len(raw_rows) > MAX_CSV_ROWS:
        raise EvidenceCsvError("CSV 超过 5000 行上限")

    fetched_at = datetime.now(UTC)
    raw_records: list[RawImportRecord] = []
    normalized_by_hash: dict[str, tuple[NormalizedShipment, str, str]] = {}
    warnings: list[str] = []
    for index, source in enumerate(raw_rows, start=2):
        row = {str(key).strip(): (value or "").strip() for key, value in source.items()}
        importer = row.get("importer_name", "")
        if not importer:
            warnings.append(f"第 {index} 行缺少 importer_name，已跳过")
            continue
        payload = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        fallback_id = hashlib.sha256(payload.encode()).hexdigest()[:20]
        raw = RawImportRecord(
            provider=provider_name,
            provider_record_id=row.get("provider_record_id") or f"csv-{fallback_id}",
            request_id=request_id,
            raw_payload_json=payload,
            fetched_at=fetched_at,
        )
        raw_records.append(raw)
        arrival = normalize_arrival_date(row.get("arrival_date"))
        arrival_at = datetime.combine(arrival, time(12, 0), tzinfo=UTC) if arrival else None
        containers = tuple(
            dict.fromkeys(
                normalized
                for item in re.split(r"[|;,]", row.get("container_numbers", ""))
                if (normalized := normalize_container_number(item))
            )
        )
        raw_weight = _float(row.get("weight"))
        weight = normalize_weight(raw_weight, row.get("weight_unit"))
        house_bol = normalize_bol_number(row.get("house_bol"))
        master_bol = normalize_bol_number(row.get("master_bol"))
        scac = normalize_scac(row.get("carrier_scac"))
        dedupe_status = dedupe_status_for_shipment(
            house_bol=house_bol,
            master_bol=master_bol,
            importer_name=importer,
            arrival_date=arrival.isoformat() if arrival else "",
            carrier_scac=scac,
        )
        declared_value = _float(row.get("declared_value_usd"))
        shipment = NormalizedShipment(
            importer_name=importer,
            importer_address=row.get("importer_address", ""),
            shipper_name=row.get("shipper_name", ""),
            shipper_country=row.get("shipper_country", "").upper()[:2],
            country_of_origin=row.get("origin_country", "").upper()[:2],
            arrival_date=arrival_at,
            port_of_lading=normalize_port(row.get("port_of_lading")),
            port_of_discharge=normalize_port(row.get("port_of_discharge")),
            master_bol=master_bol,
            house_bol=house_bol,
            carrier_scac=scac,
            vessel=normalize_vessel_name(row.get("vessel")),
            voyage=normalize_voyage(row.get("voyage")),
            container_numbers=containers,
            weight_kg=weight["normalized_kg"],
            teu=_float(row.get("teu")),
            hs_codes=tuple(
                value.strip()
                for value in re.split(r"[|;,]", row.get("hs_codes", ""))
                if value.strip()
            ),
            goods_description_raw=row.get("goods_description", ""),
            goods_description_normalized=row.get("goods_description", "").lower(),
            value_amount=declared_value,
            value_type=ValueType.OBSERVED if declared_value is not None else ValueType.UNKNOWN,
            provider=provider_name,
            provider_record_id=raw.provider_record_id,
            dedupe_status=dedupe_status.value,
            container_count=len(containers),
            raw_weight=raw_weight,
            raw_weight_unit=str(weight["raw_unit"] or ""),
            normalized_weight=weight["normalized_kg"],
            normalized_weight_unit="kg",
            weight_scope=str(weight["weight_scope"]),
            normalization_version="v1",
        )
        normalized_by_hash[raw.raw_payload_hash] = (
            shipment,
            row.get("importer_domain", ""),
            row.get("importer_country", "US"),
        )

    provider = CsvImportEvidenceProvider(provider_name=provider_name, _records=raw_records)
    company_records = await provider.fetch(UUID(int=0), company_name)
    selected = {record.raw_payload_hash for record in company_records}
    parsed = tuple(
        ParsedEvidenceRow(record, *normalized_by_hash[record.raw_payload_hash])
        for record in raw_records
        if record.raw_payload_hash in selected
    )
    if raw_records and not parsed:
        warnings.append("CSV 中没有与当前公司名称匹配的 importer 记录")
    return ParsedEvidenceCsv(len(raw_rows), parsed, tuple(warnings))


def _float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None
