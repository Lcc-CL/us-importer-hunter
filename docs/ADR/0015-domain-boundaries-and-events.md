# ADR-0015: Domain boundaries, aggregates and domain events

Date: 2026-07-15 · Status: Accepted

## Context

Sprint 2 designs the business domain before persistence. Without explicit
boundaries, "score", "status" and "attempt" blur across modules, email
drafts get mistaken for the sales process, and modules start calling into
each other's internals — the exact coupling the architecture principles
forbid.

## Decision

Five bounded contexts (Discovery, Intelligence, Outreach, Execution,
Identity) own nine entities, organized into four aggregates (Company,
Opportunity, Outreach, Task). Details: docs/business-domain.md.

### Why Opportunity is the product's central value aggregate

The product's one irreplaceable screen is the prioritized opportunity
list. Everything upstream (discovery, evidence) exists to create
opportunities; everything downstream (outreach, outcomes) exists to act
on them and improve them. Concretely: the score may only change through
domain behaviors (`rescore`, `apply_outcome`) that append to an
assessment history — an unexplainable or untraceable score is invalid by
definition, because an unexplainable ranking is a product users won't
trust.

### Why Company, Opportunity, Outreach and Task are separate aggregates

They change for different reasons, at different rates, driven by
different actors:

- **Company** changes when *external reality* is re-observed (new
  evidence, enrichment) — it is a fact and must stay judgment-free so
  many users can judge the same importer differently.
- **Opportunity** changes when *judgment* changes (rescore, stage
  transition) — per user, recomputable, explainable.
- **Outreach** changes when *the conversation* moves (draft, approve,
  send, reply) — human-gated, and an EmailDraft is one artifact inside
  that conversation, not the sales process itself.
- **Task** changes when *the machine* works (attempts, errors, cost) —
  it must never contain business judgment, or execution retries would
  rewrite business history.

One aggregate merging any two of these would force unrelated state to be
locked, versioned and audited together.

### Why contexts communicate through typed contracts/events, not direct calls

Direct cross-module calls make the pipeline a rigid chain: adding "when
research finishes, also refresh the RAG index" means editing the research
module. With typed events (`ResearchCompleted` → subscribers), it means
adding a subscriber. Events also *are* the audit trail — the business
narrative ("qualified → drafted → sent → replied → won") becomes data,
which the report agent and memory layer consume without touching the
producers. Fifteen initial events are defined in business-domain.md.

### Why event transport stays implementation-agnostic in the MVP

The MVP runs single-process; an in-process EventBus (ADR-0004) is
sufficient and adds zero infrastructure. Kafka/RabbitMQ/Celery-as-bus now
would be premature optimization (Sprint constraint #8: no unnecessary
packages). Event *definitions* are typed schemas independent of
transport — implemented as immutable dataclasses in the domain layer
(ADR-0016); transport-level wrappers may be added when a real bus lands.
Swapping the bus for Redis pub/sub or a broker later changes plumbing,
not meaning — producers and subscribers keep their signatures.

## Consequences

- Persistence design (next lessons) maps aggregates to tables knowing
  the consistency boundaries in advance.
- specs/company.yaml lost its scoring block to specs/opportunity.yaml;
  Outreach joins the official entity list.
- Cross-context reads go through contracts (typed schemas), keeping
  future service extraction possible without a rewrite.
