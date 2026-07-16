"""Task aggregate ↔ persistence mapping."""

from app.database.models.task import TaskAttemptModel, TaskModel
from app.domain.task import Task, TaskAttempt, TaskStatus
from app.domain.values import IdempotencyKey


class TaskMapper:
    @staticmethod
    def to_model(task: Task) -> TaskModel:
        return TaskModel(
            id=task.id,
            goal=task.goal,
            idempotency_key=task.idempotency_key.value,
            status=task.status.value,
            attempts=task.attempts,
            max_retries=task.max_retries,
            started_at=task.started_at,
            finished_at=task.finished_at,
            error=task.error,
            created_at=task.created_at,
            attempt_history=[
                TaskAttemptModel(
                    task_id=task.id,
                    number=attempt.number,
                    started_at=attempt.started_at,
                    finished_at=attempt.finished_at,
                    error=attempt.error,
                )
                for attempt in task.attempt_history
            ],
        )

    @staticmethod
    def to_domain(model: TaskModel) -> Task:
        task = Task(
            id=model.id,
            goal=model.goal,
            idempotency_key=IdempotencyKey(model.idempotency_key),
            max_retries=model.max_retries,
            created_at=model.created_at,
        )
        task._status = TaskStatus(model.status)
        task._attempts = model.attempts
        task._started_at = model.started_at
        task._finished_at = model.finished_at
        task._error = model.error
        task._attempt_history = [
            TaskAttempt(
                number=row.number,
                started_at=row.started_at,
                finished_at=row.finished_at,
                error=row.error,
            )
            for row in model.attempt_history
        ]
        return task
