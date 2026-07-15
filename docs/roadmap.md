# Roadmap

## Sprint 1 — Foundation ✅ (2026-07-15)

- Monorepo scaffold: FastAPI backend (uv, Python 3.12), Next.js 16 frontend
  (TS, Tailwind, shadcn/ui), Docker Compose (backend/frontend/postgres/redis
  + pgAdmin profile), root .env, health endpoints, CI-ready quality gates
  (pytest / ruff / mypy strict / eslint).
- Full layer skeleton: domain, services, agents, tools, providers,
  repositories, prompts (with versioning convention), frontend features.
- No business logic yet — by design.

## Sprint 2 — Data & first vertical slice (proposed)

1. Align open questions: ImportYeti access, LinkedIn policy, scoring model.
2. `Company` / `Contact` models + repositories + first Alembic migration.
3. First tool implementation (data source with lowest legal/technical risk).
4. First end-to-end slice: search → store → list in frontend `companies`.

## Sprint 3 — AI pipeline (proposed)

1. Provider interface + OpenAI adapter; llm service.
2. Research agent + scoring service (opportunity analysis).
3. Sales agent (email generation) + prompt v1 set.
4. Workflow orchestrating the full chain.

## Later

- Celery (batch research runs), Qdrant + rag service (semantic search),
  additional LLM providers, nginx / flower, auth & multi-tenancy.
