# Workflows

Workflows (`app/workflows/`) orchestrate multi-step pipelines across
agents and services. They own sequencing, fan-out and error recovery —
they contain no low-level I/O and no prompt content.

## Service vs Workflow boundary

- **Service** — deterministic business logic: CRUD, data assembly,
  external API calls, scoring rules. Single-purpose, no LLM chains.
- **Workflow** — orchestrates a multi-step AI process by calling agents
  and services, e.g. "search companies → analyze each → rank → draft emails".

> Status: this is the working definition; flagged for confirmation with
> the product owner. (Workflows are *not* Celery task chains; when Celery
> lands, tasks will invoke workflows, not replace them.)

## Planned MVP workflow (not yet implemented)

```
lead_generation (each run wrapped in a Task — Execution context)
├── planner agent      → research plan (the Task's blueprint)
├── for each target:                    (the fan-out operates a DiscoveryRun:
│   │                                    claims in, CompanyDiscovered out — ADR-0018)
│   ├── research agent → company facts + analysis        ⤳ CompanyDiscovered (per claim),
│   │                                                      DiscoveryCompleted / Failed,
│   │                                                      CompanyFactsChanged,
│   │                                                      ImportRecordsUpdated
│   └── scoring service→ Opportunity (score + reasons)   ⤳ OpportunityScoreChanged,
│                                                          Qualified / Disqualified
├── sales agent        → Outreach + email drafts         ⤳ OutreachCreated,
│                                                          EmailDraftGenerated
└── report agent       → prioritized summary
                                    Task wrapper          ⤳ TaskCompleted / TaskFailed
```

Stage boundaries publish domain events (full catalog:
[business-domain.md](business-domain.md)) on the in-process EventBus —
stages never call each other directly (ADR-0004/0015). Progress
reporting, cancellation and batch execution (Celery) are later-sprint
concerns.

## Implemented: company_ingestion (Sprint 2 L7)

The first working workflow — the Discovery → Company seam (ADR-0019):

```
CompanyDiscovered (claim from a DiscoveryRun)
  → SnapshotNormalizer          raw text → CompanyName / WebsiteUrl
  → RepositoryCompanyDeduplicator   name match, then website host
  → CREATED (new Company + provenance + signals)
    MERGED  (alias / website-fill / source / signals — idempotent)
    REJECTED (unusable name; batch continues)
  → one UnitOfWork per event
```

No real data sources are wired; callers invoke `handle(event)` directly
until the event bus lands. Discovery still cannot import Company —
enforced by the context-boundary test.

## Implemented: opportunity (Sprint 2 L8)

The Company → Opportunity scoring seam (ADR-0020):

```
CompanyIngested | CompanyFactsChanged
  → load Company (facts + signals + sources)
  → OpportunityScoringService.assess(OpportunityScoringInput)
        replaceable strategy — MVP: mvp-deterministic-v1 placeholder
  → CREATED    (Opportunity.create_for_company + first assessment)
    REASSESSED (append to history — never overwrite)
    SKIPPED    (no sources / identical fingerprint / closed opportunity)
    REJECTED   (unknown company / incomplete assessment)
  → one UnitOfWork per event; events drained after work, before commit
```

The workflow orchestrates and never computes scores; weights live in the
scoring strategy. Idempotency: an assessment fingerprint (version +
score + confidence + reasons + evidence claims) makes replayed events
SKIP instead of duplicating history or events.
