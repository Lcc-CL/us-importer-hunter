# Release Notes

## v0.2.0 — Internal Beta — 2026-07-19

The website research agent: point it at a US importer's own site and it returns
evidence-backed claims a human reviews before anything enters the pipeline. It
never writes a Company, never scores, never sends.

### Added

**Website research agent.** Safe fetching (SSRF guard, robots, byte/time
budgets), deterministic page ranking, HTML cleaning, and a real LLM extractor
(`website-research-v1`) that proposes claims — each carrying the kind, the
verbatim sentence supporting it, the page URL it came from, and a confidence.

**Anti-hallucination gate.** Every proposed claim is checked against what was
actually fetched: kind whitelist, source URL fetched by this run, page belongs
to this run, evidence snippet is a real substring of the cleaned text,
confidence within 0–1. Failures are discarded with a recorded warning, never
downgraded into a weak signal.

**Human review and promotion.** Claims arrive pending. Accept, edit or reject
each one; the decision is recorded — rejections included — and accepted claims
fill the existing prospect form without submitting it.

**Unknown dimensions are persisted.** Dimensions with no supporting evidence
are named and survive a reload, so a saved run can say "we looked and found
nothing" rather than appearing never to have considered them. Unknown is never
a negative signal and never reaches scoring.

### Validation

Ten real US importers across five categories, one LLM request each: 10/10 safe
completions, 100% evidence localisation, 100% source-URL verification, **zero
fabricated facts**, 85.7% direct accept rate. Grainger returned zero claims and
eight unknown dimensions from a thin page — refusing to invent is the designed
behaviour. Full data: [docs/validation/](validation/v0.2-real-company-evaluation.md).

### Changed

- Extraction context budget is allocated in page-rank order rather than split
  evenly, and capped at 18,000 characters — a 25% reduction with no loss of
  validated claims.
- `clean_html` collapses repeated lines and drops cookie/legal chrome.
  `char_count` therefore counts deduplicated text: a page repeating one
  sentence six times now reads as thin, because repetition is not content.

### Known limitations

See [Known limitations](#known-limitations-v020) below.

<a id="known-limitations-v020"></a>
### Known limitations (v0.2.0)

- **The Research API must not be exposed anonymously on the public internet.**
  It is an authenticated internal surface only (ADR-0026).
- **Connection-level DNS/IP pinning is not implemented.** A residual DNS-rebinding
  window remains; the deployment constraint above is what closes it.
- **The validated provider is a third-party OpenAI-compatible gateway**
  (`gpt-5.6-terra`). The official `api.openai.com` endpoint has not been
  cost-validated, so the token figures here do not transfer to it.
- **A company website cannot prove import records.** Volumes, customs history
  and supplier identities are not verifiable from a marketing site.
- **Most `china_dependency` dimensions stay Unknown.** Nine of ten evaluated
  companies disclosed nothing about sourcing origin. This needs a customs data
  source, not prompt tuning.
- **Every claim requires human review.** Nothing is promoted automatically.
- **No email is sent, ever.** Drafts wait for a human.
- **JS-heavy sites may need browser rendering.** They return `needs_browser`
  rather than silently empty results; headless rendering is out of scope.
- **`reviewer_name` is not connected to a real identity system.** It is an
  unauthenticated local operator label.

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
