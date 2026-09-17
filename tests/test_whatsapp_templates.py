from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.webhook_event import WebhookEvent
from app.models.whatsapp_delivery import WhatsAppTemplateDelivery
from app.services.whatsapp_service import (
    is_conversation_window_active,
    send_whatsapp_template,
)


@pytest.mark.asyncio
async def test_is_conversation_window_active(db_session):
    wa_id = "1234567890"

    # Not active (no events)
    is_active = await is_conversation_window_active(db_session, wa_id)
    assert not is_active

    # Active (recent event)
    event = WebhookEvent(
        id="wamid.12345",
        wa_id=wa_id,
        text="Hello",
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(event)
    await db_session.commit()

    is_active = await is_conversation_window_active(db_session, wa_id)
    assert is_active

    # Not active (old event)
    event.created_at = datetime.now(UTC) - timedelta(hours=25)
    db_session.add(event)
    await db_session.commit()

    is_active = await is_conversation_window_active(db_session, wa_id)
    assert not is_active


@pytest.mark.asyncio
async def test_send_whatsapp_template(db_session):
    to_number = "1234567890"
    template_name = "utility_reminder"
    language = "en_US"
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Test User"},
                {"type": "text", "text": "Test Reminder"},
            ],
        }
    ]

    with patch("httpx.AsyncClient.post") as mock_post:

        class MockResponse:
            def json(self):
                return {
                    "messaging_product": "whatsapp",
                    "contacts": [{"input": to_number, "wa_id": to_number}],
                    "messages": [{"id": "wamid.123"}],
                }

            def raise_for_status(self):
                pass

        mock_post.return_value = MockResponse()

        response = await send_whatsapp_template(
            db_session, to_number, template_name, language, components
        )
        assert response["messages"][0]["id"] == "wamid.123"

        # Check DB log
        stmt = select(WhatsAppTemplateDelivery).where(
            WhatsAppTemplateDelivery.to_number == to_number
        )
        result = await db_session.execute(stmt)
        log = result.scalar_one_or_none()

        assert log is not None
        assert log.template_name == template_name
        assert log.success is True
        assert log.provider_response is not None


@pytest.mark.asyncio
async def test_whatsapp_client_uses_configured_version():
    from app.core.config import settings
    from app.services.whatsapp_service import _get_whatsapp_client

    async with _get_whatsapp_client() as client:
        assert (
            str(client.base_url)
            == f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/"
        )
