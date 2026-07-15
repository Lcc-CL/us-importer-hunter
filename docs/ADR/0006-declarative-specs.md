# ADR-0006: Declarative specs as wiring source of truth

Date: 2026-07-15 · Status: Accepted

## Context

Agent/tool/workflow wiring and the Company entity shape need a single
place to review and evolve, independent of implementation detail.

## Decision

`apps/backend/specs/` holds YAML specifications (agent.yaml,
workflow.yaml, tool.yaml, company.yaml). Specs update first, code
follows; TBD fields mirror the open questions in docs/prd.md.

## Consequences

- Design review happens on YAML diffs, not code archaeology.
- Drift between spec and code is a defect.
