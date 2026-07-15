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
HuntWorkflow
├── planner agent      → research plan
├── for each target:
│   ├── research agent → company analysis (via tools)
│   └── scoring service→ opportunity score
├── sales agent        → personalized email drafts
└── report agent       → prioritized summary
```

Progress reporting, cancellation and batch execution (Celery) are
later-sprint concerns.
