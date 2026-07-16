# ADR-0020: Company → Opportunity scoring boundary

Date: 2026-07-16 · Status: Accepted

## Context

L8 wires the first Company → Opportunity chain. The temptation at this
seam is to let "just a little" scoring leak into the workflow, the
company, or the database. This ADR fixes where judgment may live.

## Decision

### Why Company only stores facts

The same importer is a gold prospect for one forwarder and worthless to
another. If a score lived on Company, one user's judgment would be every
user's judgment, and re-scoring would rewrite shared state. Facts are
multi-tenant by nature; judgments are per-lens. Enforced in code
(`Company` has no score/priority/sales attribute — tested) and in the
schema (no such columns).

### Why Opportunity stores judgment

Judgment changes for its own reasons (new evidence, new policy, outcome
feedback) at its own rate, and must carry its own audit trail. The
Opportunity aggregate is exactly that container: score, confidence,
priority, reasons, recommended action, CRM stage, append-only history.

### Why scoring sits behind a replaceable service interface

Scoring needs data beyond one aggregate and will change implementation
(deterministic → rules → LLM → hybrid). `OpportunityScoringService` is
the domain-owned contract: explicit `OpportunityScoringInput` in
(scorers may not fetch anything else — no repository, no network,
enforced by boundary test), complete immutable `OpportunityAssessment`
out. The workflow proves replaceability by running with a Fake in unit
tests and the deterministic scorer in integration.

### Why a deterministic placeholder scorer now

The real scoring dimensions (volume, lane match, switching signals) are
an **open product decision** and their data source (ImportYeti) is
unresolved. Blocking the pipeline on that decision would stall every
downstream lesson; inventing weights would fake certainty. So
`mvp-deterministic-v1` uses only fields that exist today (website,
verification, signals, provenance), never fabricates import volume or
cargo value, and is documented as **not fit for real sales decisions**.
Being deterministic, it is also the ideal test fixture.

### Why Priority thresholds don't belong in the Value Object

A threshold is a *policy choice* that varies by scorer version and
eventually by user; a value object is a *universal truth* (a score is
0–100 everywhere, forever). Burying `>= 70` in `Priority` would make
every policy change a domain change. `ScoringPolicy` (versioned, owned
by the scoring strategy) maps score → priority; the L8 test proves the
same score yields different priorities under different policies.

### Why final scoring dimensions remain open

They depend on the ImportYeti access decision (what evidence exists),
on outcome data (what actually converts), and on the user lens design —
all pending. The interface, the assessment shape and the versioning are
stable; only the arithmetic inside the strategy will change.

### Why Assessment history is append-only

Each assessment is a dated fact: "on this day, scorer vX judged 82 with
these reasons." Overwriting it would destroy the ability to explain why
yesterday's ranking differed, to audit drift between scorer versions,
and to calibrate against outcomes. The aggregate appends (no history
entry, no score change — ADR-0016); the schema mirrors it (assessment
rows are never UPDATEd).

### Why duplicate events must not duplicate assessments

Events will be redelivered — retries, bus at-least-once semantics,
manual replays. Without idempotency every redelivery would append a
identical assessment, distort history, and re-emit events downstream.
The workflow computes an assessment fingerprint (scoring_version +
score + confidence + reasons + evidence claims) and SKIPs when the
latest history entry matches — replay-safe without burying idempotency
in the repository.

## Consequences

- `OpportunityAssessment` gained priority / recommended_action /
  assessed_by (persisted; migration eaef5d33aa6a).
- `Opportunity.create_for_company` now emits `OpportunityCreated`.
- New application facts `CompanyIngested` and `CompanyFactsChanged`
  (the latter supersedes the catalog name CompanyProfileUpdated).
- `OpportunityRepository.get_for_company_and_user` replaces the list
  lookup; open opportunities win over closed ones.
- When the event bus lands, both L7 and L8 workflows become subscribers
  without signature changes.
