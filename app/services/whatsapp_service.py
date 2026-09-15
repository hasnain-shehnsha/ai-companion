import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def send_whatsapp_message(to_number: str, text: str):
    """
    Sends a text message to a WhatsApp number using the Meta Graph API.
    """
    url = (
        f"https://graph.facebook.com/v20.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Successfully sent WhatsApp message to {to_number}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API Error: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {str(e)}")
            raise

async def mark_whatsapp_message_read(message_id: str):
    """
    Marks an incoming WhatsApp message as read to trigger blue ticks for the user.
    """
    url = (
        f"https://graph.facebook.com/v20.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Successfully marked WhatsApp message {message_id} as read")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API Error (mark read): {e.response.text}")
        except Exception as e:
            logger.error(f"Failed to mark WhatsApp message as read: {str(e)}")
