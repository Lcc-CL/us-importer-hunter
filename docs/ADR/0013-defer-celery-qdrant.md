# ADR-0013: Defer Celery and Qdrant

Date: 2026-07-15 · Status: Accepted

## Context

Celery (batch runs) and Qdrant (semantic search / RAG) are in the
target stack but nothing in Sprint 1–2 needs them; MVP constraints
forbid unused packages and premature infrastructure.

## Decision

Neither is installed nor composed in Sprint 1. `docker-compose.yml`
uses named volumes, a shared bridge network and healthchecked
`depends_on` so `celery-worker`, `qdrant` (plus `nginx`, `flower`) are
add-only changes. Layer homes already exist (`app/tasks/`,
`app/services/rag/`).

## Consequences

- Smaller install/attack surface now; zero restructuring later.
