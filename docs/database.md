# Database

PostgreSQL 16 · SQLAlchemy 2.x (async, asyncpg) · Alembic migrations.

## Layout

```
app/database/
├── base.py          # DeclarativeBase + TimestampMixin
├── session.py       # engine / session factories (created in app lifespan)
├── models/          # ORM models — every module registered in models/__init__.py
├── repositories/    # the only place raw queries live
├── seed/            # demo/test/init datasets (demo_company, demo_contact, ...)
└── migrations/      # Alembic (async env; URL from app settings, not ini)
```

## Conventions

- Models: SQLAlchemy 2.x style — `Mapped[]` / `mapped_column()`; inherit
  `Base`, add `TimestampMixin` for created_at/updated_at.
- Every model module must be imported in `models/__init__.py`, otherwise
  Alembic autogenerate will not see it.
- Repositories take an `AsyncSession` via constructor injection and return
  ORM models or typed schemas — never raw rows. Services and tools depend
  on repositories, not sessions.
- No table without a migration; no manual schema changes.

## Commands

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
# or from repo root: make revision m="..." && make migrate
```

## Schema

No tables yet — first models (`Company`, `Contact`) land in Sprint 2.
