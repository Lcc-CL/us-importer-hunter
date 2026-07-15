# ADR-0005: Memory as a standalone layer

Date: 2026-07-15 · Status: Accepted

## Context

Agent memory (what the system accumulates and recalls at runtime) will
grow its own storage mix and policies; burying it under services would
couple that evolution to unrelated code.

## Decision

`app/memory/` is its own layer with four sub-domains: `short_term`
(run/session scratch, Redis+TTL), `long_term` (durable facts,
PostgreSQL/Qdrant), `conversation` (dialogue history), `user` (forwarder
profile & preferences). Agents/workflows access memory only through its
interfaces; backing stores stay swappable.

## Consequences

- Memory is distinct from `knowledge/` (curated corpus): different
  writers, different lifecycle, even if both may use Qdrant.
- Personalization inputs (user memory) have a defined home from day one.
