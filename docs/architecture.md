# Architecture

## Principles

1. Follow Clean Architecture.
2. Business logic never lives inside API routes.
3. Agents never call databases directly — they access data only through tools.
4. Services communicate with tools.
5. Workflows orchestrate agents (and services).
6. Modules are highly cohesive and loosely coupled.
7. All outputs use typed schemas (Pydantic end-to-end).
8. Every module is independently testable (dependency injection everywhere).
9. Design for scalability.
10. Code readability over cleverness.

## Layering

```
API Routes (FastAPI)      HTTP in/out + validation only, no business logic
    ↓
Workflows / Services      Workflows orchestrate multi-step AI pipelines;
                          Services hold deterministic business logic
    ↓
Agents                    LLM reasoning units; typed structured outputs;
                          no direct DB access; LLM calls only via llm service
    ↓                         ↓
Tools                     Providers
(only data-access path    (LLM vendor adapters behind a common
 for agents)               interface — swap vendors freely)
    ↓
Repositories              The only place raw queries live
    ↓
Infrastructure            SQLAlchemy (async) · Redis · Qdrant (later)

Domain (app/domain/)      Cross-cutting: pure business entities & rules,
                          framework-free; services map domain ↔ ORM ↔ schema
```

## Domain boundaries

Five bounded contexts own the nine business entities (full model:
[business-domain.md](business-domain.md), decision: ADR-0015):

| Context | Owns | Maps mainly to |
|---|---|---|
| Discovery | Company, Contact, ImportRecord | tools/, services/company, services/search |
| Intelligence | Opportunity (central value aggregate) | services/scoring, domain/crm |
| Outreach | Outreach, EmailDraft, Outcome | agents/sales, services/email |
| Execution | Task | workflows/, tasks/, observability/ |
| Identity | User | memory/user, core settings |

Contexts communicate through typed contracts and domain events
(`app/events/`) — never direct cross-module calls. Aggregates reference
each other by id only.

## Backend layout (`apps/backend/app/`)

| Directory      | Responsibility |
|----------------|----------------|
| `core/`        | Settings, infrastructure client factories |
| `observability/` | Metrics, logging, tracing — agent/prompt failure diagnosis lives here |
| `api/`         | FastAPI routes, DI providers, middleware |
| `schemas/`     | Pydantic models: API contracts, agent outputs, tool I/O |
| `domain/`      | Pure business entities & rules (company, contact, email, crm) |
| `agents/`      | LLM reasoning units (planner, research, sales, report) |
| `tools/`       | Agent capabilities (google, website, linkedin, importyeti, browser) |
| `providers/`   | LLM vendor adapters (openai; anthropic/deepseek/gemini later) |
| `services/`    | Deterministic business logic (llm, email, search, company, scoring, rag) |
| `workflows/`   | Multi-step orchestration (lead_generation, research, email, followup) |
| `events/`      | Typed pub/sub between pipeline stages — stages never call each other directly |
| `memory/`      | Standalone memory layer: short_term, long_term, conversation, user |
| `tasks/`       | Queue-executed entry points (Celery, later) — thin wrappers that invoke workflows, never orchestration |
| `prompts/`     | Prompt templates + `versions/` archive |
| `database/`    | ORM models, repositories, seed data, session factories, Alembic migrations |
| `shared/`      | Cross-cutting primitives: constants, enums, exceptions, types — no logic, no I/O |

## Related docs

- [Business domain](business-domain.md) — entities and ownership, defined before persistence
- [Coding standards](coding-standard.md)
- [Agents](agents.md) · [Workflows](workflow.md)
- [API](api.md) · [Database](database.md)
- [Decision log](decision.md) · [Roadmap](roadmap.md) · [PRD](prd.md)
