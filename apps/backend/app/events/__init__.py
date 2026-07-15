"""Events layer: publish/subscribe decoupling between pipeline stages.

Rule: a stage never calls the next stage directly. It publishes a typed
event; subscribers react.

    research agent finishes
        → publish ResearchCompleted (typed event schema)
        → sales agent's subscriber picks it up

Planned shape (implemented when the first two stages actually connect):
- events are Pydantic schemas (past-tense names: ResearchCompleted,
  EmailDrafted, ...)
- an EventBus interface with an in-process implementation for MVP;
  Redis pub/sub or a broker can replace it later without touching
  publishers or subscribers.

As the number of agents grows, orchestration shifts from imperative
workflow steps to event-driven wiring.
"""
