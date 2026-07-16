# ADR-0022: Contact and decision-maker model

Date: 2026-07-16 · Status: Accepted

## Context

L10 models the people side: contacts, their channels, and the choice of
a logistics decision maker for an opportunity — with no real contact
providers (LinkedIn/Apollo/Hunter) wired.

## Decisions

### 1. Why Contact is an independent aggregate root

A contact is used by many outreaches, and their title, channels and
verification state change on their own timeline — independent of any
company edit or conversation. Inside Company, every contact change
would version/lock the company; inside Outreach, the same person would
be duplicated per conversation. An independent root (Outreach context)
gives contacts their own lifecycle, transactions and events.

### 2. Why Company ↔ Contact link by company_id

Cross-aggregate references are ids only (ADR-0015). The FK gives
integrity (contacts die with their company, CASCADE); the id-only
object graph keeps loading a company from loading its people.

### 3. Why Outreach references only contact_id

The conversation needs to know *who* it addresses, not the person's
full channel history. Referencing by id lets the contact's verification
state evolve without touching sent conversations — the outreach records
whom it wrote to; the contact records how reachable they are now.

### 4. Why contact facts and decision-maker judgment are separate

The same fact/judgment split as Company/Opportunity (ADR-0020): "Maria
is Director of Supply Chain with a verified email" is a fact on the
Contact; "Maria is the best person to pitch" is a judgment —
`DecisionMakerFitAssessment`, immutable, evidence-backed, versioned,
append-only in its own table. Judgments recompute; facts persist.

### 5. Why channels are independently verified

An email bounces; a LinkedIn profile survives. One "contact verified"
flag can't express that. Per-channel `ContactVerificationStatus` (with
verified_at and confidence) lets one channel die without killing the
person — an INVALID channel is excluded from lookups and reachability
while the contact remains valid.

### 6. Why the selection policy is a versioned MVP assumption

mvp-decision-maker-policy-v1's numbers (department fit, seniority
bonuses, 60/40 role-reachability blend) are reasoned guesses with zero
reply data behind them. They live in one weights object, stamped onto
every assessment; when outcomes exist, recalibration bumps the version
and history explains itself.

### 7. Why contactability feeds Opportunity but never replaces it

A reachable company is not a valuable company — reachability is one of
eight dimensions (CONTACTABILITY, weight 10). Contact changes emit
`ContactabilityChanged`, which later triggers CompanyFactsChanged /
reassessment; the contact workflows never touch OpportunityAssessment
directly. Otherwise "easy to email" would silently outrank "ships 400
TEU from Shanghai".

## Consequences

- contacts placeholder table upgraded; contact_channels /
  contact_sources / contact_fit_assessments added (fingerprint-unique,
  append-only). Migration c4470047a477 (up/down/up verified).
- Two new workflows (contact_ingestion, decision_maker) follow the L9
  peek → commit → drain rule; DecisionMakerSelected is carried in the
  outcome for the email-draft workflow (next lesson).
- Dedup never merges on name alone; conflicting channels return
  POSSIBLE_MATCH for a human.
