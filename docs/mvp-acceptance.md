# MVP v0.1 Acceptance

- Acceptance date: 2026-07-16
- Version: v0.1 release candidate
- Status: Pending one real OpenAI smoke test

## Core paths verified

- Browser form accepted a company, two independent source references, factual
  signals, an optional contact, and sender details.
- The persisted chain completed as `QUALIFIED → SELECTED → GENERATED` with the
  Fake provider.
- The UI displayed score, confidence, data completeness, qualification reasons,
  decision-maker selection, and the review-only email draft.
- Draft approval persisted its approver and timestamp. `Refresh Result` and a
  full browser reload both restored the approved state.
- An exact replay reused the assessment context and returned the existing draft
  as `SKIPPED`; it did not create a duplicate draft. A genuinely changed sender
  value proposition correctly created a new draft version.
- No email was sent. The UI identifies every generated item as a draft.

## Fake provider

Passed in Docker Compose through the frontend. The demonstration prospect used
non-sensitive example contact data and two clearly identified references. The
qualified run produced a deterministic draft, supported approval, and survived
refresh and reload. The Fake provider remains the default and its automated
coverage verifies that no `OPENAI_API_KEY` is required.

## OpenAI smoke test

Not run. The local root `.env` contained only a short placeholder rather than a
usable credential, so no OpenAI request was attempted. No key or complete email
body was written to this document or to a long-lived test log.

The following release acceptance evidence remains required after a valid key is
installed locally: successful generation through the existing
`OpenAIEmailDraftGenerator`, subject and body word count, one CTA, context-only
facts, no invented commercial or shipment claims, approval, and persisted
refresh.

## Quality gates

- Backend: 373 tests passed, including real PostgreSQL migrations and the MVP
  analyze/query/approve/replay E2E test.
- Ruff: passed.
- mypy strict: passed for 189 source files.
- Frontend TypeScript check: passed.
- Frontend ESLint: passed.
- Frontend production build: passed with Next.js 16.2.10.
- Docker: frontend and backend running; PostgreSQL and Redis healthy; backend
  health, readiness, and Swagger returned HTTP 200.

## Security checks

- `.env` is ignored and untracked; `.env.example` has an empty key value.
- No long-form OpenAI key pattern was found in tracked files, the current diff,
  or Git history.
- The frontend runtime has no OpenAI key reference, and the frontend container
  no longer receives the root `.env`.
- Backend application logging contains no statement that prints the key.
- SQL statement echo is disabled even in debug mode so bound draft bodies are
  not retained in application logs.
- OpenAI adapter tests use mocks; the acceptance smoke test is deliberately not
  part of pytest.

## Known limitations

- Real OpenAI output quality is not accepted until the one blocked smoke test is
  completed.
- This MVP has no authentication, multi-tenancy, email sending, follow-up,
  company list, or full CRM workflow.
- Source quality remains the operator's responsibility; the application does
  not invent or independently verify submitted references.
- The page is a focused desktop-first workspace with basic responsive behavior,
  not a complete dashboard.

## Decision

MVP v0.1 is functionally ready under the Fake provider, but final release
acceptance is **not yet granted**. Complete the single real OpenAI smoke test,
record its quality result here, and then move to a small real-user trial rather
than adding architecture or product breadth.
