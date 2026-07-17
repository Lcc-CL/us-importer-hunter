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

## Documentation

- **[PROJECT.md](PROJECT.md)** — the project document: vision, MVP,
  architecture, workflow, sprints, progress, roadmap. **Start here.**
- [docs/](docs/) — detailed references: PRD, business domain, architecture,
  coding standards, agents, workflows, API, database, decision log (ADRs),
  roadmap.
