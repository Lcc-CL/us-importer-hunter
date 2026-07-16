# ADR-0019: Claim → Company ingestion at the application layer

Date: 2026-07-16 · Status: Accepted

## Context

ADR-0018 established that Discovery produces claims and events, never
companies. Someone has to consume `CompanyDiscovered` and turn claims
into canonical companies — without breaking the boundary in either
direction.

## Decision

A dedicated application workflow, `CompanyIngestionWorkflow`
(`app/workflows/company_ingestion/`), is the only place Discovery output
meets the Company aggregate:

```
CompanyDiscovered (claim)
  → SnapshotNormalizer      raw text → CompanyName / WebsiteUrl
                            (no scheme → https://; invalid website →
                             dropped with a note; unusable name →
                             claim REJECTED, nothing persisted)
  → RepositoryCompanyDeduplicator   1) exact normalized-name match
                                    2) same website host
  → not found → Company.create + sources + signals   (CREATED)
    found     → merge into the canonical aggregate    (MERGED)
  → one UnitOfWork per event, explicit commit
```

### Merge policy (idempotent by design)

- Different spelling → `add_alias` (`DuplicateOperation` swallowed —
  reprocessing the same claim changes nothing).
- Website: fill when missing, no-op when identical; a *conflicting*
  website is refused by the new domain behavior `Company.set_website`
  and recorded as a note — resolution policy is deliberately pending.
- Source provenance appended unless the exact (source, reference) pair
  is already recorded.
- Signals appended as `"kind: detail"` text.

### Why an application workflow, not a domain service or Discovery code

Discovery cannot do it (it must not know Company — enforced by test).
The Company aggregate cannot do it (it would need repository access).
A domain service could decide *duplicate-or-not* (it does:
`CompanyDeduplicationService`), but the orchestration — normalize,
look up, choose create-vs-merge, commit — is a use case, and use cases
live in the application layer with one transaction each (ADR-0017).

### Why rejection is an outcome, not an exception

Ingestion is batch-shaped: one bad claim among fifty must not abort the
other forty-nine. The workflow returns a typed `IngestionOutcome`
(created / merged / rejected + notes) so callers aggregate results;
exceptions stay for programming errors, not data quality.

## Consequences

- No event bus yet: callers invoke `handle(event)` directly; bus wiring
  (ADR-0004) will subscribe this workflow unchanged.
- Evidence on claims is not persisted yet (no home until ImportRecord
  lands); only provenance (SourceReference) reaches the company.
- New repository lookup `find_by_website_host` joins the protocol;
  dedup remains name-first, host-second — fuzzy matching is a later,
  evidence-driven upgrade.
