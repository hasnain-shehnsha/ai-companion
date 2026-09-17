import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.celery_app import celery_app
from app.core.database import get_celery_db
from app.models.reminder import Reminder, ReminderStatus
from app.models.subscription import DailySubscription
from app.models.subscription_delivery import DeliveryStatus, SubscriptionDelivery
from app.models.user import User
from app.models.webhook_event import WebhookEvent, WebhookStatus

logger = logging.getLogger(__name__)


@celery_app.task
def process_daily_subscriptions():
    """
    Celery Beat task that runs every minute to check for daily subscriptions
    that should be enqueued for delivery at the current time."""
    from app.core.async_utils import run_async

    run_async(_process_subscriptions_async())


async def _process_subscriptions_async():
    try:
        from app.tasks.subscription_tasks import process_daily_delivery

        async with get_celery_db() as db:
            stmt = select(DailySubscription).where(DailySubscription.is_active == True)
            result = await db.execute(stmt)
            subscriptions = result.scalars().all()

            for sub in subscriptions:
                user_stmt = select(User).where(User.id == sub.user_id)
                user = (await db.execute(user_stmt)).scalar_one_or_none()

                if not user:
                    continue

                try:
                    tz = ZoneInfo(user.timezone)
                except ZoneInfoNotFoundError:
                    tz = ZoneInfo("UTC")

                now_local = datetime.now(tz)
                sub_time = sub.time_of_day

                # Check if it's the exact minute to trigger
                if (
                    sub_time.hour == now_local.hour
                    and sub_time.minute == now_local.minute
                ):
                    if sub.last_successful_delivery_date == now_local.date():
                        continue

                    # Attempt to insert a PENDING delivery for today using ON CONFLICT DO NOTHING
                    import uuid

                    delivery_id = str(uuid.uuid4())

                    insert_stmt = (
                        insert(SubscriptionDelivery)
                        .values(
                            id=delivery_id,
                            subscription_id=sub.id,
                            delivery_date=now_local.date(),
                            status=DeliveryStatus.PENDING,
                        )
                        .on_conflict_do_nothing(
                            index_elements=["subscription_id", "delivery_date"]
                        )
                        .returning(SubscriptionDelivery.id)
                    )

                    result = await db.execute(insert_stmt)
                    inserted_id = result.scalar_one_or_none()
                    await db.commit()

                    if inserted_id:
                        logger.info(
                            f"Enqueuing daily subscription delivery {inserted_id} for sub {sub.id}"
                        )
                        process_daily_delivery.delay(inserted_id)

    except Exception as e:
        logger.exception("Error in scheduler task")
        raise e


@celery_app.task
def recover_pending_deliveries():
    """
    Celery Beat task that runs every minute to scan for overdue PENDING/FAILED deliveries
    or stale PROCESSING deliveries."""
    from app.core.async_utils import run_async

    run_async(_recover_pending_deliveries_async())


async def _recover_pending_deliveries_async():
    try:
        from app.tasks.subscription_tasks import process_daily_delivery

        async with get_celery_db() as db:
            stale_threshold = datetime.now(UTC) - timedelta(minutes=5)

            # Reset stale PROCESSING
            stale_stmt = select(SubscriptionDelivery).where(
                SubscriptionDelivery.status == DeliveryStatus.PROCESSING,
                SubscriptionDelivery.last_attempt_at <= stale_threshold,
            )
            stale_result = await db.execute(stale_stmt)
            stale_deliveries = stale_result.scalars().all()

            for stale in stale_deliveries:
                logger.warning(f"Resetting stale processing delivery {stale.id}")
                await db.execute(
                    update(SubscriptionDelivery)
                    .where(SubscriptionDelivery.id == stale.id)
                    .values(status=DeliveryStatus.PENDING)
                )

            if stale_deliveries:
                await db.commit()

            # Retry PENDING or FAILED
            retry_stmt = select(SubscriptionDelivery).where(
                SubscriptionDelivery.status.in_(
                    [DeliveryStatus.PENDING, DeliveryStatus.FAILED]
                ),
                SubscriptionDelivery.delivery_date
                == datetime.now(UTC).date(),  # Only retry today's
            )
            result = await db.execute(retry_stmt)
            deliveries = result.scalars().all()

            for delivery in deliveries:
                logger.info(f"Recovering pending/failed delivery {delivery.id}")
                process_daily_delivery.delay(delivery.id)

    except Exception as e:
        logger.exception("Error in recover_pending_deliveries task")
        raise e


@celery_app.task
def recover_pending_reminders():
    """
    Celery Beat task that runs every minute to scan for overdue PENDING reminders
    that failed to enqueue originally due to broker outages or crashes."""
    from app.core.async_utils import run_async

    run_async(_recover_pending_reminders_async())


async def _recover_pending_reminders_async():
    try:
        # Import inside function to avoid any potential circular imports
        from datetime import datetime, timedelta

        from sqlalchemy import update
        from sqlalchemy.sql import func

        from app.tasks.reminder_tasks import send_reminder_email

        async with get_celery_db() as db:
            # 1. Recover stale PROCESSING tasks (worker crashed post-claim)
            stale_threshold = datetime.now(UTC) - timedelta(minutes=5)
            stale_stmt = select(Reminder).where(
                Reminder.status == ReminderStatus.PROCESSING,
                Reminder.last_attempt_at <= stale_threshold,
            )
            stale_result = await db.execute(stale_stmt)
            stale_reminders = stale_result.scalars().all()

            for stale in stale_reminders:
                logger.warning(
                    "Resetting stale processing reminder",
                    extra={"reminder_id": stale.id},
                )
                await db.execute(
                    update(Reminder)
                    .where(Reminder.id == stale.id)
                    .values(status=ReminderStatus.PENDING)
                )

            if stale_reminders:
                await db.commit()

            # 2. Recover overdue PENDING tasks, or PARTIALLY_SENT tasks that crashed before retrying
            stmt = select(Reminder).where(
                (Reminder.status == ReminderStatus.PENDING)
                | (
                    (Reminder.status == ReminderStatus.PARTIALLY_SENT)
                    & (Reminder.attempt_count <= 3)
                ),
                Reminder.remind_at <= func.now(),
            )
            result = await db.execute(stmt)
            reminders = result.scalars().all()

            for reminder in reminders:
                logger.info(
                    f"Recovering reminder {reminder.id} (status: {reminder.status})"
                )
                # Enqueue the task immediately since it's already overdue or stuck
                send_reminder_email.delay(reminder.id)

    except Exception as e:
        logger.exception("Error in recover_pending_reminders task")
        raise e


@celery_app.task
def recover_webhook_events():
    """
    Celery Beat task that runs every minute to scan for stuck WebhookEvents
    that failed to enqueue originally due to broker outages or crashes."""
    from app.core.async_utils import run_async

    run_async(_recover_webhook_events_async())


async def _recover_webhook_events_async():
    try:
        from datetime import datetime, timedelta

        from sqlalchemy import update

        from app.tasks.webhook_tasks import process_whatsapp_webhook

        async with get_celery_db() as db:
            # 1. Recover stale PROCESSING tasks (worker crashed post-claim)
            stale_threshold = datetime.now(UTC) - timedelta(minutes=5)
            stale_stmt = select(WebhookEvent).where(
                WebhookEvent.status == WebhookStatus.PROCESSING,
                WebhookEvent.last_attempt_at <= stale_threshold,
            )
            stale_result = await db.execute(stale_stmt)
            stale_events = stale_result.scalars().all()

            for stale in stale_events:
                logger.warning(
                    "Resetting stale processing webhook", extra={"msg_id": stale.id}
                )
                await db.execute(
                    update(WebhookEvent)
                    .where(WebhookEvent.id == stale.id)
                    .values(status=WebhookStatus.RECEIVED)
                )

            if stale_events:
                await db.commit()

            # 2. Recover overdue RECEIVED tasks (broker dropped them before claim)
            overdue_stmt = select(WebhookEvent).where(
                WebhookEvent.status == WebhookStatus.RECEIVED,
                WebhookEvent.created_at <= stale_threshold,
            )
            result = await db.execute(overdue_stmt)
            events = result.scalars().all()

            for event in events:
                logger.info(
                    "Recovering overdue pending webhook", extra={"msg_id": event.id}
                )
                process_whatsapp_webhook.delay(event.id)

    except Exception as e:
        logger.exception("Error in recover_webhook_events task")
        raise e
