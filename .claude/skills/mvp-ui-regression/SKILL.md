---
name: mvp-ui-regression
description: Run, debug, or extend the US Importer Hunter browser E2E regression — start the isolated e2e stack, run the Playwright suite (fake or real provider), screenshot failures, open the HTML report. Use when asked to run e2e, browser tests, UI regression, verify the MVP flow end to end, or check a change did not break analyze → draft → approve.
---

# US Importer Hunter — browser E2E regression

This skill is an **orchestration entry point only**. Every moving part lives in
the repository and runs without it: the Playwright suite in `e2e/`, the stack
overlay in `docker-compose.e2e.yml`, and the `make` targets below. Nothing
depends on a scratchpad, a temp directory, or a prior conversation.

All paths are relative to the repository root.

## What it drives

An **isolated** stack, so a run can never touch the dev database:

| | dev stack | e2e stack |
|---|---|---|
| backend | `:8000` | `:8001` |
| frontend | `:3000` | `:3001` |
| database | `importer_hunter` | `importer_hunter_e2e` (created, then dropped) |
| provider | whatever `.env` says | `fake` by default |

Postgres and Redis containers are shared; the e2e backend simply points at its
own database and its own Redis db index.

## Run it

```bash
make e2e          # default: Fake provider, whole suite, no LLM cost
make e2e-real     # one draft through the live provider (needs OPENAI_API_KEY)
```

Both targets install dependencies, recreate the throwaway database, apply
migrations, start the stack, run the suite, and tear down — including on
failure (the teardown is an `EXIT` trap). First run downloads Chromium.

Debugging a failure, or iterating on a spec:

```bash
make e2e-up                       # leave the stack running on :8001/:3001
cd e2e && npx playwright test --grep-invert @real --headed
cd e2e && npx playwright test tests/review-path.spec.ts   # one spec
make e2e-report                   # open the HTML report
make e2e-down                     # stop and drop the database
```

Artifacts: `e2e/playwright-report/` (HTML), `e2e/test-results/` (failure
screenshots and traces). Both are gitignored.

## What it covers

| Spec | Asserts |
|---|---|
| `tests/qualified-path.spec.ts` | company → Chinese structured signals → QUALIFIED (70.5 / completeness 1.0) → decision maker → draft → approve → reload restores. Verifies in Postgres, and that `pain_point` is stored but scores nothing. |
| `tests/review-path.spec.ts` | thin evidence → REVIEW (37.5 / completeness 0.55) → **no draft**, approve button absent, "unknown, not negative" reasons visible. |
| `tests/i18n.spec.ts` | Chinese default → English toggle → persists across reload; signal-kind dropdown shows localized labels and submits canonical English enums. |
| `tests/provider-badge.spec.ts` | badge matches the running provider (演示模式 / 真实 AI); page HTML and `/health/runtime` contain no key, no base URL. |

Every spec also fails on React duplicate-key warnings and unhandled page
exceptions via `utils/console-guard.ts`.

## Rules the fixtures encode

- **Synthetic data only.** No real customers, no real contacts.
- **Nothing is hard-coded.** Company ids, assessment ids and draft ids come
  back from the API or the database at runtime.
- **Every run randomizes the website host, not just the company name.** Company
  dedup matches on host — a fixed host silently merges each run into the
  previous run's company and the score assertions drift. This cost a debugging
  session once; `fixtures/prospects.ts` derives both from one token.

## Gotchas

- **`--noproxy '*'` is mandatory for host curl.** A local proxy (Clash) hijacks
  `localhost`, so readiness polls fail without it. `scripts/up.sh` already
  does this; add it to any curl you write by hand. Chromium is unaffected.
- **`make e2e` rebuilds nothing in the dev stack** — the two are independent.
  The dev stack can keep running throughout.
- **Migrations do not run on container start.** `scripts/up.sh` applies them
  with a one-shot `docker compose run` before the service comes up; a bare
  `docker compose up backend-e2e` gives you an empty schema.
- **The suite is serial by design** (`workers: 1`). It shares one database and
  asserts exact scores; parallel runs interleave and produce confusing diffs.
- **Real mode checks only that a credential exists**, never its value. If
  `make e2e-real` reports a missing key, set `OPENAI_API_KEY` in the shell or
  the root `.env`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Provider mismatch: stack reports "openai" but the run expects "fake"` | A previous `make e2e-real` left the stack up. `make e2e-down`, then rerun. |
| `E2E backend unreachable at http://localhost:8001` | Stack not started (`make e2e-up`), or port 8001 taken by something else. |
| `Throwaway database importer_hunter_e2e is missing` | `up.sh` did not finish; rerun `make e2e-up` and read its output. |
| `relation "companies" does not exist` | Migrations were skipped — recreate with `make e2e-down && make e2e-up`. |
| Score assertions off by a few points | A fixture's signal kinds changed. Expected arithmetic is spelled out in `fixtures/prospects.ts`; update both together. |
