# ADR-0018: Discovery produces claims and events, never companies

Date: 2026-07-16 · Status: Accepted

## Context

Sprint 2 L6 models the Discovery context in the domain (no real data
sources yet). The tempting shortcut is to let discovery code create
`Company` aggregates directly — it has the data in hand.

## Decision

Discovery produces **claims** (`DiscoveryResult`: a `RawCompanySnapshot`
plus `Evidence` and `Signal`s) wrapped in **events**
(`CompanyDiscovered`), tracked by a `DiscoveryRun` aggregate
(Created → Running → Completed/Failed, with query/claim statistics).
It never creates `Company` or `Opportunity` aggregates and never scores.

### Why a claim is not a company

A source saying "Pacific Home Goods Inc, pacifichomegoods.com" is an
observation, not truth: the same importer arrives under five spellings
from three sources. Canonical identity requires deduplication
(`CompanyDeduplicationService`) and provenance-tracked fact-merging —
that is the Company side of the Discovery context's job, consuming
`CompanyDiscovered` downstream. Snapshot text fields stay raw
(`name_text`, not `CompanyName`) precisely because normalization is the
accepting side's decision.

### Why DiscoveryRun is its own aggregate (not Task)

Task (Execution context) tracks *machine work*: attempts, retries, cost.
DiscoveryRun tracks *discovery semantics*: which criteria ran, how many
source queries succeeded/failed, how many claims surfaced. A workflow
run wraps both — one Task may operate one DiscoveryRun — but merging
them would put business statistics inside execution state (violating
ADR-0015's Task invariant #1).

### Counting semantics

One successful source query may yield many claims: `succeeded`/`failed`
count queries, `discovered` counts claims. `record_failure` is a query
failing while the run continues; `fail()` is the run itself breaking.

## Consequences

- The boundary is enforced by tests: `app/domain/discovery` must not
  import company/opportunity/outreach/task modules.
- Crawler/tool implementations (later sprints) plug in *under* this
  model: tools produce `RawCompanySnapshot`s, the run records them.
- Discovery events carry full claim payloads so the Company-side
  consumer needs no callback into Discovery.
