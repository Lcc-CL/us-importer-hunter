# ADR-0008: Prompt versioning in-repo

Date: 2026-07-15 · Status: Accepted

## Context

Prompt changes silently alter agent behavior; failed runs must be
attributable to the exact prompt version that produced them.

## Decision

Active prompts live in `app/prompts/<agent>/`; shared system prompts
and fragments in `app/prompts/shared/` (composed, never duplicated).
Superseded versions are archived to
`app/prompts/versions/<agent>/<name>.v<N>.md`. Tracing spans carry the
prompt version (see observability layer).

## Consequences

- Reproducible runs, diffable prompts, rollback without external tools.
- Structure maps cleanly onto a prompt-management platform later.
