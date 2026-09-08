from celery import Celery
from app.core.config import settings

from celery.schedules import crontab

celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.reminder_tasks", "app.tasks.scheduler_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "process-daily-subscriptions-every-minute": {
            "task": "app.tasks.scheduler_tasks.process_daily_subscriptions",
            "schedule": crontab(minute="*"),
        },
    },
)
