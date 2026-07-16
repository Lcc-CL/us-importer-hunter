# ADR-0021: Explainable opportunity scoring policy v1

Date: 2026-07-16 · Status: Accepted

## Context

L9 replaces the flat placeholder scorer with a dimensional, explainable
policy (8 dimensions, weights summing to 100), a qualification decision,
hard gates, persisted fingerprints, and a corrected event/commit order.

## Decisions

### 1. Why score and data completeness are separate

A score answers "how good does this prospect look?"; completeness
answers "how much of the picture have we actually seen?". Folding them
together makes a thin-data company look like a bad company. They are
independent axes: score = Σ(weight × normalized) over *assessed*
dimensions; completeness = evidence-backed weight ÷ applicable weight.

### 2. Why unknown data is not low-score data

No cargo-value data does not mean low cargo value — it means we haven't
looked yet. Unknown dimensions earn exactly 0 (enforced by the
DimensionAssessment invariant), lower completeness and confidence, and
route the company to RESEARCH_MORE — never to a penalty. Punishing
missing data would systematically bury exactly the prospects nobody has
researched yet, which is where the opportunities are.

### 3. Why a dimensional score breakdown

"82" convinces nobody. "IMPORT_ACTIVITY 16/20 because importyeti
recorded shipments; CARGO_VALUE unknown — no data" convinces a
salesperson and enables debugging, calibration and audit. Each
DimensionAssessment carries its own status, evidence, reasons and
earned score; the breakdown is stored as an immutable snapshot.

### 4. Why hard gates are separate from weighted scoring

"Not a US company" is not a −40; it is a categorical exit. Mixing
knockouts into weights lets enough bonus points outvote a fatal fact.
HardGatePolicy runs before qualification, fires only on explicit
markers **with evidence** (a gate without evidence is a rumor), and a
hit preserves the full scoring input for audit.

### 5. Why scoring and qualification are two steps

Scoring is measurement (deterministic arithmetic over facts);
qualification is a business decision over measurements (thresholds,
gates, actions). They version independently: recalibrating "what counts
as qualified" must not change how dimensions are measured, and vice
versa. Both run behind the scorer interface, but as two explicit,
separately versioned policies (mvp-explainable-scoring-v1 /
mvp-qualification-policy-v1).

### 6. Why every assessed dimension requires evidence

The product's promise is judgments traceable to evidence (three-layer
rule, ADR-0015). A dimension scored without evidence is an opinion; the
invariant makes it unconstructible, and the no-fabrication tests make
sure the scorer never invents TEU, cargo value, China dependency or
revenue it doesn't have.

### 7. Why thresholds and weights live in versioned policy

Weights (20/15/15/10/10/10/10/10) and thresholds (70 / 0.65 / 0.50 /
0.40) are tunable business hypotheses, not universal truths. In a
policy object they change by configuration and are stamped onto every
assessment (policy_version), so historical rankings stay explainable after
recalibration. In a Value Object or ORM column they would be constants
pretending to be facts.

### 8. Why the assessment fingerprint is persisted

L8 derived the fingerprint at comparison time — good enough for a
single process, invisible to the database and to concurrent writers.
Persisting a SHA-256 over canonical, time-independent judgment content
gives: an application-level replay check that survives restarts, a
database unique constraint (opportunity_id, fingerprint) that closes
the concurrency race, and an audit key linking identical judgments
across event redeliveries. Python's builtin hash() is process-seeded
and unusable for this.

### 9. Why these rules are still MVP assumptions

Every number here (weights, normalized values, thresholds) was chosen
by reasoning, not by data — there are zero real outcomes yet. The
documentation and version strings say so explicitly: this policy ranks
development data and exercises the pipeline; it must not drive real
sales decisions.

### 10. How outcomes will calibrate the weights later

Outcomes (replies, meetings, wins/losses — the Outreach context's
append-only records) join back to assessments via opportunity ids and
policy versions. Once enough outcomes exist: compare reply/win rates
across score bands per policy version, adjust weights/thresholds,
bump the version, re-score. The append-only history makes every
recalibration an A/B comparison instead of an overwrite.

## Consequences

- Events now drain only after successful commit (peek → commit →
  drain); a failed commit keeps them pending, so retries publish once.
- opportunity_assessments gains data_completeness, qualification
  _decision, policy_version, assessment_fingerprint, score_breakdown
  (JSONB — immutable audit snapshot; searchable fields stay columns).
- The QUALIFIED band is reachable only with all dimensions evidenced
  and multiple distinct sources — deliberately conservative.
