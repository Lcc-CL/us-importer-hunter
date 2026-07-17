# ADR-0024: Minimal MVP prospect analysis API facade

Date: 2026-07-16 · Status: Accepted

## Context

The backend has independently tested workflows for Company ingestion,
Opportunity assessment, Contact ingestion, decision-maker selection and
EmailDraft generation. Sprint 3 Lesson 1 needs one browser-facing vertical
slice without committing the MVP to a broad CRUD surface or duplicating those
business rules in FastAPI routes.

## Decisions

### 1. Use an aggregate analysis facade, not a complete CRUD API

`MvpProspectAnalysisWorkflow` represents the single product action being
validated: analyze one prospect and prepare a reviewable draft when the facts
support it. Three focused endpoints expose analyze, read and approve. Generic
company/contact/opportunity CRUD, search and administration remain out of scope.

### 2. The facade calls existing workflows

The facade converts the request into the existing Discovery and Contact claim
contracts, calls each workflow in order and maps their typed outcomes. Multiple
explicit company source references are each ingested through the existing
Company workflow before scoring; no source is fabricated. The legacy singular
source is accepted only when the supplied website is its real reference. The
facade never scores a company, ranks a contact, builds a prompt, opens a
SQLAlchemy session or touches an ORM model.

### 3. Each stage retains its own transaction

Company, Opportunity, Contact, decision-maker assessment and EmailDraft remain
separate use cases with separate Unit of Work boundaries. A later failure does
not roll back already committed upstream facts. This matches the existing
aggregate boundaries and makes retry behavior explicit.

### 4. Later-stage failure returns PARTIAL

The analysis response records the outcome of every attempted stage. Provider or
downstream failures return `PARTIAL` with safe warnings, preserving identifiers
for successfully stored upstream data. Failure before Company persistence is
`FAILED`; a business-rejected company is `REJECTED`.

### 5. Business rejection is not always an HTTP error

`RESEARCH_MORE`, human `REVIEW`, no contact and qualification rejection are
normal business outcomes, returned in a 200 typed response. HTTP errors are
reserved for malformed input, missing resources, invalid state transitions,
provider availability and unexpected system failures.

### 6. Local development defaults to the fake email generator

`EMAIL_GENERATOR_PROVIDER=fake` is the default. `openai` must be selected
explicitly, and its API key is checked lazily only when generation is attempted.
Application startup, analysis without generation and all automated tests need no
OpenAI key or network access.

### 7. Authentication and multi-tenancy remain deferred

The facade uses one documented MVP system-user UUID as the Opportunity lens.
There is no login, JWT or authorization layer in this lesson. The fixed lens is
an application composition choice, not a new identity-domain model.

### 8. Approval remains separate from sending

The approval endpoint invokes `Outreach.approve_draft`, persists the aggregate,
commits and then drains its events. It does not send mail or call Gmail, SMTP or
any provider. `EmailDraft` owns and persists the approval status, UTC timestamp,
and approver display name so a refreshed query reconstructs the human decision.
Sending requires a future, separately authorized use case.

## Consequences

- The browser can analyze, reload persisted results and approve a draft through
  a minimal stable API.
- Partial results are inspectable and retryable without cross-aggregate rollback.
- OpenAPI can exercise the offline Fake generator path.
- Minimal approval metadata is durable without introducing authentication,
  multi-tenancy, or a broader identity/audit model.
- EventBus, Celery, RAG, authentication, full CRUD and email delivery remain out
  of scope.
