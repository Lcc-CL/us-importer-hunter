# Agents

Four agents, each an LLM reasoning unit with typed (Pydantic) outputs.
Agents never call the database — data access goes through `app/tools/`.
All LLM calls go through the `llm` service, never the SDK directly.

| Agent | Package | Responsibility | Bounded context | Prompts |
|---|---|---|---|---|
| Planner | `app/agents/planner/` | Decompose a user goal into an executable research plan (a Task's blueprint) | Execution | `prompts/planner/` |
| Research | `app/agents/research/` | Discover & analyze US importers via tools | Discovery (facts) + Intelligence (analysis input) | `prompts/research/` |
| Sales | `app/agents/sales/` | Generate drafts inside an Outreach conversation | Outreach | `prompts/sales/` |
| Report | `app/agents/report/` | Aggregate findings & outcomes into funnel reports | cross-context (read-only) | `prompts/summary/` |

Agents work *within* domain boundaries (docs/business-domain.md): the
research agent may enrich a Company but never sets a score (scoring
service does, via the Opportunity aggregate); the sales agent generates
EmailDrafts only through the Outreach root and never sends anything.

Scoring today is the **deterministic placeholder** mvp-deterministic-v1
behind the replaceable `OpportunityScoringService` protocol (ADR-0020) —
no LLM involved and not fit for real sales decisions. When agents land,
the research agent's job is to *feed better facts and evidence* into
that same interface, not to score.

## Main chain

```
user goal → Planner → Research (× N companies) → Sales → Report
```

Orchestrated by `app/workflows/` (see workflow.md). Agents are stateless;
anything persistent goes through services/repositories.

## Testing

Each agent must be unit-testable with a mocked llm service and mocked
tools — no network, no database.
