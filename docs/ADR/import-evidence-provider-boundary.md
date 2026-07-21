# ADR: Import Evidence Provider Boundary

**Status**: Proposed · **Date**: 2026-07-21

## Context

The MVP scorer needs customs-grade data (import_activity, china_dependency,
cargo_value_potential). Multiple providers exist with different data models,
pricing, and coverage. We need a boundary that isolates provider-specific logic
from the normalization and scoring pipeline.

## Decision

Use a Provider Adapter pattern. Each provider implements:

```python
class ImportEvidenceProvider(Protocol):
    provider_name: str
    async def fetch(company: Company) -> list[RawImportRecord]
    async def fetch_by_name(name: str, country: str | None) -> list[RawImportRecord]
```

`RawImportRecord` is a canonical intermediate format — no provider-specific
fields leak past this boundary. Each adapter is responsible for mapping its
native format to `RawImportRecord`.

## Providers

| Provider | Stage | Type | Values | Coverage |
|----------|-------|------|--------|----------|
| Fake | 4A | Test | N/A | Deterministic fixtures |
| ImportYeti | 4A | HTML parse | Estimated | US ocean |
| CID (CSV) | 4B | CSV parse | Observed | Canada annual |
| Datamyne | Future | API | Observed | Global air/ocean/rail |
| PIERS | Future | API | Observed | US waterborne |

## Why ImportYeti First

1. Free tier — no commercial license needed for MVP validation
2. Company-level search with supplier breakdown — directly answers "does X import from China?"
3. Real shipment counts even if values are estimated
4. Fast iteration: HTML parsing is deterministic and testable

## Why Not USITC as Primary

USITC Dataweb provides HS-code-level trade statistics, not company-level
records. It answers "how much of HS 9403 does the US import?" not "does
Pacific Home Goods Inc. import furniture from China?" It is supplementary
for HS-code validation, not core evidence.

## Canadian CID Positioning

CID provides observed (not estimated) values for Canadian importers. It
covers companies missed by ImportYeti's US-ocean-only scope. It is a
secondary provider because:
1. Annual aggregates (not per-shipment)
2. Delayed publication
3. CSV-format requiring different parsing

## License Compliance

Before any real provider is used in production:
1. Review provider ToS for automated access
2. Check rate limits and caching requirements
3. Verify data retention and redistribution terms
4. Document in provider adapter module docstring

## Consequences

- New provider = new adapter class, no changes to pipeline
- `RawImportRecord` schema must be stable; changes require migration
- Provider-specific quirks (estimated values, missing fields) are handled in
  the adapter, not the normalization layer
