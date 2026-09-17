import logging

from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import get_celery_db
from app.models.subscription import DailySubscription
from app.models.subscription_delivery import DeliveryStatus, SubscriptionDelivery
from app.models.user import User
from app.services.llm_service import MODEL
from app.services.whatsapp_service import (
    is_conversation_window_active,
    send_whatsapp_message,
    send_whatsapp_template,
)

logger = logging.getLogger(__name__)


@celery_app.task
def process_daily_delivery(delivery_id: str):
    """
    Celery task to generate content and send a daily subscription."""
    from app.core.async_utils import run_async

    run_async(_process_delivery_async(delivery_id))


async def _process_delivery_async(delivery_id: str):
    try:
        async with get_celery_db() as db:
            # Phase 1: Atomically claim the delivery
            stmt = (
                update(SubscriptionDelivery)
                .where(
                    SubscriptionDelivery.id == delivery_id,
                    SubscriptionDelivery.status.in_(
                        [DeliveryStatus.PENDING, DeliveryStatus.FAILED]
                    ),
                )
                .values(
                    status=DeliveryStatus.PROCESSING,
                    last_attempt_at=func.now(),
                    attempt_count=SubscriptionDelivery.attempt_count + 1,
                )
                .returning(SubscriptionDelivery)
            )
            result = await db.execute(stmt)
            delivery = result.scalar_one_or_none()

            if not delivery:
                logger.info(
                    f"Delivery {delivery_id} not in PENDING state or not found, skipping."
                )
                return

            await db.commit()

            # Load the subscription and user
            sub_stmt = select(DailySubscription).where(
                DailySubscription.id == delivery.subscription_id
            )
            sub = (await db.execute(sub_stmt)).scalar_one_or_none()

            if not sub:
                await _fail_delivery(db, delivery.id, "Subscription not found")
                return

            user_stmt = select(User).where(User.id == sub.user_id)
            user = (await db.execute(user_stmt)).scalar_one_or_none()

            if not user or not user.whatsapp_number:
                await _fail_delivery(
                    db, delivery.id, "User or WhatsApp number not found"
                )
                return

            from app.services.auth_service import check_premium_entitlement

            if not check_premium_entitlement(user):
                await _fail_delivery(
                    db, delivery.id, "Premium entitlement required for daily schedules"
                )
                return

            if not user.whatsapp_verified:
                await _fail_delivery(db, delivery.id, "WhatsApp number not verified")
                return

            # Phase 2: Process (Generate & Send)
            try:
                # LLM Generation
                prompt = f"Generate a short, thoughtful, and insightful message about: '{sub.topic}'. Do not include conversational filler, just the content directly. IMPORTANT: Generate the message in the exact same language (e.g., English, Roman Urdu, etc.) that the topic is written in."
                from app.services.llm_gateway import generate_llm_response

                content, _ = await generate_llm_response(
                    messages=[{"role": "user", "content": prompt}],
                    user_id=user.id,
                    model=MODEL,
                    channel="background",
                    request_type="subscription",
                    max_tokens=300,
                    temperature=0.7,
                )
                content = content.strip()

                wa_number = user.whatsapp_number.replace("+", "")

                # Check conversation window and send appropriately
                is_active = await is_conversation_window_active(db, wa_number)

                if is_active:
                    wa_message = f"Daily Subscription: {sub.topic}\n\n{content}"
                    await send_whatsapp_message(wa_number, wa_message)
                else:
                    template_name = settings.WHATSAPP_REMINDER_TEMPLATE_NAME
                    language = settings.WHATSAPP_TEMPLATE_LANGUAGE
                    components = [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": user.first_name or ""},
                                {"type": "text", "text": content},
                            ],
                        }
                    ]
                    await send_whatsapp_template(
                        db, wa_number, template_name, language, components
                    )

                # Phase 3: Finalize Success
                await db.execute(
                    update(SubscriptionDelivery)
                    .where(SubscriptionDelivery.id == delivery.id)
                    .values(status=DeliveryStatus.SENT)
                )
                await db.execute(
                    update(DailySubscription)
                    .where(DailySubscription.id == sub.id)
                    .values(last_successful_delivery_date=delivery.delivery_date)
                )
                await db.commit()
                logger.info(
                    f"Successfully processed delivery {delivery.id} for subscription {sub.id}"
                )

            except Exception as e:
                logger.exception("Error during delivery generation or dispatch")
                await _fail_delivery(db, delivery.id, str(e))
                raise e

    except Exception as e:
        logger.exception("Error in process_daily_delivery task")
        raise e


async def _fail_delivery(db, delivery_id: str, reason: str):
    await db.execute(
        update(SubscriptionDelivery)
        .where(SubscriptionDelivery.id == delivery_id)
        .values(status=DeliveryStatus.FAILED, failure_reason=reason)
    )
    await db.commit()
