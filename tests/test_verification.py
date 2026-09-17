import datetime
import uuid
from contextlib import asynccontextmanager

import pytest

from app.models.reminder import Reminder
from app.models.subscription import DailySubscription
from app.models.subscription_delivery import DeliveryStatus, SubscriptionDelivery
from app.models.user import User, UserTier
from app.tasks.reminder_tasks import _process_reminder
from app.tasks.subscription_tasks import _process_delivery_async


@pytest.fixture
async def unverified_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Unverified",
        last_name="User",
        email="unverified@example.com",
        whatsapp_number="+923001234568",
        hashed_password="dummy_password",
        tier=UserTier.PAID,
        email_verified=False,
        whatsapp_verified=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_unverified_daily_subscription_denied(
    unverified_user, db_session, mocker
):
    sub = DailySubscription(
        id=str(uuid.uuid4()),
        user_id=unverified_user.id,
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
    assert "WhatsApp number not verified" in delivery.failure_reason


async def test_unverified_reminder_denied(unverified_user, db_session, mocker):
    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=unverified_user.id,
        message="Test reminder",
        remind_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(reminder)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.reminder_tasks.get_celery_db", test_celery_db)

    mock_email = mocker.patch("app.tasks.reminder_tasks.resend.Emails.send")
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

    # Sending should not have been called
    mock_email.assert_not_called()
    mock_wa.assert_not_called()
    mock_template.assert_not_called()

    await db_session.refresh(reminder)
    assert reminder.email_status == "FAILED"
    assert reminder.whatsapp_status == "FAILED"
    assert "Address not verified" in reminder.failure_reason
    assert "Number not verified" in reminder.failure_reason
