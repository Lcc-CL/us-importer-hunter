# ADR-0004: Event-driven stage coupling

Date: 2026-07-15 · Status: Accepted

## Context

As agents multiply, direct stage-to-stage calls (research calls sales)
create a rigid chain that is hard to extend or observe.

## Decision

Pipeline stages never call each other directly. The finishing stage
publishes a typed Pydantic event (past-tense names: `ResearchCompleted`,
`EmailDrafted`) on an `EventBus` (`app/events/`); the next stage
subscribes. MVP: in-process bus. The interface allows Redis pub/sub or a
broker later without touching publishers/subscribers.

## Consequences

- Adding a new reaction to an existing stage = new subscriber, no chain edits.
- MVP workflows may still run imperatively; events land with the first
  real stage-to-stage hand-off.
