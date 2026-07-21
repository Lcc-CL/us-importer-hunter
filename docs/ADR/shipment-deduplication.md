# ADR: Shipment Deduplication

**Status**: Proposed · **Date**: 2026-07-21

## Context

A single shipment may appear in multiple provider records, multiple BOL
rows, or multiple provider fetches. Counting it multiple times inflates
import volume and misleads the scorer. We need deterministic deduplication.

## Decision

Two-tier dedup: primary key first, fingerprint fallback.

### Primary Key
`provider + provider_record_id`

When a provider assigns stable IDs, this is sufficient and efficient.

### Fallback Fingerprint
SHA-256 of canonicalized concatenation:
`provider|master_bol|house_bol|carrier_scac|arrival_date|vessel|voyage|normalized_importer|normalized_shipper|sorted_container_numbers|origin_port|destination_port`

### Master/House BOL Rules

1. **House BOL = commercial shipment**. This is the level at which an
   importer took possession of goods. One House BOL = one shipment for
   counting purposes.

2. **Master BOL = parent transport record**. Multiple House BOLs may
   share one Master. These are separate shipments and must not be merged.

3. **Same House, multiple container rows** → one shipment. Container-level
   detail rows under the same House BOL are one shipment. Container numbers
   are collected into the `container_numbers` array.

4. **Weight accumulation**: when aggregating across Master/House,
   House-level weight is authoritative for the commercial shipment.
   Master-level weight may include freight from other importers.

5. **Parent-child relationship preserved** in `master_bol` reference field.

## Anti-Patterns

- ❌ Merging House BOLs under the same Master
- ❌ Counting container rows as separate shipments
- ❌ Summing Master-level weights as company import volume
- ❌ LLM-based deduplication

## Consequences

- Shipment counts are conservative (undercount preferred to overcount)
- Container-level detail preserved for audit without inflating counts
- Fingerprint is deterministic and reproducible across runs
- Provider changes to record IDs do not cause duplicate shipments
  (fingerprint catches them)
