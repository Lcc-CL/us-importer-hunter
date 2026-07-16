# ADR-0017: Domain–persistence separation

Date: 2026-07-16 · Status: Accepted

## Context

Sprint 2 L5 adds the first persistence for the four aggregates. The
domain layer is framework-free (ADR-0016) and must stay that way while
PostgreSQL becomes the system of record.

## Decision

### Why ORM models are separate from domain entities

One class serving both masters serves neither: SQLAlchemy needs mutable
mapped attributes, lazy-loading and session awareness; the domain needs
private state, invariant-guarding behaviors and framework independence.
A shared class would let a session flush bypass `apply_assessment`, and
would drag SQLAlchemy into every domain unit test. Two models, one
explicit seam (the mapper), keeps both honest — `app/database/models/`
never crosses the repository boundary (enforced by tests).

### Why repositories expose domain aggregates

Callers (services, workflows) speak business language: they load a
`Company`, call behaviors, save it. If repositories returned ORM rows,
every caller would re-assemble aggregates ad hoc and invariants would be
bypassable everywhere. The repository is the translation point — domain
in, domain out; SQL stays inside. Operations are aggregate-oriented
(get_by_id / add / save / business lookups), no generic CRUD base
(ADR-0010).

### Why mappers are explicit

Implicit mapping (shared base classes, reflection, `__dict__` copying)
hides exactly the decisions that matter: how value objects serialize,
which child table each collection lands in, what happens to pending
events on reconstruction (answer: they are never restored). An explicit
`to_model`/`to_domain` pair per aggregate makes every persistence
decision reviewable in one file. Mappers are the one sanctioned peer of
aggregate private state.

### Why append-only histories use separate tables

`opportunity_assessments`, `opportunity_evidence`, `outcomes` and
`task_attempts` are immutable facts (ADR-0016). Separate child tables
with deterministic composite keys `(parent_id, position)` mean: appends
are inserts, existing rows are never updated, and the audit trail can be
queried and retained independently of parent-row churn. Deterministic
keys also make `session.merge` diff correctly instead of duplicating
history on every save.

### Why database constraints duplicate critical domain invariants

Defense in depth. The domain enforces rules for code paths that go
through aggregates; the database enforces them against everything else —
bugs, manual SQL, future services. Duplicated: score 0–100, confidence
0–1 (CHECK), one active task per idempotency key (partial unique index
`WHERE status IN ('created','running')`), unique canonical
`normalized_name`, explicit FK delete behavior (CASCADE inside an
aggregate, RESTRICT across aggregates). Constraints only mirror domain
rules — nothing was invented that the domain doesn't already say.

### Why MVP uses a lightweight Unit of Work

One use case = one transaction = one `AsyncSession`. The UoW is ~60
lines: it opens a session, exposes the four repositories, and commits or
rolls back explicitly; leaving the context without commit rolls back.
That is the entire transactional story the MVP needs — no session-per-
repository ambiguity, no framework. Domain event publishing is
deliberately absent; the event dispatcher lands in a later lesson and
will hook exactly here (drain aggregates → publish after commit).

## Notes

- `Company.mark_verified` is currently **idempotent** (silent no-op when
  already verified), applied as an L4 review follow-up. This remains a
  **pending decision** flagged for revisit before workflow integration —
  the alternative (raising `DuplicateOperation`) is stricter for callers
  but hostile to workflow retries. Persistence takes no side: `verified`
  is a plain boolean either way.
- `users` has no table yet: `opportunities.user_id` is a bare UUID
  column (Identity context arrives later).
- `contacts` is a minimal table so `outreaches.contact_id` has a real
  FK; the Contact domain entity comes with the Discovery implementation.
- JSONB is limited to two audit-display fields (assessment `reasons`,
  evidence `sources` provenance blobs); everything searchable is
  relational.

## Consequences

- Saves rebuild the model graph and `merge` diffs it — simple and
  correct for MVP scale; per-aggregate dirty tracking is a later
  optimization if profiling demands it.
- Repository integration tests run against real PostgreSQL (savepoint
  isolation); the migration itself is exercised up/down/up in tests.
