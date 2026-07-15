# ADR-0001: Monorepo with apps/backend + apps/frontend

Date: 2026-07-15 · Status: Accepted

## Context

Backend (FastAPI) and frontend (Next.js) need to evolve together during
the MVP; separate repos add coordination overhead for a small team.

## Decision

One repository. `apps/backend` and `apps/frontend` hold the two
applications; repo root keeps `docs/`, `scripts/`, `docker-compose.yml`
and the shared `.env`. Backend code lives in a single `app` package.

## Consequences

- One clone, one compose file, atomic cross-stack changes.
- Docker build contexts are per-app directories — shared root files are
  not visible inside image builds (see ADR-0007 for knowledge/ placement).
