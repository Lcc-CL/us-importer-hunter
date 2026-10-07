"""Explicit development provider backed by user-supplied real CSV rows."""

import csv
import io
import json
from collections.abc import Mapping

from app.domain.discovery import (
    CompanyCandidate,
    CompanyDiscoveryQuery,
    CompanyDiscoverySearchResult,
    DiscoveryProviderFailure,
)

MAX_MANUAL_CSV_BYTES = 2 * 1024 * 1024
MAX_MANUAL_CSV_ROWS = 1000


class ManualCsvValidationError(ValueError):
    """A file-level CSV error that must be rejected before a task is created."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class ManualCsvCompanyDiscoveryProvider:
    provider_name = "manual_csv"

    def __init__(self, content: bytes) -> None:
        self._rows = self._validate_and_read(content)

    @staticmethod
    def _validate_and_read(content: bytes) -> tuple[Mapping[str, str | None], ...]:
        if not content or not content.strip():
            raise ManualCsvValidationError(
                "discovery_csv_empty", "manual discovery CSV must not be empty"
            )
        if len(content) > MAX_MANUAL_CSV_BYTES:
            raise ManualCsvValidationError(
                "discovery_csv_too_large",
                f"manual discovery CSV must not exceed {MAX_MANUAL_CSV_BYTES} bytes",
            )
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ManualCsvValidationError(
                "discovery_csv_invalid_encoding", "manual discovery CSV must use UTF-8"
            ) from exc

        try:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            fieldnames = reader.fieldnames
            if not fieldnames:
                raise ManualCsvValidationError(
                    "discovery_csv_invalid_header",
                    "manual discovery CSV requires a header row",
                )
            normalized_fieldnames = [field.strip() for field in fieldnames]
            reader.fieldnames = normalized_fieldnames
            normalized_fields = set(normalized_fieldnames)
            if "company_name" not in normalized_fields or not normalized_fields.intersection(
                {"source_url", "external_id", "source_external_id"}
            ):
                raise ManualCsvValidationError(
                    "discovery_csv_invalid_header",
                    "manual discovery CSV requires company_name and source_url, "
                    "external_id, or source_external_id",
                )

            rows: list[Mapping[str, str | None]] = []
            for row_number, row in enumerate(reader, start=1):
                if row_number > MAX_MANUAL_CSV_ROWS:
                    raise ManualCsvValidationError(
                        "discovery_csv_too_many_rows",
                        f"manual discovery CSV must not exceed {MAX_MANUAL_CSV_ROWS} rows",
                    )
                rows.append(row)
        except csv.Error as exc:
            raise ManualCsvValidationError(
                "discovery_csv_malformed", f"manual discovery CSV is malformed: {exc}"
            ) from exc

        if not rows or not any(
            any(value and value.strip() for value in row.values() if isinstance(value, str))
            for row in rows
        ):
            raise ManualCsvValidationError(
                "discovery_csv_empty", "manual discovery CSV must include at least one data row"
            )
        return tuple(rows)

    async def search(self, query: CompanyDiscoveryQuery) -> CompanyDiscoverySearchResult:
        candidates: list[CompanyCandidate] = []
        failures: list[DiscoveryProviderFailure] = []
        for position, row in enumerate(self._rows, start=2):
            if len(candidates) >= query.effective_count:
                break
            name = (row.get("company_name") or "").strip()
            source_url = (row.get("source_url") or "").strip() or None
            external_id = (
                row.get("external_id") or row.get("source_external_id") or ""
            ).strip() or None
            if not name or not (source_url or external_id):
                failures.append(
                    DiscoveryProviderFailure(
                        external_id=external_id,
                        reason=f"row {position} requires company_name and source_url/external_id",
                    )
                )
                continue
            candidates.append(
                CompanyCandidate(
                    source=self.provider_name,
                    company_name=name,
                    source_url=source_url,
                    external_id=external_id,
                    website=(row.get("website") or row.get("domain") or "").strip() or None,
                    address=(row.get("address") or "").strip() or None,
                    region=(row.get("region") or "").strip() or None,
                    product_description=(row.get("product_description") or "").strip() or None,
                    import_evidence=(row.get("import_evidence") or "").strip() or None,
                    raw_metadata_json=json.dumps(row, ensure_ascii=False, sort_keys=True),
                )
            )
        return CompanyDiscoverySearchResult(
            candidates=tuple(candidates), failures=tuple(failures)
        )
