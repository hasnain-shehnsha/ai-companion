import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, update

from app.core.celery_app import celery_app
from app.core.database import get_celery_db
from app.models.subscription import DailySubscription
from app.models.user import User
from app.services.llm_service import client, MODEL
from app.services.whatsapp_service import send_whatsapp_message

logger = logging.getLogger(__name__)


@celery_app.task
def process_daily_subscriptions():
    """
    Celery Beat task that runs every minute to check for daily subscriptions
    that should be sent at the current time.
    """
    asyncio.run(_process_subscriptions_async())


async def _process_subscriptions_async():
    try:
        async with get_celery_db() as db:
            stmt = select(DailySubscription).where(DailySubscription.is_active == True)
            result = await db.execute(stmt)
            subscriptions = result.scalars().all()

            for sub in subscriptions:
                # Fetch User to get timezone and WhatsApp number
                user_stmt = select(User).where(User.id == sub.user_id)
                user = (await db.execute(user_stmt)).scalar_one_or_none()

                if not user:
                    continue

                try:
                    tz = ZoneInfo(user.timezone)
                except ZoneInfoNotFoundError:
                    tz = ZoneInfo("UTC")

                now_local = datetime.now(tz)

                # Compare hour and minute in user's timezone
                sub_time = sub.time_of_day
                if (
                    sub_time.hour == now_local.hour
                    and sub_time.minute == now_local.minute
                ):
                    if sub.last_sent_date == now_local.date():
                        continue

                    # Atomic check-and-set for idempotency
                    update_stmt = (
                        update(DailySubscription)
                        .where(DailySubscription.id == sub.id)
                        .where(
                            (DailySubscription.last_sent_date != now_local.date())
                            | (DailySubscription.last_sent_date.is_(None))
                        )
                        .values(last_sent_date=now_local.date())
                    )
                    update_result = await db.execute(update_stmt)

                    if update_result.rowcount == 0:
                        continue

                    await db.commit()

                    logger.info(
                        "Triggering daily subscription",
                        extra={"subscription_id": sub.id, "user_id": sub.user_id},
                    )

                    if user.whatsapp_number:
                        try:
                            # Generate Content via LLM
                            prompt = f"Generate a short, thoughtful, and insightful message about: '{sub.topic}'. Do not include conversational filler, just the content directly. IMPORTANT: Generate the message in the exact same language (e.g., English, Roman Urdu, etc.) that the topic is written in."
                            response = await client.chat.completions.create(
                                messages=[{"role": "user", "content": prompt}],
                                model=MODEL,
                                max_tokens=300,
                                temperature=0.7,
                            )
                            content = response.choices[0].message.content.strip()

                            # Format number for Meta (strip leading +)
                            wa_number = user.whatsapp_number.replace("+", "")
                            # Send via WhatsAp
                            success = await send_whatsapp_message(wa_number, content)
                            if success:
                                logger.info(
                                    "Successfully sent daily subscription",
                                    extra={"wa_number": wa_number},
                                )
                            else:
                                logger.error(
                                    "Failed to send daily subscription",
                                    extra={"wa_number": wa_number},
                                )

                        except Exception as e:
                            logger.exception(
                                "Error processing subscription",
                                extra={"subscription_id": sub.id},
                            )

    except Exception as e:
        logger.exception("Error in scheduler task")
