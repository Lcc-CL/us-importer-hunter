# ADR-0007: Knowledge base location and shape

Date: 2026-07-15 · Status: Accepted

## Context

RAG needs a curated corpus (industry, shipping, logistics, sales,
emails, customer, faq). It is content, not code — but it must ship in
the backend Docker image, whose build context is `apps/backend`.

## Decision

Corpus lives at `apps/backend/knowledge/` — inside the build context,
outside the `app` package. Plain Markdown, one topic per file,
kebab-case names; many small files over one large file (chunking
quality). The rag service ingests from here (embedding → Qdrant, later
sprint).

## Consequences

- Editing knowledge never requires a code change; re-ingestion picks it up.
- Corpus collection can start before any RAG code exists.
