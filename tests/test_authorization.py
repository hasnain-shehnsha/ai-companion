import datetime
import uuid
from contextlib import asynccontextmanager

import pytest

from app.api.endpoints.whatsapp import process_message
from app.models.reminder import Reminder
from app.models.subscription import DailySubscription
from app.models.subscription_delivery import DeliveryStatus, SubscriptionDelivery
from app.models.user import User
from app.tasks.reminder_tasks import _process_reminder
from app.tasks.subscription_tasks import _process_delivery_async


@pytest.fixture
async def free_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Free",
        last_name="User",
        email="freeuser@example.com",
        whatsapp_number="+923001234567",
        tier="FREE",
        hashed_password="dummy_password",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_free_user_whatsapp_webhook_denied(free_user, db_session, mocker):
    mock_send = mocker.patch("app.api.endpoints.whatsapp.send_whatsapp_message")

    # Process webhook message
    await process_message("923001234567", "Hello", db=db_session)

    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert "upgrade to Premium" in args[1]


async def test_free_user_daily_subscription_denied(free_user, db_session, mocker):
    sub = DailySubscription(
        id=str(uuid.uuid4()),
        user_id=free_user.id,
        topic="Motivation",
        time_of_day=datetime.time(10, 0, tzinfo=datetime.UTC),
    )
    db_session.add(sub)
    await db_session.commit()

    delivery = SubscriptionDelivery(
        id=str(uuid.uuid4()),
        subscription_id=sub.id,
        delivery_date=datetime.date.today(),
        status=DeliveryStatus.PENDING,
    )
    db_session.add(delivery)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.subscription_tasks.get_celery_db", test_celery_db)
    mock_generate = mocker.patch(
        "app.tasks.subscription_tasks.client.chat.completions.create"
    )

    await _process_delivery_async(delivery.id)

    # Should have failed authorization before calling LLM
    mock_generate.assert_not_called()

    await db_session.refresh(delivery)
    assert delivery.status == DeliveryStatus.FAILED
    assert "Premium entitlement required" in delivery.failure_reason


async def test_free_user_whatsapp_reminder_denied(free_user, db_session, mocker):
    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=free_user.id,
        message="Free reminder",
        remind_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(reminder)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.reminder_tasks.get_celery_db", test_celery_db)

    # Mock Email Success so we don't try to send a real email
    mocker.patch("app.tasks.reminder_tasks.resend.Emails.send", return_value=True)
    mock_wa = mocker.patch("app.tasks.reminder_tasks.send_whatsapp_message")
    mock_template = mocker.patch("app.tasks.reminder_tasks.send_whatsapp_template")

    class MockTask:
        max_retries = 0

        class request:
            retries = 0

        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc, countdown):
            pass

    await _process_reminder(MockTask(), reminder.id)

    # WhatsApp sending should not have been called
    mock_wa.assert_not_called()
    mock_template.assert_not_called()

    await db_session.refresh(reminder)
    # The overall status might be PARTIALLY_SENT (if email sent) or FAILED.
    # But whatsapp_status MUST be FAILED.
    assert reminder.whatsapp_status == "FAILED"
    assert "Premium entitlement required" in reminder.failure_reason
