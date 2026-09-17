import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.webhook_event import WebhookEvent
from app.models.whatsapp_delivery import WhatsAppTemplateDelivery

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _get_whatsapp_client():
    """
    Shared client that constructs the Graph API base URL and headers in one place.
    """
    base_url = f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        yield client


async def send_whatsapp_message(to_number: str, text: str):
    """
    Sends a text message to a WhatsApp number using the Meta Graph API.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    async with _get_whatsapp_client() as client:
        try:
            response = await client.post("messages", json=payload)
            response.raise_for_status()
            logger.info(f"Successfully sent WhatsApp message to {to_number}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API Error: {e.response.text}")
            raise


async def mark_whatsapp_message_read(message_id: str):
    """
    Marks an incoming WhatsApp message as read to trigger blue ticks for the user.
    """
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    async with _get_whatsapp_client() as client:
        try:
            response = await client.post("messages", json=payload)
            response.raise_for_status()
            logger.info(f"Successfully marked WhatsApp message {message_id} as read")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API Error (mark read): {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"WhatsApp API Request Error (mark read): {e!s}")


async def is_conversation_window_active(db: AsyncSession, wa_id: str) -> bool:
    """
    Check if the user has sent a message within the last 24 hours.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    stmt = (
        select(WebhookEvent)
        .where(WebhookEvent.wa_id == wa_id, WebhookEvent.created_at >= cutoff)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def send_whatsapp_template(
    db: AsyncSession,
    to_number: str,
    template_name: str,
    language: str,
    components: list,
):
    """
    Sends an approved WhatsApp template message and logs the delivery attempt.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components,
        },
    }

    delivery_log = WhatsAppTemplateDelivery(
        to_number=to_number,
        template_name=template_name,
        language=language,
        parameters=components,
    )
    db.add(delivery_log)
    await db.commit()

    async with _get_whatsapp_client() as client:
        try:
            response = await client.post("messages", json=payload)
            response_json = response.json()
            response.raise_for_status()

            delivery_log.success = True
            delivery_log.provider_response = response_json
            await db.commit()

            logger.info(f"Successfully sent WhatsApp template to {to_number}")
            return response_json
        except httpx.HTTPStatusError as e:
            err_text = e.response.text
            logger.error(f"WhatsApp API Error (template): {err_text}")
            delivery_log.success = False
            delivery_log.error_message = err_text
            await db.commit()
            raise
        except Exception as e:
            logger.error(f"Failed to send WhatsApp template: {e!s}")
            delivery_log.success = False
            delivery_log.error_message = str(e)
            await db.commit()
            raise
