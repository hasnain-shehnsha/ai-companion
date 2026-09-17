import hashlib
import hmac
import json
import logging

import phonenumbers
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.webhook_event import WebhookEvent, WebhookStatus
from app.services.ai_service import handle_chat
from app.services.whatsapp_service import (
    mark_whatsapp_message_read,
    send_whatsapp_message,
)

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
        if not signature:
            raise HTTPException(status_code=403, detail="Missing signature")

        if not signature.startswith("sha256="):
            raise HTTPException(status_code=403, detail="Invalid signature format")

        expected_signature = hmac.new(
            settings.META_APP_SECRET.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(f"sha256={expected_signature}", signature):
            logger.warning("Invalid WhatsApp webhook signature received")
            raise HTTPException(status_code=403, detail="Invalid signature")
    elif settings.ENVIRONMENT == "production":
        logger.error(
            "Rejecting webhook in production because META_APP_SECRET is unexpectedly missing!"
        )
        raise HTTPException(status_code=500, detail="Configuration Error")

    try:
        body = json.loads(body_bytes)

        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    for message in messages:
                        msg_id = message.get("id")

                        if message.get("type") == "text":
                            if msg_id:
                                wa_id = message.get("from")  # Sender's WhatsApp number
                                text = message.get("text", {}).get("body")

                                event = WebhookEvent(
                                    id=msg_id,
                                    wa_id=wa_id,
                                    text=text,
                                    status=WebhookStatus.RECEIVED,
                                )
                                db.add(event)
                                try:
                                    await db.commit()
                                except IntegrityError:
                                    await db.rollback()

                                    # Handle Meta retries
                                    stmt = select(WebhookEvent).where(
                                        WebhookEvent.id == msg_id
                                    )
                                    existing_event = (
                                        await db.execute(stmt)
                                    ).scalar_one_or_none()

                                    if (
                                        existing_event
                                        and existing_event.status
                                        == WebhookStatus.FAILED
                                    ):
                                        logger.info(
                                            f"Retrying previously failed webhook {msg_id}"
                                        )
                                        existing_event.status = WebhookStatus.RECEIVED
                                        await db.commit()
                                    else:
                                        logger.info(
                                            f"Duplicate WhatsApp message ID {msg_id} ignored."
                                        )
                                        continue

                                # Mark the message as read to turn ticks blue
                                background_tasks.add_task(
                                    mark_whatsapp_message_read, msg_id
                                )

                                # Enqueue durable Celery job
                                from app.tasks.webhook_tasks import (
                                    process_whatsapp_webhook,
                                )

                                process_whatsapp_webhook.delay(msg_id)

        return {"status": "success"}
    except json.JSONDecodeError as e:
        logger.error(
            "Invalid JSON payload received from webhook",
            exc_info=True,
            extra={"error": str(e)},
        )
        raise HTTPException(status_code=400, detail="Invalid JSON format")


async def process_message(wa_id: str, text: str, db=None):
    """
    Process the message, retrieve user context, and send AI response.
    """
    if db is None:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            return await process_message(wa_id, text, db=session)

    from sqlalchemy import select

    from app.services.auth_service import check_premium_entitlement

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

        if not check_premium_entitlement(user):
            fallback_msg = (
                f"Hello {user.first_name}! 🌟\n\n"
                "Your current plan doesn't include WhatsApp access. "
                "Please upgrade to Premium on our website to chat with me here!"
            )
            await send_whatsapp_message(wa_id, fallback_msg)
            return

        # Attempt to get AI response
        try:
            response_data = await handle_chat(db, user, text, channel="whatsapp")
            response_text = response_data.get(
                "response",
                "I'm sorry, I ran into a technical issue processing that. Could you please try asking again?",
            )
            if not response_text or not response_text.strip():
                response_text = "I'm sorry, I ran into a technical issue processing that. Could you please try asking again?"
        except Exception as ai_e:
            logger.exception(
                "Error in handle_chat during process_message", extra={"wa_id": wa_id}
            )
            response_text = "I'm sorry, I ran into a technical issue processing that. Could you please try asking again?"

        # Attempt to send the response exactly once
        await send_whatsapp_message(wa_id, response_text)

    except Exception as e:
        # If an error happens outside handle_chat (like during send_whatsapp_message or DB lookup)
        # we just log it. We DO NOT try to send another fallback message because it can lead to duplicate
        # deliveries if the original message was actually dispatched by Meta before the HTTP timeout.
        logger.exception("Error in process_message wrapper", extra={"wa_id": wa_id})
        raise e
