# PRD — US Importer Hunter

## What

An AI-powered sales intelligence platform for international freight forwarders.

## Problem

Freight forwarders prospect US importers manually: finding companies,
judging whether they ship enough volume on relevant lanes, and writing
outreach — slow, unsystematic, low hit-rate.

## Target users

International freight forwarders (sales / business development roles).

## Main goal

Automatically discover, analyze and prioritize US importers.

## MVP scope

1. **Search** companies (US importers) across data sources.
2. **Analyze** logistics opportunities per company.
3. **Generate** personalized outreach emails.

## Data sources

| Source | Purpose | Access method |
|---|---|---|
| ImportYeti | US customs / bill-of-lading data — importer discovery | **TBD** (no official public API; scraping has ToS risk) |
| Google | Company discovery & enrichment | TBD |
| Company websites | Content extraction for personalization | HTTP fetch / browser |
| LinkedIn | Decision-maker contacts | **TBD** (ToS risk; alternatives under consideration) |

## Out of scope for MVP

- Auth / multi-tenancy (TBD — currently assumed single-user)
- Email sending infrastructure (drafts only, unless decided otherwise)
- Billing

## Open product questions

- ImportYeti access method and legality of LinkedIn automation.
- Scoring dimensions for "logistics opportunity" (volume, lanes, current
  forwarder, switching signals?).
- Where contact emails come from (email-finding service?).
