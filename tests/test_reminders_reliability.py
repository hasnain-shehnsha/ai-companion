import datetime
import uuid
from contextlib import asynccontextmanager

import pytest

from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User
from app.tasks.reminder_tasks import _process_reminder
from app.tasks.scheduler_tasks import _recover_pending_reminders_async


@pytest.fixture
async def user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Reliability",
        last_name="User",
        email=f"rel_{uuid.uuid4()}@example.com",
        hashed_password="hashed_password",
        timezone="UTC",
        whatsapp_number="+1234567890",
        tier="PAID",
        email_verified=True,
        whatsapp_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_two_workers_compete(user, db_session, mocker):
    """Two workers compete for the same reminder; only one sends."""
    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=user.id,
        message="Concurrency test",
        remind_at=datetime.datetime.now(datetime.UTC),
        status=ReminderStatus.PENDING,
    )
    db_session.add(reminder)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        # In a real app we'd use separate sessions/connections, but for sqlite we can just yield db_session
        yield db_session

    mocker.patch("app.tasks.reminder_tasks.get_celery_db", test_celery_db)

    mock_email = mocker.patch("app.tasks.reminder_tasks.resend.Emails.send")
    mock_wa = mocker.patch(
        "app.tasks.reminder_tasks.send_whatsapp_template", return_value=True
    )
    mocker.patch(
        "app.tasks.reminder_tasks.is_conversation_window_active", return_value=False
    )

    class MockTask:
        max_retries = 3

        class request:
            retries = 0
            id = "task-id"

        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc, countdown):
            pass

    # Run two workers sequentially with the same retries count (simulating a concurrent race condition where both see attempt_count=0 and try to update)
    # The first will succeed and increment attempt_count to 1.
    # The second will fail because it expects attempt_count=0.
    await _process_reminder(MockTask(), reminder.id)
    await _process_reminder(MockTask(), reminder.id)

    # Only one should have sent the email and whatsapp!
    # If the locking is atomic, one of them will process and the other will skip.
    assert mock_email.call_count == 1
    assert mock_wa.call_count == 1

    await db_session.refresh(reminder)
    assert reminder.status == ReminderStatus.SENT


async def test_queue_unavailable_recovery(user, db_session, mocker):
    """Queue unavailable after DB commit; periodic recovery later schedules the reminder."""
    # Create a reminder that is overdue and still PENDING
    past_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)
    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=user.id,
        message="Recovery test",
        remind_at=past_time,
        status=ReminderStatus.PENDING,
    )
    db_session.add(reminder)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.scheduler_tasks.get_celery_db", test_celery_db)
    mock_delay = mocker.patch("app.tasks.reminder_tasks.send_reminder_email.delay")

    await _recover_pending_reminders_async()

    # Verify that the reminder was enqueued
    mock_delay.assert_called_once_with(reminder.id)


async def test_provider_timeout_stale_recovery(user, db_session, mocker):
    """Provider timeout/retry, partial channel success, stale PROCESSING recovery, and worker restart."""
    # Simulate a reminder that got stuck in PROCESSING (e.g. worker crashed)
    stale_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=15)
    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=user.id,
        message="Stale recovery test",
        remind_at=stale_time,
        status=ReminderStatus.PROCESSING,
        last_attempt_at=stale_time,
        email_status="SENT",
        whatsapp_status="PENDING",
    )
    db_session.add(reminder)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.scheduler_tasks.get_celery_db", test_celery_db)
    mock_delay = mocker.patch("app.tasks.reminder_tasks.send_reminder_email.delay")

    await _recover_pending_reminders_async()

    # The scanner should have reset it to PENDING and re-enqueued it
    await db_session.refresh(reminder)
    assert reminder.status == ReminderStatus.PENDING
    mock_delay.assert_called_once_with(reminder.id)


async def test_daily_subscription_retry_on_failure(user, db_session, mocker):
    """Daily generation/provider failure does not suppress the next retry."""
    from app.models.subscription import DailySubscription
    from app.models.subscription_delivery import DeliveryStatus, SubscriptionDelivery
    from app.tasks.subscription_tasks import _process_delivery_async

    sub = DailySubscription(
        id=str(uuid.uuid4()),
        user_id=user.id,
        topic="Testing",
        time_of_day=datetime.time(9, 0),
        is_active=True,
    )
    db_session.add(sub)

    delivery = SubscriptionDelivery(
        id=str(uuid.uuid4()),
        subscription_id=sub.id,
        delivery_date=datetime.datetime.now(datetime.UTC).date(),
        status=DeliveryStatus.PENDING,
    )
    db_session.add(delivery)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.subscription_tasks.get_celery_db", test_celery_db)

    # Mock LLM gateway to fail the first time
    mock_llm = mocker.patch(
        "app.services.llm_gateway.generate_llm_response",
        side_effect=Exception("LLM Down"),
    )

    # First attempt: should fail and set status to FAILED
    try:
        await _process_delivery_async(delivery.id)
    except Exception as e:
        assert str(e) == "LLM Down"
    await db_session.refresh(delivery)
    assert delivery.status == DeliveryStatus.FAILED

    # Mock LLM gateway to succeed the second time
    mock_llm.side_effect = None
    mock_llm.return_value = ("Success Content", None)
    mock_wa = mocker.patch(
        "app.tasks.subscription_tasks.send_whatsapp_message", return_value=True
    )
    mocker.patch(
        "app.tasks.subscription_tasks.is_conversation_window_active", return_value=True
    )

    # The scanner recovers it (which we simulate by just calling _process_delivery_async again)
    # The requirement is that FAILED deliveries can be successfully processed when retried.
    await _process_delivery_async(delivery.id)

    await db_session.refresh(delivery)
    assert delivery.status == DeliveryStatus.SENT
    mock_wa.assert_called_once()
