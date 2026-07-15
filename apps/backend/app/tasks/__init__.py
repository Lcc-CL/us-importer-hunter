"""Tasks layer: queue-executed entry points (Celery, later sprint).

Workers execute these directly. A task is a thin wrapper — deserialize
arguments, invoke a workflow or service, persist/report the result.
Business orchestration stays in workflows; task modules never contain it.

Task definitions land together with the Celery dependency; module
docstrings below record what each task will wrap.
"""
