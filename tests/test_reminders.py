import datetime
import random
import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User
from app.tasks.reminder_tasks import _process_reminder


@pytest.fixture
async def tz_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email=f"tzuser_{uuid.uuid4()}@example.com",
        hashed_password=get_password_hash("password123"),
        timezone="Asia/Karachi",
        whatsapp_number=f"+92{random.randint(3000000000, 3999999999)}",
        tier="PAID",
        email_verified=True,
        whatsapp_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def get_token(async_client, email):
    response = await async_client.post(
        "/users/login",
        json={"email": email, "password": "password123"},
    )
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.text}")
    return response.json()["access_token"]


async def test_future_reminder(async_client, tz_user, mocker, db_session):
    token = await get_token(async_client, tz_user.email)

    # Mock Intent to return a SET_REMINDER intent
    mock_intent = mocker.patch("app.services.ai_service.analyze_intent")

    from app.services.intent_service import IntentResponse

    future_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)
    mock_intent.return_value = IntentResponse(
        intent="SET_REMINDER", datetime_iso=future_time, reminder_text="Buy milk"
    )

    response = await async_client.post(
        "/chat/",
        json={"message": "Remind me to buy milk in 2 hours"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "remind you to" in response.json()["response"]

    # Verify reminder was saved
    result = await db_session.execute(
        select(Reminder).where(Reminder.user_id == tz_user.id)
    )
    reminders = result.scalars().all()
    assert len(reminders) == 1
    assert reminders[0].message == "Buy milk"


async def test_invalid_datetime_intent(async_client, tz_user, mocker):
    token = await get_token(async_client, tz_user.email)

    # Analyze intent doesn't return datetime_iso (None)
    mock_intent = mocker.patch("app.services.ai_service.analyze_intent")

    from app.services.intent_service import IntentResponse

    mock_intent.return_value = IntentResponse(
        intent="SET_REMINDER", datetime_iso=None, reminder_text="Buy milk"
    )

    response = await async_client.post(
        "/chat/",
        json={"message": "Remind me to buy milk at invalid time"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    # Because datetime_iso is None, ai_service falls back to normal CHAT
    # which returns "Mock LLM response"
    assert response.json()["response"] == "Mock LLM response"


async def test_failed_deliveries(tz_user, db_session, mocker):
    # Test the Celery task directly for failed deliveries
    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=tz_user.id,
        message="Test reminder",
        remind_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(reminder)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.reminder_tasks.get_celery_db", test_celery_db)

    # Mock Resend to throw exception
    mocker.patch(
        "app.tasks.reminder_tasks.resend.Emails.send",
        side_effect=Exception("Email Down"),
    )

    # Mock WhatsApp to return False
    mocker.patch(
        "app.tasks.reminder_tasks.is_conversation_window_active", return_value=True
    )
    mocker.patch(
        "app.tasks.reminder_tasks.send_whatsapp_message",
        side_effect=Exception("WhatsApp Down"),
    )

    class MockTask:
        max_retries = 0

        class request:
            retries = 0

        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc, countdown):
            from celery.exceptions import Retry

            raise Retry("Retrying...")

    await _process_reminder(MockTask(), reminder.id)

    await db_session.refresh(reminder)
    assert reminder.email_status == "FAILED"
    assert reminder.whatsapp_status == "FAILED"
    assert reminder.status == ReminderStatus.FAILED
    assert "Email Down" in reminder.failure_reason
    assert "WhatsApp Down" in reminder.failure_reason


# --- Retry and Channel Logic Tests ---


@pytest.fixture
async def setup_delivery_test(db_session, tz_user):
    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=tz_user.id,
        message="Test channel retry logic",
        remind_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(reminder)
    await db_session.commit()

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    yield reminder, test_celery_db


async def test_email_success_whatsapp_fail_partial(setup_delivery_test, mocker):
    reminder, db_context = setup_delivery_test
    mocker.patch("app.tasks.reminder_tasks.get_celery_db", db_context)

    # Mock Email Success
    mocker.patch("app.tasks.reminder_tasks.resend.Emails.send", return_value=True)
    # Mock WhatsApp Failure
    mocker.patch(
        "app.tasks.reminder_tasks.send_whatsapp_message",
        side_effect=Exception("WhatsApp down"),
    )

    # Mock the Celery Task so we can intercept self.retry
    class MockTask:
        max_retries = 0

        class request:
            retries = 0

        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc, countdown):
            from celery.exceptions import Retry

            raise Retry("Retrying...")

    await _process_reminder(MockTask(), reminder.id)

    async with db_context() as db:
        await db.refresh(reminder)
        assert reminder.email_status == "SENT"
        assert reminder.whatsapp_status == "FAILED"
        assert reminder.status == ReminderStatus.PARTIALLY_SENT


async def test_whatsapp_success_email_fail_partial(setup_delivery_test, mocker):
    reminder, db_context = setup_delivery_test
    mocker.patch("app.tasks.reminder_tasks.get_celery_db", db_context)

    # Mock Email Failure
    mocker.patch(
        "app.tasks.reminder_tasks.resend.Emails.send",
        side_effect=Exception("Email down"),
    )
    # Mock WhatsApp Success
    mocker.patch("app.tasks.reminder_tasks.send_whatsapp_message", return_value=True)
    mocker.patch(
        "app.tasks.reminder_tasks.is_conversation_window_active", return_value=True
    )

    # Mock Celery Task
    class MockTask:
        max_retries = 0

        class request:
            retries = 0

        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc, countdown):
            from celery.exceptions import Retry

            raise Retry("Retrying...")

    await _process_reminder(MockTask(), reminder.id)

    async with db_context() as db:
        await db.refresh(reminder)
        assert reminder.email_status == "FAILED"
        assert reminder.whatsapp_status == "SENT"
        assert reminder.status == ReminderStatus.PARTIALLY_SENT


async def test_retry_skips_successful_channel(setup_delivery_test, mocker):
    reminder, db_context = setup_delivery_test
    mocker.patch("app.tasks.reminder_tasks.get_celery_db", db_context)

    mock_email = mocker.patch(
        "app.tasks.reminder_tasks.resend.Emails.send", return_value=True
    )
    mock_wa = mocker.patch(
        "app.tasks.reminder_tasks.send_whatsapp_message",
        side_effect=[Exception("WA down"), True],
    )
    mocker.patch(
        "app.tasks.reminder_tasks.is_conversation_window_active", return_value=True
    )

    class MockTask:
        max_retries = 1

        class request:
            retries = 0

        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc, countdown):
            self.request.retries += 1
            from celery.exceptions import Retry

            raise Retry("RETRYING")

    task_mock = MockTask()

    # First attempt
    try:
        await _process_reminder(task_mock, reminder.id)
    except Exception as e:
        assert str(e) == "RETRYING"

    async with db_context() as db:
        await db.refresh(reminder)
        assert reminder.email_status == "SENT"
        assert reminder.whatsapp_status == "FAILED"

    # Second attempt
    await _process_reminder(task_mock, reminder.id)

    async with db_context() as db:
        await db.refresh(reminder)
        assert reminder.email_status == "SENT"
        assert reminder.whatsapp_status == "SENT"
        assert reminder.status == ReminderStatus.SENT

    # Assert Email was only called once, WhatsApp called twice
    assert mock_email.call_count == 1
    assert mock_wa.call_count == 2


async def test_unverified_channels_gated_outbound_delivery(db_session, mocker):
    # Create an unverified user
    user = User(
        id=str(uuid.uuid4()),
        first_name="Unverified",
        last_name="User",
        email=f"unverified_{uuid.uuid4()}@example.com",
        hashed_password="password123",
        timezone="UTC",
        whatsapp_number=f"+92{random.randint(3000000000, 3999999999)}",
        tier="PAID",
        email_verified=False,
        whatsapp_verified=False,
    )
    db_session.add(user)

    reminder = Reminder(
        id=str(uuid.uuid4()),
        user_id=user.id,
        message="This should not send",
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

    class MockTask:
        max_retries = 0

        class request:
            retries = 0

        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc, countdown):
            from celery.exceptions import Retry

            raise Retry("Retrying...")

    try:
        await _process_reminder(MockTask(), reminder.id)
    except Exception as e:
        assert str(e) == "Retrying..."

    # Assert Email and WhatsApp were NOT called
    assert mock_email.call_count == 0
    assert mock_wa.call_count == 0

    # Verify reminder status
    await db_session.refresh(reminder)
    assert reminder.status == ReminderStatus.FAILED
    assert reminder.email_status == "FAILED"
    assert reminder.whatsapp_status == "FAILED"
    assert "not verified" in reminder.failure_reason.lower()
