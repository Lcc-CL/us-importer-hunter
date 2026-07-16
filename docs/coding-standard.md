# Coding Standards

## Backend (Python 3.12, uv)

- **Production-ready**: full error handling, logging, no placeholders.
- **Dependency injection**: FastAPI `Depends` + constructor injection; no
  module-level singletons. Shared resources (engine, redis) are created in
  the app lifespan and live on `app.state`.
- **Async everywhere it matters**: routes, DB (SQLAlchemy 2.x async +
  asyncpg), HTTP (httpx), LLM calls. Celery workers (later) are the
  exception and are handled explicitly.
- **Typing**: full type hints; `mypy --strict` must pass.
- **Pydantic v2** for all data models; no bare dicts across layer
  boundaries.
- **SQLAlchemy 2.x** declarative style: `Mapped[]` / `mapped_column()`.
- **DRY & SOLID**; readability over cleverness; clear naming; no global
  state.
- Lint/format: `ruff check` + `ruff format` (line length 100).

### Domain layer (`app/domain/`) — additional rules (ADR-0016)

- **No infrastructure imports** — no FastAPI/SQLAlchemy/Redis/Celery/LLM
  SDKs/HTTP clients/Pydantic; enforced by `tests/domain/test_purity.py`.
- Value objects: frozen dataclasses, validated in `__post_init__`,
  value-based equality. No bare primitives across aggregate boundaries.
- Aggregates: private state, public read-only properties, state changes
  only through behavior methods that enforce invariants and raise typed
  `DomainError` subclasses. Entity identity = UUID.
- Domain events: immutable, past-tense facts; aggregates buffer them,
  `drain_events()` hands them to the application layer. No bus in the
  domain.
- Datetimes are always UTC-aware (`app.domain.clock`).

### Persistence layer (`app/database/`) — additional rules (ADR-0017)

- ORM models are persistence-only: they never cross the repository
  boundary and domain classes never inherit from them.
- All mapping lives in `app/database/mappers/` — never in aggregates or
  API schemas. Reconstructed aggregates start with an empty event buffer.
- Repositories implement the protocols in `app/domain/repositories.py`:
  domain aggregates in and out, aggregate-oriented methods only, no
  generic CRUD base.
- One use case = one Unit of Work = one transaction; repositories never
  commit.
- Append-only history tables (`*_assessments`, `*_evidence`, `outcomes`,
  `task_attempts`): rows are inserted, never updated.
- Critical domain invariants are duplicated as DB constraints (CHECK,
  partial unique, explicit FK ondelete) — defense in depth, never a
  replacement for domain enforcement.

## Frontend (Next.js, TypeScript)

- Feature-first structure under `src/features/` (see its README).
- All backend calls via `src/lib/api.ts` — no raw `fetch` in components.
- shadcn/ui for UI primitives (`src/components/ui/`); note it is Base
  UI-based — element substitution uses the `render` prop, not `asChild`.
- ESLint must pass; production build (`npm run build`) must succeed.
- This repo runs **Next.js 16** — consult the bundled docs in
  `node_modules/next/dist/docs/` rather than assuming older conventions.

## Quality gates (all must pass before merge)

```bash
cd apps/backend && uv run pytest && uv run ruff check . && uv run mypy app
cd apps/frontend && npm run lint && npm run build
```

## Constraints (standing, from product owner)

- Do not over-engineer; avoid premature optimization.
- No unnecessary packages — justify every new dependency.
- Focus only on MVP; keep the architecture extensible.
