import asyncio
from celery.schedules import crontab
from app.core.celery_app import celery_app
from app.core.config import settings
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def process_daily_subscriptions():
    """
    Celery Beat task that runs every minute to check for daily subscriptions
    that should be sent at the current time.
    """
    asyncio.run(_process_subscriptions_async())


async def _process_subscriptions_async():
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        async_sessionmaker,
        AsyncSession,
    )
    from sqlalchemy import select
    from app.models.subscription import DailySubscription
    from app.models.user import User
    from app.services.llm_service import client, MODEL
    from app.services.whatsapp_service import send_whatsapp_message

    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    local_engine = create_async_engine(db_url, echo=False)
    LocalAsyncSession = async_sessionmaker(
        local_engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with LocalAsyncSession() as db:

            now = datetime.now().astimezone()

            stmt = select(DailySubscription).where(DailySubscription.is_active == True)
            result = await db.execute(stmt)
            subscriptions = result.scalars().all()

            for sub in subscriptions:

                sub_time = sub.time_of_day
                if sub_time.hour == now.hour and sub_time.minute == now.minute:
                    logger.info(
                        f"Triggering daily subscription {sub.id} for user {sub.user_id}"
                    )

                    user_stmt = select(User).where(User.id == sub.user_id)
                    user = (await db.execute(user_stmt)).scalar_one_or_none()

                    if user and user.whatsapp_number:
                        try:

                            prompt = f"Generate a short, thoughtful, and insightful message about: '{sub.topic}'. Do not include conversational filler, just the content directly."
                            response = await client.chat.completions.create(
                                messages=[{"role": "user", "content": prompt}],
                                model=MODEL,
                                max_tokens=300,
                                temperature=0.7,
                            )
                            content = response.choices[0].message.content.strip()

                            wa_number = user.whatsapp_number
                            if wa_number.startswith("0"):
                                wa_number = "92" + wa_number[1:]

                            success = await send_whatsapp_message(wa_number, content)
                            if success:
                                logger.info(
                                    f"Successfully sent daily subscription to {wa_number}"
                                )
                            else:
                                logger.error(
                                    f"Failed to send daily subscription to {wa_number}"
                                )

                        except Exception as e:
                            logger.error(f"Error processing subscription {sub.id}: {e}")

    finally:
        await local_engine.dispose()
