# ADR-0016: Domain model — value objects, aggregates and invariants

Date: 2026-07-15 · Status: Accepted

## Context

Sprint 2 L4 implements the first code of the approved domain design
(ADR-0015): value objects, four aggregate roots, domain events and
domain service protocols, all under `app/domain/` with zero
infrastructure imports (enforced by `tests/domain/test_purity.py`).

## Decision

### Why primitive obsession is avoided

A bare `float` score can be 250; a bare `str` company name can be empty;
a bare `str` email can be anything. Every such value would need
re-validation at every layer boundary — and one missed check ships a
corrupt judgment. Value objects (`OpportunityScore`, `CompanyName`,
`EmailAddress`, …) validate once at construction, so **invalid values
are unrepresentable** and downstream code stops checking. They also give
business language a type: a signature taking `Confidence` documents
itself in a way `float` never will.

### Why domain objects are framework-independent

Business rules outlive frameworks and infrastructure choices. A rule
like "nothing sends without human approval" must be testable in
microseconds without a database, and must not change when SQLAlchemy,
FastAPI or the LLM provider changes. The purity test turns this from
intention into a failing build: `app/domain` cannot import FastAPI,
SQLAlchemy, Redis, Celery, LLM SDKs, HTTP clients, Pydantic, or any app
infrastructure module.

### Why OpportunityAssessment is immutable

An assessment is a historical fact: "on this date, scorer v1 judged this
company 82 with these reasons and this evidence." Editing a fact after
the event would corrupt the audit trail the product's trust is built on
— the score history must mean what it says. Immutability (frozen
dataclass) plus the append-only history in the Opportunity aggregate
makes retroactive tampering structurally impossible rather than merely
forbidden.

### Why aggregate methods control state changes

Public setters distribute rule enforcement to every caller — one
careless assignment (`opportunity.score = 99`) bypasses the history, the
events and the explanation. With private state behind behaviors
(`apply_assessment`, `qualify`, `mark_sent`, `retry`), every change
passes the invariant checks and emits its events exactly once. The rule
is enforced where the state lives, not where the caller happens to be.

### Why scoring computation belongs behind a domain service interface

Scoring needs data from outside one aggregate (company facts, user lens,
evidence aggregates) and its algorithm will evolve (rule-based → ML →
hybrid). The domain owns the *contract* — `OpportunityScoringService`
returns an immutable, versioned, explainable `OpportunityAssessment` —
while `app/services/scoring` owns the *computation*. The aggregate stays
ignorant of how scores are computed and merely refuses to accept
unexplainable ones.

## Consequences

- Aggregates buffer domain events internally (`drain_events()`); the
  application layer publishes them — the domain has no bus dependency.
- Events are immutable dataclasses here; transport-level schemas (when a
  real bus lands) may wrap them without changing domain code.
- The Task idempotency rule takes caller-supplied `active_keys` — the
  registry of active tasks is a persistence concern arriving with
  repositories.
- 112 unit tests document every legal and illegal transition.
