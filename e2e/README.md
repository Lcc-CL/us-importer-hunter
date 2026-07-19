# Browser E2E regression

Playwright suite that drives the real application — UI, API and database —
against an **isolated** stack, so runs never touch the dev database.

| | dev stack | e2e stack |
|---|---|---|
| backend | `:8000` | `:8001` |
| frontend | `:3000` | `:3001` |
| database | `importer_hunter` | `importer_hunter_e2e` (created, then dropped) |
| provider | whatever `.env` says | `fake` unless you ask otherwise |

## Usage

```bash
make e2e          # Fake provider, whole suite, no LLM cost   (default)
make e2e-real     # one draft through the live provider
make e2e-up       # start the stack and leave it up (debugging)
make e2e-down     # stop it and drop the database
make e2e-report   # open the last HTML report
```

`make e2e` is self-contained: it installs dependencies, recreates the database,
applies migrations, starts containers, runs the suite and tears everything down
— including when the suite fails.

Reports land in `playwright-report/`; failure screenshots and traces in
`test-results/`. Both are gitignored.

## Layout

```
fixtures/prospects.ts    synthetic payloads + the expected score arithmetic
utils/api.ts             typed client for analyze / detail / runtime
utils/db.ts              psql assertions against the throwaway database
utils/form.ts            prospect-form driver
utils/console-guard.ts   duplicate-key / page-exception detector
global-setup.ts          pre-flight: stack up, right provider, right database
scripts/up.sh            create db → migrate → start → wait for both tiers
scripts/down.sh          remove containers → drop database
```

## Conventions

- Synthetic data only — never real customers or contacts.
- No hard-coded database ids; everything is read back at runtime.
- Each run randomizes the **website host** as well as the company name, because
  company deduplication matches on host.
- Expected scores are written down in `fixtures/prospects.ts`. If you change a
  fixture's signals, update the expectation in the same commit.

For agent-facing instructions see `.claude/skills/mvp-ui-regression/SKILL.md`.
