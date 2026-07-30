"""Explicit development provider backed by user-supplied real CSV rows."""

import csv
import io
import json

from app.domain.discovery import (
    CompanyCandidate,
    CompanyDiscoveryQuery,
    CompanyDiscoverySearchResult,
    DiscoveryProviderFailure,
)


class ManualCsvCompanyDiscoveryProvider:
    provider_name = "manual_csv"

    def __init__(self, content: bytes) -> None:
        self._content = content

    async def search(self, query: CompanyDiscoveryQuery) -> CompanyDiscoverySearchResult:
        try:
            text = self._content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("manual discovery CSV must use UTF-8") from exc

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "company_name" not in reader.fieldnames:
            raise ValueError("manual discovery CSV requires company_name")

        candidates: list[CompanyCandidate] = []
        failures: list[DiscoveryProviderFailure] = []
        for position, row in enumerate(reader, start=2):
            if len(candidates) >= query.effective_count:
                break
            name = (row.get("company_name") or "").strip()
            source_url = (row.get("source_url") or "").strip() or None
            external_id = (row.get("external_id") or "").strip() or None
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
