"""Declarative base shared by all ORM models.

Model modules live in app.database.models and are registered there;
Alembic's env.py imports that package to populate the metadata.
"""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class TimestampMixin:
    """Adds created_at / updated_at columns maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
