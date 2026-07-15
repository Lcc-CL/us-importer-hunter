# ADR-0014: Lazy infrastructure clients, observable readiness

Date: 2026-07-15 · Status: Accepted

## Context

Failing app startup when PostgreSQL/Redis are briefly unavailable makes
local development and container orchestration brittle.

## Decision

Engine and Redis clients are created (not connected) in the FastAPI
lifespan and stored on `app.state` — no module-level globals. Readiness
is observable via `GET /api/v1/health/ready`, which reports
per-dependency status; liveness (`/health`) has no dependencies.

## Consequences

- App boots regardless of infra order; orchestrators gate on readiness.
- Connection failures surface as diagnosable readiness output, not
  crash loops.
