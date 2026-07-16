# US Importer Hunter

AI-powered sales intelligence for international freight forwarders —
automatically discover, analyze and prioritize US importers, and generate
personalized outreach emails.

**FastAPI · Python 3.12 · Next.js 16 · PostgreSQL · Redis · OpenAI**

## Quick start

```bash
cp .env.example .env          # fill in OPENAI_API_KEY and passwords

# full stack (requires Docker)
make up                       # frontend :3000 · API docs :8000/docs

# or on the host
make infra                    # postgres + redis in Docker
make backend                  # FastAPI with hot reload
make frontend                 # Next.js dev server
```

## Documentation

- **[PROJECT.md](PROJECT.md)** — the project document: vision, MVP,
  architecture, workflow, sprints, progress, roadmap. **Start here.**
- [docs/](docs/) — detailed references: PRD, business domain, architecture,
  coding standards, agents, workflows, API, database, decision log (ADRs),
  roadmap.
