import pytest
import hmac
import hashlib
import json
import uuid
from unittest.mock import AsyncMock
from app.core.config import settings
from app.models.user import User, UserTier
from app.models.webhook_event import WebhookEvent
from app.core.security import get_password_hash


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


async def test_valid_signature_free_user(
    async_client, base_webhook_payload, mocker, wa_user
):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")
    process_mock = mocker.patch(
        "app.api.endpoints.whatsapp.process_message", new_callable=AsyncMock
    )
    sig = generate_signature(base_webhook_payload, "test_secret")

    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload_body(base_webhook_payload),
        headers={"X-Hub-Signature-256": sig},
    )
    assert response.status_code == 200
    process_mock.assert_awaited_once_with("9999999999", "Hello")


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


async def test_duplicate_webhook(
    async_client, db_session, base_webhook_payload, mocker
):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")
    sig = generate_signature(base_webhook_payload, "test_secret")

    # Insert WebhookEvent to cause IntegrityError
    event = WebhookEvent(id="wamid.ABCDEFGH")
    db_session.add(event)
    await db_session.commit()

    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload_body(base_webhook_payload),
        headers={"X-Hub-Signature-256": sig},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


async def test_unknown_user_registration_fallback(
    async_client, base_webhook_payload, mocker, db_session
):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")

    # Change phone number to an unknown one
    payload = base_webhook_payload.copy()
    payload["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"] = "8888888888"
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = "8888888888"

    sig = generate_signature(payload, "test_secret")

    process_mock = mocker.patch(
        "app.api.endpoints.whatsapp.process_message", new_callable=AsyncMock
    )

    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload_body(payload),
        headers={"X-Hub-Signature-256": sig},
    )
    assert response.status_code == 200

    process_mock.assert_awaited_once_with("8888888888", "Hello")


async def test_multiple_messages_in_one_webhook(
    async_client, base_webhook_payload, mocker, wa_user
):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test_secret")
    process_mock = mocker.patch(
        "app.api.endpoints.whatsapp.process_message", new_callable=AsyncMock
    )

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
    assert process_mock.await_count == 2
