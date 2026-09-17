from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.reminder_tasks",
        "app.tasks.scheduler_tasks",
        "app.tasks.webhook_tasks",
        "app.tasks.subscription_tasks",
        "app.tasks.memory_tasks",
        "app.tasks.usage_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=2,  # Limit concurrency to 2 to avoid exhausting Supabase PgBouncer connections
    beat_schedule={
        "process-daily-subscriptions-every-minute": {
            "task": "app.tasks.scheduler_tasks.process_daily_subscriptions",
            "schedule": crontab(minute="*"),
        },
        "recover-pending-deliveries-every-minute": {
            "task": "app.tasks.scheduler_tasks.recover_pending_deliveries",
            "schedule": crontab(minute="*"),
        },
        "recover-pending-reminders-every-minute": {
            "task": "app.tasks.scheduler_tasks.recover_pending_reminders",
            "schedule": crontab(minute="*"),
        },
        "recover-webhook-events-every-minute": {
            "task": "app.tasks.scheduler_tasks.recover_webhook_events",
            "schedule": crontab(minute="*"),
        },
    },
)

from celery.signals import worker_process_init


@worker_process_init.connect
def init_worker(**kwargs):
    from app.services.memory_service import setup_memory_service

    setup_memory_service()
