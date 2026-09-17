from sqlalchemy import select

from app.models.reminder import Reminder
from app.models.user import User


async def test_register_with_valid_timezone(async_client, db_session):
    response = await async_client.post(
        "/users/",
        json={
            "first_name": "Timezone",
            "last_name": "User",
            "email": "tz_register@example.com",
            "whatsapp_number": "+923001112223",
            "password": "password123",
            "timezone": "Asia/Karachi",
        },
    )
    assert response.status_code == 201

    # Verify in DB
    result = await db_session.execute(
        select(User).where(User.email == "tz_register@example.com")
    )
    user = result.scalar_one()
    assert user.timezone == "Asia/Karachi"


async def test_register_with_invalid_timezone(async_client):
    response = await async_client.post(
        "/users/",
        json={
            "first_name": "Timezone",
            "last_name": "User",
            "email": "tz_invalid@example.com",
            "whatsapp_number": "+923001112224",
            "password": "password123",
            "timezone": "Invalid/Timezone",
        },
    )
    assert response.status_code == 422
    assert "Invalid timezone" in response.text


async def test_update_timezone_via_patch(async_client, db_session):
    # Register first
    reg_response = await async_client.post(
        "/users/",
        json={
            "first_name": "Update",
            "last_name": "User",
            "email": "tz_update@example.com",
            "whatsapp_number": "+923001112225",
            "password": "password123",
        },
    )
    assert reg_response.status_code == 201

    # Login
    login_response = await async_client.post(
        "/users/login",
        json={"email": "tz_update@example.com", "password": "password123"},
    )
    token = login_response.json()["access_token"]

    # Update Timezone
    patch_response = await async_client.patch(
        "/users/me",
        json={"timezone": "America/New_York"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["timezone"] == "America/New_York"

    # Verify in DB
    result = await db_session.execute(
        select(User).where(User.email == "tz_update@example.com")
    )
    user = result.scalar_one()
    assert user.timezone == "America/New_York"


async def test_reminder_timezone_conversion(async_client, mocker, db_session):
    # Register user with America/New_York (DST observing)
    await async_client.post(
        "/users/",
        json={
            "first_name": "Reminder",
            "last_name": "User",
            "email": "tz_reminder@example.com",
            "whatsapp_number": "+923001112226",
            "password": "password123",
            "timezone": "America/New_York",
        },
    )

    login_response = await async_client.post(
        "/users/login",
        json={"email": "tz_reminder@example.com", "password": "password123"},
    )
    token = login_response.json()["access_token"]

    # Mock LLM to return a naive datetime that represents local time
    # e.g. the user says "remind me at 9am on July 1st", the LLM parses it to 9am.
    mock_json = '{"intent": "SET_REMINDER", "datetime_iso": "2030-07-01T09:00:00", "reminder_text": "Wake up", "is_general_question": false, "search_query": null}'
    mocker.patch(
        "app.services.llm_gateway.generate_llm_response", return_value=(mock_json, None)
    )

    chat_response = await async_client.post(
        "/chat/",
        json={"message": "remind me to wake up at 9am on July 1st"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert chat_response.status_code == 200

    # Verify DB reminder time is correctly offset to UTC
    # 09:00:00 in America/New_York on July 1st (EDT, UTC-4) is 13:00:00 in UTC
    result = await db_session.execute(
        select(User).where(User.email == "tz_reminder@example.com")
    )
    user = result.scalar_one()

    rem_result = await db_session.execute(
        select(Reminder).where(Reminder.user_id == user.id)
    )
    reminder = rem_result.scalar_one()

    # remind_at should be exactly 2030-07-01 13:00:00+00:00
    assert reminder.remind_at.hour == 13
    assert reminder.remind_at.minute == 0
