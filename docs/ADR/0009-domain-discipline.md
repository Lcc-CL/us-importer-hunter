# ADR-0009: Domain layer discipline

Date: 2026-07-15 · Status: Accepted

## Context

A full DDD treatment (domain entity + ORM model + API schema for every
concept) triples mapping code; the MVP constraint is "do not
over-engineer".

## Decision

`app/domain/` (company, contact, email, crm) is framework-free — no
SQLAlchemy/FastAPI/OpenAI imports. Only concepts with real business
rules get domain entities; pure data-transfer concepts use schema + ORM
model only. No mapping for symmetry's sake.

## Consequences

- CRM stage transitions, scoring rules etc. stay testable without infra.
- Some concepts intentionally have no domain class — that is not a gap.
