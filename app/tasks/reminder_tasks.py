import asyncio
import resend
import html
import logging
from sqlalchemy import select
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import get_celery_db
from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User
from app.services.whatsapp_service import send_whatsapp_message


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
    try:
        async with get_celery_db() as db:

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

            reminder.attempt_count += 1
            reminder.last_attempt_at = func.now()

            failures = []

            # Email Delivery
            try:
                escaped_name = html.escape(user.first_name or "")
                escaped_message = html.escape(reminder.message or "")

                params = {
                    "from": "AI Companion <onboarding@resend.dev>",
                    "to": [user.email],
                    "subject": "⏰ Your AI Reminder",
                    "html": f"""
                    <div style="font-family: sans-serif; padding: 20px;">
                        <h2>Hi {escaped_name},</h2>
                        <p>You asked me to remind you about:</p>
                        <blockquote style="border-left: 4px solid #4F46E5; padding-left: 15px; font-size: 18px; font-style: italic;">
                            "{escaped_message}"
                        </blockquote>
                        <p>Have a great day!</p>
                    </div>
                    """,
                }
                resend.Emails.send(params)
                reminder.email_status = ReminderStatus.SENT.value
            except Exception as e:
                logger.exception(
                    "Failed to send reminder email via Resend",
                    extra={"reminder_id": reminder.id, "user_id": user.id},
                )
                reminder.email_status = ReminderStatus.FAILED.value
                failures.append(f"Email: {str(e)}")

            # WhatsApp Delivery
            if user.whatsapp_number:
                try:
                    wa_number = user.whatsapp_number.replace("+", "")
                    wa_message = f'⏰ *Reminder for {user.first_name}:*\n\n"{reminder.message}"\n\nHave a great day! 🤖'
                    await send_whatsapp_message(wa_number, wa_message)
                    reminder.whatsapp_status = ReminderStatus.SENT.value
                except Exception as wa_e:
                    logger.exception(
                        "Failed to send WhatsApp reminder",
                        extra={
                            "reminder_id": reminder.id,
                            "user_id": user.id,
                            "wa_number": wa_number,
                        },
                    )
                    reminder.whatsapp_status = ReminderStatus.FAILED.value
                    failures.append(f"WhatsApp: {str(wa_e)}")
            else:
                reminder.whatsapp_status = None

            if failures:
                reminder.failure_reason = " | ".join(failures)

            # Overall Status
            attempted = 0
            failed = 0
            if reminder.email_status:
                attempted += 1
                if reminder.email_status == ReminderStatus.FAILED.value:
                    failed += 1
            if reminder.whatsapp_status:
                attempted += 1
                if reminder.whatsapp_status == ReminderStatus.FAILED.value:
                    failed += 1

            if attempted > 0 and failed == attempted:
                reminder.status = ReminderStatus.FAILED
            else:
                reminder.status = ReminderStatus.SENT

            await db.commit()
    except Exception as e:
        logger.exception(
            "Error processing reminder", extra={"reminder_id": reminder_id}
        )
