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
| 1 | Foundation: scaffold, layers, docs, specs, Docker stack verified | ✅ Done (2026-07-15) |
| 2 | Core domain chain: ingestion, scoring, contact selection, draft generation | ✅ Done (2026-07-16) |
| 3 | Minimal API facade, browser workflow, and v0.1 acceptance | ⚠ OpenAI smoke pending |
| Next | Small real-user trial and validated workflow improvements | After v0.1 acceptance |

## Current Progress

**Sprint 1 complete & verified (2026-07-15).** Full skeleton, zero
business logic (by design). Baseline commits: `66217d2` (architecture
v1.0, 167 files) · `c7a0a01` (container-safe settings fix).

- Backend: FastAPI app factory + lifespan DI, async SQLAlchemy + Alembic
  (async env), Redis client, health/readiness endpoints, settings from
  root `.env`. Quality gates green: pytest · ruff · mypy --strict.
- Layers scaffolded (15 modules): domain(4) · agents(4) · tools(5) ·
  providers(4) · services(6) · workflows(4) · repositories · seed ·
  prompts(+shared/+versions) · schemas · shared · events · memory(4) ·
  tasks · observability(3).
- Frontend: Next.js 16 + TS + Tailwind + shadcn/ui, feature-first
  structure (5 features), typed API client. Build & lint green.
- **Infra verified end-to-end in Docker (OrbStack)**: all four compose
  services healthy; readiness probe reports Postgres ✓ Redis ✓; frontend
  serves on :3000, API docs on :8000/docs. pgAdmin available via
  `--profile tools`.
- Docs: 9 topic files + 14 ADRs (docs/ADR/), YAML specs (4), knowledge
  base (7 topic areas), demo seed data (3 companies + 3 contacts).

**Dev environment notes**: Docker Hub pulls go through the host Clash
proxy via OrbStack's relay — if pulls fail with EOF, fully restart
OrbStack (`orbctl stop && orbctl start`), keep `network_proxy auto`,
and retry.

**Top open questions** (block Sprint 2 design): ImportYeti access method ·
LinkedIn compliance approach · scoring dimensions · contact email sourcing.
Full list: [docs/prd.md](docs/prd.md#open-product-questions).

**Sprint 3 browser slice implemented (2026-07-16).** The backend exposes the
three-endpoint MVP facade (analyze, reload, approve), with Fake email generation
as the local default and durable approval metadata. The Next.js root page now
provides one focused prospect form and result workspace: multiple real sources,
optional signals/contact, qualification metrics, decision-maker selection,
review-only draft approval, and URL-based persisted reload. This is intentionally
not a Dashboard, CRM, authentication system, or sending client.

**MVP v0.1 release acceptance in progress (2026-07-16).** The complete Fake
Provider path has passed in Docker through the browser, including qualification,
draft generation, approval, persisted refresh/reload, and exact-replay
idempotency. Backend and frontend quality gates are green, and the local secret
boundary has been tightened so the frontend container does not inherit the root
`.env`. Final acceptance is waiting only for one real OpenAI generation with a
valid local credential; no real call was made with the placeholder value. See
[docs/mvp-acceptance.md](docs/mvp-acceptance.md).

## Future Roadmap

- **Complete v0.1 acceptance** — run one real OpenAI draft smoke test using the
  existing adapter, then record the quality decision without retaining the key
  or full sensitive content.
- **Next: real-user trial** — put the evidence → qualification → draft → human
  review loop in front of a small number of freight-forwarder users, collect
  observed blockers, and prioritize only validated workflow improvements.
- **Later backlog** — revisit broader platform capabilities only after the user
  trial establishes a concrete need; architecture expansion is not the next
  milestone.

Details: [docs/roadmap.md](docs/roadmap.md)
