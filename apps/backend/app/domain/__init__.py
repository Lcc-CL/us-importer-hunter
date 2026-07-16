"""Domain layer: pure business entities, value objects and rules.

Framework-free by design — no FastAPI, SQLAlchemy, Redis, Celery, LLM
SDKs, HTTP clients or repositories (enforced by tests/domain/test_purity.py).

Layout:
- values.py      immutable value objects (CompanyName, OpportunityScore, ...)
- exceptions.py  DomainError hierarchy
- events.py      immutable domain events (facts, past tense)
- services.py    domain service protocols (implemented in app/services)
- clock.py       UTC-aware time helpers
- company/ opportunity/ outreach/ task/   the four aggregates (ADR-0015)
- contact/ crm/ email/                    entity/rule homes (see their docstrings)
"""
