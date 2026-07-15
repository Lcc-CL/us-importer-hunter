"""Repositories: the only place raw queries live.

Rules:
- Repositories receive an AsyncSession via constructor injection.
- They return ORM models or typed schemas — never raw rows.
- Services and tools depend on repositories, not on sessions directly.
"""
