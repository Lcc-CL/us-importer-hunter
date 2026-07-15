# ADR-0010: Repository pattern, no generic base

Date: 2026-07-15 · Status: Accepted

## Context

Agents must not touch the database; services need a testable data
access seam. Generic `BaseRepository[T]` abstractions tend to be built
before any query exists to justify them.

## Decision

`app/database/repositories/` is the only place raw queries live.
Repositories take an `AsyncSession` via constructor injection and
return ORM models or typed schemas — never raw rows. No generic base
class until real models prove the abstraction.

## Consequences

- Services/tools mock repositories in tests; sessions stay an
  implementation detail.
- Some early duplication between repositories is accepted deliberately.
