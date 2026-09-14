import pytest
import uuid
import datetime
from contextlib import asynccontextmanager
from app.models.user import User
from app.models.reminder import Reminder, ReminderStatus
from app.core.security import get_password_hash
from sqlalchemy import select
from app.tasks.reminder_tasks import _process_reminder


@pytest.fixture
async def tz_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email="tzuser@example.com",
        hashed_password=get_password_hash("password123"),
        timezone="Asia/Karachi",
        whatsapp_number="+923001234567",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def get_token(async_client, email):
    response = await async_client.post(
        "/users/login",
        json={"email": email, "password": "password123"},
    )
    return response.json()["access_token"]


async def test_future_reminder(async_client, tz_user, mocker, db_session):
    token = await get_token(async_client, tz_user.email)

    # Mock Intent to return a SET_REMINDER intent
    mock_intent = mocker.patch("app.services.ai_service.analyze_intent")

    from app.services.intent_service import IntentResponse

    future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        hours=2
    )
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
        remind_at=datetime.datetime.now(datetime.timezone.utc),
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
        "app.tasks.reminder_tasks.send_whatsapp_message",
        side_effect=Exception("WhatsApp Down"),
    )

    await _process_reminder(reminder.id)

    await db_session.refresh(reminder)
    assert reminder.email_status == "FAILED"
    assert reminder.whatsapp_status == "FAILED"
    assert reminder.status == ReminderStatus.FAILED
    assert "Email Down" in reminder.failure_reason
    assert "WhatsApp Down" in reminder.failure_reason
