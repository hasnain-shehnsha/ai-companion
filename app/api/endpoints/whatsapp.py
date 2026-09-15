import json
import hmac
import hashlib
import phonenumbers
import logging
from sqlalchemy.exc import IntegrityError
from fastapi import (
    APIRouter,
    Depends,
    Request,
    HTTPException,
    Response,
    BackgroundTasks,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db, AsyncSessionLocal
from app.core.config import settings
from app.models.user import User, UserTier
from app.models.webhook_event import WebhookEvent
from app.services.ai_service import handle_chat
from app.services.whatsapp_service import send_whatsapp_message, mark_whatsapp_message_read

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Webhook verification endpoint required by Meta Graph API.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("WEBHOOK_VERIFIED")
            return Response(content=challenge, media_type="text/plain", status_code=200)
        else:
            raise HTTPException(status_code=403, detail="Verification token mismatch")

    raise HTTPException(status_code=400, detail="Missing parameters")


@router.post("/webhook")
async def handle_whatsapp_message(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle incoming WhatsApp messages from Meta Webhook.
    """
    body_bytes = await request.body()

    if settings.META_APP_SECRET:
        signature = request.headers.get("x-hub-signature-256", "")
        if not signature.startswith("sha256="):
            raise HTTPException(status_code=403, detail="Invalid signature format")

        expected_signature = hmac.new(
            settings.META_APP_SECRET.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(f"sha256={expected_signature}", signature):
            logger.warning("Invalid WhatsApp webhook signature received")
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        body = json.loads(body_bytes)

        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    for message in messages:
                        msg_id = message.get("id")

                        if msg_id:
                            event = WebhookEvent(id=msg_id)
                            db.add(event)
                            try:
                                await db.commit()
                            except IntegrityError:
                                await db.rollback()
                                logger.info(
                                    f"Duplicate WhatsApp message ID {msg_id} ignored."
                                )
                                continue

                        if message.get("type") == "text":
                            wa_id = message.get("from")  # Sender's WhatsApp number
                            text = message.get("text", {}).get("body")

                            # Mark the message as read to turn ticks blue
                            background_tasks.add_task(mark_whatsapp_message_read, msg_id)
                            
                            # Process in the background to avoid Meta webhook timeouts (and retries)
                            background_tasks.add_task(process_message, wa_id, text)

        return {"status": "success"}
    except json.JSONDecodeError as e:
        logger.error(
            "Invalid JSON payload received from webhook",
            exc_info=True,
            extra={"error": str(e)},
        )
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        logger.exception("Internal error handling WhatsApp webhook")
        # We must return a 5xx status so Meta registers a failure and retries the webhook.
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_message(wa_id: str, text: str):
    """
    Process the message, retrieve user context, and send AI response.
    """
    async with AsyncSessionLocal() as db:
        try:
            try:
                # Meta usually provides wa_id without the leading '+'
                parsed_wa_id = phonenumbers.parse(f"+{wa_id}")
                normalized_wa_id = phonenumbers.format_number(
                    parsed_wa_id, phonenumbers.PhoneNumberFormat.E164
                )
            except phonenumbers.NumberParseException:
                normalized_wa_id = wa_id

            result = await db.execute(
                select(User).filter(User.whatsapp_number == normalized_wa_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                fallback_msg = (
                    "Hello! I am your AI Companion. 🧠\n\n"
                    "I couldn't find an account associated with this number. "
                    "Please create a Premium account on our website to start chatting with me here!"
                )
                await send_whatsapp_message(wa_id, fallback_msg)
                return

            if user.tier != UserTier.PAID:
                fallback_msg = (
                    f"Hello {user.first_name}! 🧠\n\n"
                    "WhatsApp access is a Premium feature. "
                    "Please upgrade your account on our website to continue our conversation here!"
                )
                await send_whatsapp_message(wa_id, fallback_msg)
                return

            response_data = await handle_chat(db, user, text, channel="whatsapp")
            response_text = response_data.get(
                "response",
                "I'm sorry, I ran into a technical issue processing that. Could you please try asking again?",
            )

            if not response_text or not response_text.strip():
                response_text = "I'm sorry, I ran into a technical issue processing that. Could you please try asking again?"

            await send_whatsapp_message(wa_id, response_text)
        except Exception as e:
            logger.exception("Error in process_message", extra={"wa_id": wa_id})
            try:
                import httpx

                await send_whatsapp_message(
                    wa_id,
                    "I'm sorry, I ran into a technical issue processing that. Could you please try asking again?",
                )
            except httpx.RequestError as inner_e:
                logger.error(
                    "Failed to send fallback WhatsApp message",
                    exc_info=True,
                    extra={"wa_id": wa_id},
                )
