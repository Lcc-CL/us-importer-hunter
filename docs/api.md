# API

FastAPI app, all routes under `API_V1_PREFIX` (default `/api/v1`).
Interactive docs at `/docs` (disabled in production).

## Conventions

- Routes live in `app/api/routes/`, one module per resource, aggregated
  in `app/api/router.py`.
- Routes contain **no business logic** — validate, delegate to a
  service/workflow, return a typed schema from `app/schemas/`.
- Dependencies come from `app/api/deps.py` (`SettingsDep`, `DbSessionDep`,
  `RedisDep`).
- Errors: raise `HTTPException` in routes only; deeper layers raise
  domain exceptions that routes translate.

## Current endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Liveness — no external dependencies |
| GET | `/api/v1/health/ready` | Readiness — checks PostgreSQL & Redis, reports per-dependency status |

## Planned resources (Sprint 2+, names tentative)

`/companies` (search & list), `/research` (runs), `/emails` (drafts) — to
be specified when the first vertical slice is designed.
