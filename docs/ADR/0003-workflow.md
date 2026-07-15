# ADR-0003: Workflow orchestration model

Date: 2026-07-15 · Status: Accepted

## Context

Multi-step AI pipelines (plan → research → score → draft → report) need
an owner. Business logic must stay out of routes, agents and task-queue
entry points.

## Decision

- **Service** = deterministic business logic (CRUD, external APIs,
  scoring rules).
- **Workflow** (`app/workflows/`) = orchestrates agents and services;
  owns sequencing, fan-out, error recovery; no low-level I/O, no prompts.
- **Task** (`app/tasks/`) = thin queue-executed wrapper (Celery, later):
  deserialize → invoke workflow/service → persist result. Workers execute
  tasks directly; orchestration never lives in tasks.
- Four workflows: lead_generation (main pipeline), research, email,
  followup.

## Consequences

- MVP runs workflows synchronously; Celery slots in later without
  moving orchestration.
- Stage-to-stage coupling migrates to events over time (ADR-0004).
