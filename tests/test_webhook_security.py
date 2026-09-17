import hashlib
import hmac

import pytest
from pydantic import ValidationError

from app.core.config import ProductionSettings


def test_production_settings_requires_secret(monkeypatch):
    # Ensure it doesn't read from os.environ if it's set there
    monkeypatch.delenv("META_APP_SECRET", raising=False)

    # Attempting to instantiate ProductionSettings without META_APP_SECRET should fail
    # We pass dummy required values and _env_file=None to ignore the local .env
    with pytest.raises(ValidationError) as exc:
        ProductionSettings(
            _env_file=None,
            DATABASE_URL="postgresql://test",
            GROQ_API_KEY="test",
            ALLOWED_ORIGINS="*",
            WHATSAPP_TOKEN="test",
            WHATSAPP_PHONE_NUMBER_ID="test",
            WHATSAPP_VERIFY_TOKEN="test",
            REDIS_URL="redis://localhost",
            RESEND_API_KEY="test",
            SECRET_KEY="test",
            # META_APP_SECRET is intentionally omitted
        )
    assert "META_APP_SECRET" in str(exc.value)


async def test_webhook_missing_signature(async_client, mocker):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test-secret")
    response = await async_client.post("/whatsapp/webhook", json={"test": "payload"})
    assert response.status_code == 403
    assert "Missing signature" in response.text


async def test_webhook_invalid_signature_format(async_client, mocker):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test-secret")
    response = await async_client.post(
        "/whatsapp/webhook",
        json={"test": "payload"},
        headers={"x-hub-signature-256": "invalid-format"},
    )
    assert response.status_code == 403
    assert "Invalid signature format" in response.text


async def test_webhook_wrong_signature(async_client, mocker):
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", "test-secret")
    response = await async_client.post(
        "/whatsapp/webhook",
        json={"test": "payload"},
        headers={"x-hub-signature-256": "sha256=wrongsignature"},
    )
    assert response.status_code == 403
    assert "Invalid signature" in response.text


async def test_webhook_valid_signature(async_client, mocker):
    secret = "test-secret"
    payload = b'{"test": "payload"}'

    # Calculate valid signature
    expected_signature = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()

    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", secret)

    response = await async_client.post(
        "/whatsapp/webhook",
        content=payload,
        headers={"x-hub-signature-256": f"sha256={expected_signature}"},
    )
    assert response.status_code == 200


async def test_webhook_production_failsafe(async_client, mocker):
    mocker.patch("app.api.endpoints.whatsapp.settings.ENVIRONMENT", "production")
    mocker.patch("app.api.endpoints.whatsapp.settings.META_APP_SECRET", None)

    response = await async_client.post("/whatsapp/webhook", json={"test": "payload"})
    assert response.status_code == 500
    assert "Configuration Error" in response.text
