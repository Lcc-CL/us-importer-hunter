# ADR-0011: Root .env as single source of truth

Date: 2026-07-15 · Status: Accepted

## Context

Docker compose and the backend both need configuration; two env files
drift apart.

## Decision

One `.env` at repo root. Compose reads it natively; backend
`pydantic-settings` resolves the repo-root path explicitly. Real
environment variables always override file values (compose overrides
`POSTGRES_HOST=postgres` etc. inside containers).

## Consequences

- One file to fill in; no per-app env drift.
- `.env` is git-ignored; `.env.example` documents every variable.
