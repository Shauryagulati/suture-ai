"""Celery app for Suture workers.

Broker: Redis at config.celery_broker_url.
Tasks live in services.workers.tasks. The beat schedule (defined here so
`celery -A services.workers.app beat` works in one command) wakes
check_overdue_tasks every 15 minutes — see Phase 8 for the task itself.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "suture",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.workers.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "check-overdue-tasks-every-15m": {
            "task": "services.workers.tasks.check_overdue_tasks",
            "schedule": crontab(minute="*/15"),
        },
    },
)
