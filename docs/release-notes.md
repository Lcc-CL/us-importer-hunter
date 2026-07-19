# Release Notes

## v0.1.1 — 2026-07-19

Two things ship together: a scoring defect that made the product unusable for
its actual users, and the test infrastructure that would have caught it.

### Fixed

**Chinese signals scored zero (P0).** The deterministic scorer recognized a
scoring dimension only by searching the signal text for English keywords, so a
prospect described in Chinese scored on at most three of eight dimensions —
and those three matched by coincidence, because their English *kind* prefix
(`import_activity`, `china_dependency`, `growth`) happens to contain a detector
keyword. Four dimensions (`shipping_fit`, `cargo_value_potential`,
`company_scale`, `logistics_complexity`) scored 0 no matter what evidence
existed. The score was capped below the qualification bar, so every
Chinese-language prospect settled at REVIEW and no email draft was ever
generated for one.

The scorer now resolves the dimension from the structured `"<kind>: …"` prefix
through an alias table, falling back to the existing keyword detectors when the
kind is unrecognized so legacy free-text signals still score. Qualification
thresholds, dimension weights, the database schema, the opportunity state
machine and the email-generation gate are all unchanged.

Measured on the reported company, re-analyzed against its already-stored
signals: score 39.5 → **70.5**, completeness 0.55 → **1.00**, REVIEW →
**QUALIFIED**, priority low → **high**, zero drafts → **one generated draft**.

### Added

- **Simplified Chinese UI, English toggle.** The interface now defaults to
  Chinese for its target users (freight-forwarder sales in China), with an
  English switch that persists across reloads. One translation dictionary, no
  duplicated pages. Database and API enums stay English; only display is
  translated.
- **Signal type is a dropdown.** Free-text kinds were the reason a typo
  (`ogistics_complexity`) could silently score zero. The field now offers the
  eight canonical kinds with localized labels and submits fixed English enums.
  Legacy stored values still render with their canonical meaning, and an
  unrecognized value is shown explicitly as "未知信号类型" rather than dropped.
- **Live provider badge.** The header reads `GET /api/v1/health/runtime` and
  shows 演示模式 (Fake) or 真实 AI (live) with the model name. The endpoint
  returns only provider, model and environment — never a credential or an
  endpoint URL.
- **Browser E2E regression** (`make e2e`). Runs the qualified path, the review
  path, i18n persistence and provider/secret checks against an isolated stack
  on its own database, using the Fake provider so it costs nothing.
  `make e2e-real` exercises one draft through the live provider. See
  `e2e/README.md`.

### Changed

- The draft notice no longer says "no email has been sent". It now states what
  the product does: drafts are generated and approved here, never sent
  automatically.

### Known limitations

- Signal kinds are still not validated at ingestion. The dropdown prevents bad
  input going forward, but stored rows with a malformed kind remain unscored.
- Company deduplication matches on website host, so a synthetic company sharing
  a real company's domain merges into it. This is how `[TEST ONLY]` rows
  entered one production record.
- The live-provider path is exercised through an OpenAI-compatible gateway;
  output quality via `api.openai.com` has not been separately measured.
