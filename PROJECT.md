# US Importer Hunter — Project Document

> The living master document for this project. README.md is the short
> introduction; this file is where vision, scope, architecture and progress
> are tracked. Detailed references live in [docs/](docs/).

## Vision

Freight forwarders win customers through slow, manual prospecting: finding
US importers, judging their shipping volume and lanes, hunting contacts,
writing cold emails. US Importer Hunter turns that into an AI pipeline —
**a sales-intelligence platform that discovers, analyzes and prioritizes
US importers automatically, and drafts the outreach for you.**

## MVP

Three capabilities, one chain:

1. **Search** — find US importers across data sources (customs/BoL data,
   web, company sites).
2. **Analyze** — assess each company as a logistics opportunity (volume,
   lanes, current forwarder, switching signals).
3. **Outreach** — generate personalized outreach emails per company.

Out of scope for MVP: auth/multi-tenancy, email sending infrastructure,
billing. Full scope and open product questions: [docs/prd.md](docs/prd.md).

## Target User

International freight forwarders — sales and business-development roles
prospecting the US import market.

## Architecture

Clean Architecture, monorepo (`apps/backend` FastAPI + `apps/frontend`
Next.js 16):

```
API Routes → Workflows / Services → Agents → Tools → Repositories → Infra
                                       ↓
                                   Providers (LLM vendors, swappable)
Domain: framework-free business entities · Schemas: typed I/O everywhere
```

- **Stack**: FastAPI · Python 3.12 (uv) · PostgreSQL + SQLAlchemy 2.x
  (async) · Redis · Next.js + TypeScript + shadcn/ui · OpenAI SDK.
  Planned: Celery, Qdrant.
- **Key rules**: no business logic in routes; agents never touch the DB;
  all LLM calls via the llm service → provider adapters; typed schemas
  end-to-end; DI everywhere, no global state.
- **Declarative specs**: `apps/backend/specs/*.yaml` is the wiring source
  of truth. **Knowledge base**: `apps/backend/knowledge/` feeds RAG.

Details: [docs/architecture.md](docs/architecture.md) ·
[docs/coding-standard.md](docs/coding-standard.md) ·
[docs/decision.md](docs/decision.md)

## Workflow

Main MVP pipeline (`hunt`):

```
user goal → Planner → Research (fan-out per company, via tools)
          → Scoring service → Sales (email drafts) → Report
```

Agents: planner / research / sales / report. Data sources: ImportYeti,
Google, company websites, LinkedIn (access methods partly TBD).
Details: [docs/workflow.md](docs/workflow.md) · [docs/agents.md](docs/agents.md)

## Sprint

| Sprint | Theme | Status |
|---|---|---|
| 1 | Foundation: scaffold, layers, docs, specs | ✅ Done (2026-07-15) |
| 2 | Data & first vertical slice: models, first tool, search → list | Planned |
| 3 | AI pipeline: providers, agents, prompts, hunt workflow | Planned |
| Later | Celery, Qdrant/RAG, more providers, auth | Backlog |

## Current Progress

**Sprint 1 complete (2026-07-15).** Full skeleton, zero business logic (by
design):

- Backend: FastAPI app factory + lifespan DI, async SQLAlchemy + Alembic
  (async env), Redis client, health/readiness endpoints, settings from
  root `.env`. Quality gates green: pytest · ruff · mypy --strict.
- Layers scaffolded: domain(4) · agents(4) · tools(5) · providers(4) ·
  services(6) · repositories · prompts(+versioning) · schemas.
- Frontend: Next.js 16 + TS + Tailwind + shadcn/ui, feature-first
  structure (5 features), typed API client. Build & lint green.
- Infra: Docker Compose (backend/frontend/postgres/redis + pgAdmin
  profile), multi-stage Dockerfiles. ⚠️ Docker not yet installed on the
  dev machine — compose config written but unverified.
- Docs (9 files in docs/), YAML specs (4), knowledge base (7 topic areas).

**Top open questions** (block Sprint 2 design): ImportYeti access method ·
LinkedIn compliance approach · scoring dimensions · contact email sourcing.
Full list: [docs/prd.md](docs/prd.md#open-product-questions).

## Future Roadmap

- **Sprint 2** — resolve data-source decisions; `Company`/`Contact` models
  + first migration; first tool implementation; vertical slice: search →
  store → companies list in frontend.
- **Sprint 3** — provider interface + OpenAI adapter; research agent +
  scoring; sales agent + prompt v1; hunt workflow end-to-end.
- **Beyond** — Celery batch runs; Qdrant + RAG over the knowledge base;
  provider expansion (Anthropic/DeepSeek/Gemini); auth & multi-tenancy;
  deployment hardening (nginx, flower, CI/CD).

Details: [docs/roadmap.md](docs/roadmap.md)
