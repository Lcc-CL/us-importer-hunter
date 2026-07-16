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
├── for each target:
│   ├── research agent → company facts + analysis        ⤳ DiscoveryCompleted,
│   │                                                      CompanyProfileUpdated,
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
