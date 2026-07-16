# Decision Log

Architecture decisions are recorded as numbered ADRs in [ADR/](ADR/).
One decision per file; status is Accepted unless noted. To add one:
copy the format of an existing ADR, take the next number, link it here.

| # | Decision | Date |
|---|---|---|
| [0001](ADR/0001-monorepo.md) | Monorepo with apps/backend + apps/frontend | 2026-07-15 |
| [0002](ADR/0002-provider.md) | LLM provider abstraction (gateway + adapters) | 2026-07-15 |
| [0003](ADR/0003-workflow.md) | Workflow orchestration model (service / workflow / task) | 2026-07-15 |
| [0004](ADR/0004-events.md) | Event-driven stage coupling | 2026-07-15 |
| [0005](ADR/0005-memory-layer.md) | Memory as a standalone layer | 2026-07-15 |
| [0006](ADR/0006-declarative-specs.md) | Declarative specs as wiring source of truth | 2026-07-15 |
| [0007](ADR/0007-knowledge-base.md) | Knowledge base location and shape | 2026-07-15 |
| [0008](ADR/0008-prompt-versioning.md) | Prompt versioning in-repo | 2026-07-15 |
| [0009](ADR/0009-domain-discipline.md) | Domain layer discipline | 2026-07-15 |
| [0010](ADR/0010-repositories.md) | Repository pattern, no generic base | 2026-07-15 |
| [0011](ADR/0011-root-env.md) | Root .env as single source of truth | 2026-07-15 |
| [0012](ADR/0012-python-312.md) | Python 3.12 pinned | 2026-07-15 |
| [0013](ADR/0013-defer-celery-qdrant.md) | Defer Celery and Qdrant | 2026-07-15 |
| [0014](ADR/0014-lazy-infra-clients.md) | Lazy infra clients, observable readiness | 2026-07-15 |
| [0015](ADR/0015-domain-boundaries-and-events.md) | Domain boundaries, aggregates and domain events | 2026-07-15 |
| [0016](ADR/0016-domain-model-and-invariants.md) | Domain model: value objects, aggregates, invariants | 2026-07-15 |
| [0017](ADR/0017-domain-persistence-separation.md) | Domain–persistence separation: mappers, repositories, UoW | 2026-07-16 |
