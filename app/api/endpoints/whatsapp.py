from fastapi import APIRouter, Depends, Request, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.services.ai_service import handle_chat
from app.services.whatsapp_service import send_whatsapp_message
import logging

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
async def handle_whatsapp_message(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle incoming WhatsApp messages from Meta Webhook.
    """
    body_bytes = await request.body()

    import json

    try:
        body = json.loads(body_bytes)

        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    if messages:
                        message = messages[0]

                        if message.get("type") == "text":
                            wa_id = message.get("from")  # Sender's WhatsApp number
                            text = message.get("text", {}).get("body")

                            await process_message(db, wa_id, text)

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {str(e)}")

        return {"status": "error"}


async def process_message(db: AsyncSession, wa_id: str, text: str):
    """
    Process the message, retrieve user context, and send AI response.
    """

    search_term = wa_id[-10:] if len(wa_id) >= 10 else wa_id
    result = await db.execute(
        select(User).filter(User.whatsapp_number.like(f"%{search_term}"))
    )
    user = result.scalar_one_or_none()

    if not user:

        fallback_msg = (
            "Hello! I am your AI Companion. 🧠\n\n"
            "I couldn't find an account associated with this number. "
            "Please create a Premium account on our website to start chatting with me!"
        )
        await send_whatsapp_message(wa_id, fallback_msg)
        return

    response_data = await handle_chat(db, user, text)
    response_text = response_data.get(
        "response", "Sorry, I encountered an error generating a response."
    )

    await send_whatsapp_message(wa_id, response_text)
