"""Task aggregate persistence: execution state + append-only attempts.

A partial unique index enforces the domain's idempotency rule at the
database level: at most one active task per idempotency key.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_tasks_attempts_non_negative"),
        CheckConstraint("max_retries >= 0", name="ck_tasks_max_retries_non_negative"),
        Index("ix_tasks_status", "status"),
        Index(
            "uq_tasks_active_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where="status IN ('created', 'running')",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    goal: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column()
    max_retries: Mapped[int] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    attempt_history: Mapped[list["TaskAttemptModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TaskAttemptModel.number"
    )


class TaskAttemptModel(Base):
    __tablename__ = "task_attempts"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
