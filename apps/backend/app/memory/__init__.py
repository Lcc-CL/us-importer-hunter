"""Memory layer: what the system remembers across agent runs.

A standalone layer (deliberately not a service) — memory will grow its
own storage mix and policies. Agents and workflows read/write memory
through the interfaces defined here; backing stores (Redis, PostgreSQL,
Qdrant) stay swappable behind them.

Distinct from knowledge/ (curated static corpus): memory is what the
system accumulates and recalls on its own while running.
"""
