import hashlib
import hmac
import json
import uuid
from datetime import UTC

import pytest

from app.core.security import get_password_hash
from app.models.user import User, UserTier
from app.models.webhook_event import WebhookEvent


def generate_signature(payload: dict, secret: str) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def payload_body(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def base_webhook_payload():
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "12345",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "12345",
                                "phone_number_id": "12345",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": "9999999999",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "9999999999",
                                    "id": "wamid.ABCDEFGH",
                                    "timestamp": "1610000000",
                                    "text": {"body": "Hello"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


@pytest.fixture
async def wa_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email="wa@example.com",
        hashed_password=get_password_hash("password123"),
        whatsapp_number="+923001234567",
        tier=UserTier.FREE,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def premium_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Premium",
        last_name="User",
        email="premium@example.com",
        hashed_password=get_password_hash("password123"),
        whatsapp_number="+923001234567",
        tier=UserTier.PAID,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_valid_signature_queues_task(
    async_client, base_webhook_payload, mocker, wa_user
):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")
    delay_mock = mocker.patch("app.tasks.webhook_tasks.process_whatsapp_webhook.delay")
    mocker.patch("app.api.endpoints.whatsapp.mark_whatsapp_message_read")
    sig = generate_signature(base_webhook_payload, "test_secret")

    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload_body(base_webhook_payload),
        headers={"X-Hub-Signature-256": sig},
    )
    assert response.status_code == 200
    delay_mock.assert_called_once_with("wamid.ABCDEFGH")


async def test_invalid_signature(async_client, base_webhook_payload, mocker):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")
    sig = "sha256=invalidsignature"

    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload_body(base_webhook_payload),
        headers={"X-Hub-Signature-256": sig},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid signature"


async def test_duplicate_webhook_handled(
    async_client, db_session, base_webhook_payload, mocker
):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")
    sig = generate_signature(base_webhook_payload, "test_secret")
    delay_mock = mocker.patch("app.tasks.webhook_tasks.process_whatsapp_webhook.delay")
    mocker.patch("app.api.endpoints.whatsapp.mark_whatsapp_message_read")

    # Insert WebhookEvent to cause IntegrityError for duplicate ID
    from app.models.webhook_event import WebhookStatus

    event = WebhookEvent(
        id="wamid.ABCDEFGH",
        wa_id="9999999999",
        text="Hello",
        status=WebhookStatus.RECEIVED,
    )
    db_session.add(event)
    await db_session.commit()

    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload_body(base_webhook_payload),
        headers={"X-Hub-Signature-256": sig},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    # Delay mock should NOT be called because it was ignored as a duplicate
    delay_mock.assert_not_called()


async def test_multiple_messages_in_one_webhook(
    async_client, base_webhook_payload, mocker, wa_user
):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")
    delay_mock = mocker.patch("app.tasks.webhook_tasks.process_whatsapp_webhook.delay")
    mocker.patch("app.api.endpoints.whatsapp.mark_whatsapp_message_read")

    payload = base_webhook_payload.copy()
    payload["entry"][0]["changes"][0]["value"]["messages"].append(
        {
            "from": "9999999999",
            "id": "wamid.IJKLMNOP",
            "timestamp": "1610000001",
            "text": {"body": "Another message"},
            "type": "text",
        }
    )

    sig = generate_signature(payload, "test_secret")

    # The webhook should process both
    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload_body(payload),
        headers={"X-Hub-Signature-256": sig},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert delay_mock.call_count == 2


async def test_process_message_rejects_free_user(mocker, wa_user, db_session):
    """FREE users are rejected from Premium-only WhatsApp features."""
    from app.api.endpoints.whatsapp import process_message

    mock_send = mocker.patch(
        "app.api.endpoints.whatsapp.send_whatsapp_message", return_value=True
    )
    mock_handle_chat = mocker.patch("app.api.endpoints.whatsapp.handle_chat")

    # Process message directly
    await process_message("923001234567", "Hello", db=db_session)

    # Should send a rejection message
    mock_send.assert_awaited_once()
    args = mock_send.call_args[0]
    assert "Your current plan doesn't include WhatsApp access" in args[1]

    # Should NOT call handle_chat
    mock_handle_chat.assert_not_called()


async def test_process_message_accepts_premium_user(mocker, premium_user, db_session):
    """Premium users are allowed to use WhatsApp."""
    from app.api.endpoints.whatsapp import process_message

    mock_send = mocker.patch(
        "app.api.endpoints.whatsapp.send_whatsapp_message", return_value=True
    )
    mock_handle_chat = mocker.patch(
        "app.api.endpoints.whatsapp.handle_chat",
        return_value={"response": "I am an AI response"},
    )

    # Process message directly
    await process_message("923001234567", "Hello", db=db_session)

    # Should process chat
    mock_handle_chat.assert_awaited_once()
    # Should send AI response
    mock_send.assert_awaited_once_with("923001234567", "I am an AI response")


async def test_webhook_event_persisted_worker_crash_recovery(db_session, mocker):
    """Event persisted followed by worker crash; retry eventually processes once."""
    from datetime import datetime, timedelta

    from app.models.webhook_event import WebhookEvent, WebhookStatus
    from app.tasks.scheduler_tasks import _recover_webhook_events_async

    # Simulate a worker crash by manually putting an event in PROCESSING state for more than 5 minutes
    event = WebhookEvent(
        id="wamid.CRASH",
        wa_id="9999999999",
        text="Hello",
        status=WebhookStatus.PROCESSING,
        created_at=datetime.now(UTC) - timedelta(minutes=10),
        last_attempt_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db_session.add(event)
    await db_session.commit()

    mock_delay = mocker.patch("app.tasks.webhook_tasks.process_whatsapp_webhook.delay")

    # Run recovery task
    await _recover_webhook_events_async()

    # The event should be rolled back to RECEIVED and re-enqueued
    await db_session.refresh(event)
    assert event.status == WebhookStatus.RECEIVED
    mock_delay.assert_called_once_with("wamid.CRASH")
