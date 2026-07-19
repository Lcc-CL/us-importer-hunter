# US Importer Hunter

AI-powered sales intelligence for international freight forwarders —
automatically discover, analyze and prioritize US importers, and generate
personalized outreach emails.

**FastAPI · Python 3.12 · Next.js 16 · PostgreSQL · Redis · OpenAI**

## Quick start

```bash
cp .env.example .env          # Fake email provider works without an OpenAI key

# full stack (requires Docker)
docker compose up --build     # frontend :3000 · backend :8000 · docs :8000/docs

# or on the host
make infra                    # postgres + redis in Docker
make backend                  # FastAPI with hot reload
make frontend                 # Next.js dev server
```

Open <http://localhost:3000> for the single-page MVP flow. Submit a company with
real evidence sources, inspect the qualification and draft, approve it, then use
**Refresh result** (or reload the `?company_id=...` URL) to verify persistence.
The UI never sends email. Browser API access is configured once through
`NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

## Website research (v0.2.0 — Internal Beta)

Give the research panel a company name and its website; it fetches the site
safely, extracts evidence-backed claims, and waits for a human to accept, edit
or reject each one. Every claim carries the sentence that supports it and the
page it came from. Research never creates a Company, never scores, and never
sends email — accepted claims only fill the existing prospect form.

The panel is an internal testing surface: it is off unless
`NEXT_PUBLIC_ENABLE_RESEARCH=true`, and **the Research API must not be exposed
anonymously on the public internet**. Extraction defaults to a Fake provider;
a real model requires `RESEARCH_EXTRACTOR_PROVIDER=openai`.

> **Changing any `NEXT_PUBLIC_*` value requires rebuilding the frontend.**
> Next.js compiles these into the client bundle, so restarting the container
> is not enough — the old value is already baked in:
>
> ```bash
> docker compose build --no-cache frontend && docker compose up -d frontend
> ```
>
> This applies to `NEXT_PUBLIC_ENABLE_RESEARCH` and `NEXT_PUBLIC_API_BASE_URL`
> alike. Both are passed as build args and as runtime environment, so the dev
> and prod targets behave the same.

Validation and known limitations:
[docs/validation/](docs/validation/v0.2-real-company-evaluation.md) ·
[release notes](docs/release-notes.md).

## Documentation

- **[PROJECT.md](PROJECT.md)** — the project document: vision, MVP,
  architecture, workflow, sprints, progress, roadmap. **Start here.**
- [docs/](docs/) — detailed references: PRD, business domain, architecture,
  coding standards, agents, workflows, API, database, decision log (ADRs),
  roadmap.
