"""Task domain (Execution context): supervised pipeline runs."""

from app.domain.task.aggregate import DEFAULT_MAX_RETRIES, Task, TaskAttempt, TaskStatus

__all__ = ["DEFAULT_MAX_RETRIES", "Task", "TaskAttempt", "TaskStatus"]
