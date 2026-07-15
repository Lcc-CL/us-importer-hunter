# Agents

Four agents, each an LLM reasoning unit with typed (Pydantic) outputs.
Agents never call the database — data access goes through `app/tools/`.
All LLM calls go through the `llm` service, never the SDK directly.

| Agent | Package | Responsibility | Prompts |
|---|---|---|---|
| Planner | `app/agents/planner/` | Decompose a user goal into an executable research plan | `prompts/planner/` |
| Research | `app/agents/research/` | Discover & analyze US importers via tools | `prompts/research/` |
| Sales | `app/agents/sales/` | Generate personalized outreach emails from analysis | `prompts/sales/` |
| Report | `app/agents/report/` | Aggregate & prioritize findings into a final report | `prompts/summary/` |

## Main chain

```
user goal → Planner → Research (× N companies) → Sales → Report
```

Orchestrated by `app/workflows/` (see workflow.md). Agents are stateless;
anything persistent goes through services/repositories.

## Testing

Each agent must be unit-testable with a mocked llm service and mocked
tools — no network, no database.
