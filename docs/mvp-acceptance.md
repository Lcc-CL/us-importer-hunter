# MVP v0.1 Acceptance

- Acceptance date: 2026-07-16
- Version: v0.1 release candidate
- Status: Real LLM smoke test passed (2026-07-17, via OpenAI-compatible gateway)

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

Second attempt (2026-07-17, baseline `e20acc6`): still blocked. The pre-flight
check found `OPENAI_API_KEY` in `.env` unchanged (6-character placeholder) and
no key in the shell environment. The provider switch was deliberately not made
and no request was sent, so no invalid credential ever left the machine. The
Fake-provider loop was independently re-verified the same day through the live
stack (QUALIFIED → SELECTED → GENERATED → approved → reload, PostgreSQL rows
confirmed). Result: **FAIL (blocked — no valid local credential)**.

Third attempt (2026-07-17, baseline `240c326`): a real request was sent for the
first time, and it failed authentication. `.env` now held a 67-character
`sk-`-prefixed value, so `EMAIL_GENERATOR_PROVIDER=openai` was enabled and the
full analyze flow was run through the live Docker stack. The upstream chain
succeeded against the real provider wiring (company CREATED, opportunity
QUALIFIED at score 70.5, decision maker SELECTED), but the draft step returned
the typed `FAILED` outcome: OpenAI answered `401 invalid_api_key` to the
application's `chat/completions` call, and an independent direct check against
`/v1/models` with the same key confirmed the rejection, ruling out application
code. No draft was generated or persisted; upstream analysis was saved as
designed. The provider override was then removed from `.env` and the stack was
restored to the Fake default (health verified). Result: **FAIL (credential
rejected by OpenAI — the configured key is not a valid OpenAI API key)**. Note:
the configured `OPENAI_MODEL` value has still never been validated, because
authentication fails before model resolution.

Fourth attempt (2026-07-17, post-`240c326` working tree): **PASS**. The local
`.env` was reconfigured to an OpenAI-compatible gateway
(`OPENAI_BASE_URL=https://codeyu.shop/v1`, consumed by the OpenAI SDK's
documented env-var fallback — no application code was changed) with
`OPENAI_MODEL=gpt-5.6-terra` and `EMAIL_GENERATOR_PROVIDER=openai`. A
pre-flight `GET /v1/models` against the gateway returned HTTP 200 and listed
the configured model. The full analyze flow then ran through the live Docker
stack:

- Request result: HTTP 200, `overall_status=COMPLETED` — company CREATED,
  opportunity QUALIFIED (score 70.5, confidence 0.7, completeness 1.0),
  decision maker SELECTED (confidence 0.9), email draft **GENERATED** (v1).
- Provider/model persisted on the draft: `provider=openai`,
  `model=gpt-5.6-terra` (first time model resolution has been exercised).
- Latency: 7.52 s end-to-end for the analyze request through the live stack
  (LLM generation dominates; the same flow with the Fake provider is
  sub-second).
- Draft quality: subject "Asia-to-US inbound freight support" (5 words);
  body 102 words; exactly one CTA (a 15-minute call request); every factual
  statement traces to a submitted signal (customs shipment activity,
  China-origin cargo, ocean FCL, high-value goods, warehouse operations,
  growing multi-origin supply chain) and is hedged as observation ("may be
  managing") rather than asserted; no invented commercial, volume, pricing,
  or shipment claims; professional greeting and sign-off using the submitted
  contact and sender names. Per established practice the full body is not
  reproduced here.
- Approval: the draft was approved (`approved_by_name` and `approved_at`
  persisted) and a follow-up detail read confirmed the approved state,
  provider, and model survive refresh.

Caveat: the request was served by a third-party OpenAI-compatible relay, not
`api.openai.com`, and `gpt-5.6-terra` is the gateway's model catalog name.
Output quality through the official endpoint remains unexercised; the
application-side wiring is now fully verified either way.

## v0.1.1 P0 — scorer signal-kind regression (2026-07-18/19)

Root cause: `DeterministicOpportunityScoringService` recognized a dimension
only by searching the signal text for **English** keywords. Chinese signal
detail therefore matched nothing, and four dimensions
(`shipping_fit`, `cargo_value_potential`, `company_scale`,
`logistics_complexity`) scored 0 despite the signals existing in the database.
The three dimensions that did score (`import_activity`, `china_dependency`,
`growth_signal`) matched only by coincidence — their English *kind* prefix
happens to contain a detector keyword. The score was capped at 39.5 (< 70), so
qualification could only ever be REVIEW, and because drafts are gated on
QUALIFIED (`workflows/email/workflow.py`), no email was ever generated.

Fix (scoped to detection only): the scorer now resolves a dimension from the
structured `"<kind>: …"` prefix through an alias table, and falls back to the
existing English keyword detectors when the kind is unknown, so legacy
free-text signals still score. **No qualification threshold, dimension weight,
schema, state machine, email gate, or production row was changed.**
`pain_point` maps to no dimension: it is stored, and never scores.

Regression evidence on the reported company
`7e1a93a8-84bb-49b1-857a-22d2852f4fb5` (JESKE), re-analyzed through the live
Docker stack with an **empty** signals payload so only the 20 already-stored
signals were re-scored — the signal count (20) and source count (4) were
unchanged by the run:

| | before | after |
|---|---|---|
| score | 39.5 | **70.5** |
| data completeness | 0.55 | **1.00** |
| qualification | review | **qualified** |
| recommended action | human_review | **prepare_outreach** |
| priority | low | **high** |
| email draft | none (0 outreaches) | **generated v1** |

The four previously blind dimensions now score from their Chinese detail:
`shipping_fit` +12, `cargo_value` (alias → `cargo_value_potential`) +6,
`company_scale` +6, `complexity` (alias → `logistics_complexity`) +7. The new
assessment was appended at position 2 (append-only history preserved; the two
historical REVIEW rows are intact). The draft persisted `provider=openai`,
`model=gpt-5.6-terra`, `prompt_version=first-outreach-v1`, was approved in the
browser, and survived reload.

A second, independent proof used a brand-new company submitted through the UI
with **100% Chinese signal detail** and canonical kinds chosen from the new
dropdown: score 70.5, completeness 1.00, qualified, real LLM draft generated
and approved. Before the fix that same input would have scored 39.5.

Frontend: the signal-kind field became a controlled dropdown — Chinese labels,
fixed English enum values on the wire (`import_activity`, `china_dependency`,
`shipping_fit`, `cargo_value_potential`, `company_scale`, `growth_signal`,
`logistics_complexity`, `pain_point`). Legacy stored values (`cargo_value`,
`growth`, `complexity`) still render with their canonical meaning when editing,
and any unrecognized value is shown explicitly as "未知信号类型 / Unknown signal
type" rather than being silently dropped.

## v0.1.1 — browser E2E regression harness

The regression above was found by hand and verified with throwaway scripts. It
is now a committed suite (`e2e/`, driven by `make e2e`) so the same class of
defect fails a gate instead of reaching a user. The harness starts an
**isolated** stack — backend `:8001`, frontend `:3001`, database
`importer_hunter_e2e` — created and dropped per run. The dev database is never
opened by a run, so isolation is structural rather than dependent on cleanup.

Coverage: the qualified path (Chinese structured signals → QUALIFIED → decision
maker → draft → approve → reload), the review path (thin evidence → REVIEW, no
draft, explainable "unknown, not negative" reasons), i18n default/toggle/persist
plus the signal-kind dropdown enum contract, and provider-badge correctness with
assertions that no key or base URL reaches the browser. Every spec also fails on
React duplicate-key warnings and unhandled page exceptions.

Fixtures are synthetic — no real customers or contacts — and hard-code no
database ids; company, assessment and draft ids are read back at runtime. Each
run randomizes the website host as well as the company name, because company
dedup matches on host and a fixed host silently merges consecutive runs.

Results on 2026-07-19, from the current tree:

- `make e2e` (Fake provider, no LLM cost): **6/6 passed**, teardown confirmed
  `importer_hunter_e2e` rows in `pg_database` = 0.
- `make e2e-real` (live provider): **1/1 passed** — draft persisted with
  `provider=openai`, a model name and a prompt version. The credential is
  presence-checked only and never printed.
- Dev database after both runs: 9 companies, JESKE still 20 signals / 70.5,
  and zero rows matching the E2E fixture naming — untouched.

## Quality gates

- Backend: 382 tests passed (v0.1.1: 373 → 374 runtime-status → 382 with eight
  new scorer cases covering kind detection, keyword fallback, the three
  aliases, unknown kinds, and `pain_point` not scoring), including real
  PostgreSQL migrations and the MVP analyze/query/approve/replay E2E test.
- Browser E2E: `make e2e` 6/6, `make e2e-real` 1/1 (2026-07-19).
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

- The real-LLM smoke test passed through an OpenAI-compatible gateway; output
  quality via the official `api.openai.com` endpoint has not been separately
  exercised.
- The v0.1.1 P0 fix addressed detection only. Two known issues were diagnosed
  and deliberately left out of scope: (P1) signal kinds are not validated at
  ingestion, so a typo such as the stored `ogistics_complexity` still maps to
  no dimension and silently scores 0 — the new dropdown prevents this for new
  input but does not repair stored rows; (P2) company deduplication merges on
  website host, so a synthetic QA company sharing a real company's domain is
  absorbed into it — this is how `[TEST ONLY]` signals entered the JESKE
  record. No production rows were altered to work around either.
- This MVP has no authentication, multi-tenancy, email sending, follow-up,
  company list, or full CRM workflow.
- Source quality remains the operator's responsibility; the application does
  not invent or independently verify submitted references.
- The page is a focused desktop-first workspace with basic responsive behavior,
  not a complete dashboard.

## Decision

MVP v0.1 is functionally ready under the Fake provider, and the previously
blocking real-LLM smoke test has now passed with its quality evidence recorded
above (2026-07-17, via an OpenAI-compatible gateway). All release acceptance
evidence is complete; formal sign-off of v0.1 is Lcc's call, noting the
gateway caveat. Next step remains a small real-user trial rather than adding
architecture or product breadth.
