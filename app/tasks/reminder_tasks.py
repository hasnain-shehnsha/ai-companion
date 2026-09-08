import asyncio
import resend
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User


@celery_app.task
def send_reminder_email(reminder_id: str):
    """
    Celery task to send an email reminder using Resend.
    Since Celery tasks are synchronous by default in this setup,
    we use asyncio.run to execute the async DB calls if needed,
    or we just use synchronous SQLAlchemy session.
    """
    resend.api_key = settings.RESEND_API_KEY

    asyncio.run(_process_reminder(reminder_id))


async def _process_reminder(reminder_id: str):
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        async_sessionmaker,
        AsyncSession,
    )
    from sqlalchemy import select

    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    local_engine = create_async_engine(db_url, echo=False)
    LocalAsyncSession = async_sessionmaker(
        local_engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with LocalAsyncSession() as db:

            stmt = select(Reminder).where(Reminder.id == reminder_id)
            result = await db.execute(stmt)
            reminder = result.scalar_one_or_none()

            if not reminder or reminder.status != ReminderStatus.PENDING:
                return

            stmt_user = select(User).where(User.id == reminder.user_id)
            result_user = await db.execute(stmt_user)
            user = result_user.scalar_one_or_none()

            if not user:
                return

            try:
                params = {
                    "from": "AI Companion <onboarding@resend.dev>",
                    "to": [
                        "hasnainshehnsha.ai@gmail.com"
                    ],  # Hardcoded for Resend Free Tier testing
                    "subject": "⏰ Your AI Reminder",
                    "html": f"""
                    <div style="font-family: sans-serif; padding: 20px;">
                        <h2>Hi {user.first_name},</h2>
                        <p>You asked me to remind you about:</p>
                        <blockquote style="border-left: 4px solid #4F46E5; padding-left: 15px; font-size: 18px; font-style: italic;">
                            "{reminder.message}"
                        </blockquote>
                        <p>Have a great day!</p>
                    </div>
                    """,
                }
                email_response = resend.Emails.send(params)

                if user.whatsapp_number:
                    try:
                        from app.services.whatsapp_service import send_whatsapp_message

                        wa_number = "923404386378"

                        wa_message = f'⏰ *Reminder for {user.first_name}:*\n\n"{reminder.message}"\n\nHave a great day! 🤖'
                        await send_whatsapp_message(wa_number, wa_message)
                    except Exception as wa_e:
                        print(f"Failed to send WhatsApp reminder: {wa_e}")

                reminder.status = ReminderStatus.SENT
                await db.commit()

            except Exception as e:
                print(f"Failed to send email: {e}")
                reminder.status = ReminderStatus.FAILED
                await db.commit()
    finally:
        await local_engine.dispose()
