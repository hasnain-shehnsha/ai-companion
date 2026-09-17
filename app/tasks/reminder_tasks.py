import html
import logging

import resend
from sqlalchemy import select, update
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import get_celery_db
from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User
from app.services.whatsapp_service import (
    is_conversation_window_active,
    send_whatsapp_message,
    send_whatsapp_template,
)

# Maximum number of Celery-level retries for transient failures
MAX_RETRIES = 3
# Initial backoff delay in seconds (doubles each retry: 30s, 60s, 120s)
RETRY_BACKOFF_BASE = 30


@celery_app.task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF_BASE,
    retry_backoff=True,
    retry_backoff_max=300,
    acks_late=True,
)
def send_reminder_email(self, reminder_id: str):
    """
    Celery task to deliver a reminder via email and WhatsApp.
    Uses bounded retries with exponential backoff.
    Only retries channels that haven't already succeeded.
    """
    resend.api_key = settings.RESEND_API_KEY
    from app.core.async_utils import run_async

    run_async(_process_reminder(self, reminder_id))


async def _process_reminder(task_self, reminder_id: str):
    try:
        async with get_celery_db() as db:
            # Phase 1: Atomically claim the reminder (only on first attempt)
            # On retries, the reminder is already PROCESSING — just load it.
            claim_stmt = (
                update(Reminder)
                .where(
                    Reminder.id == reminder_id,
                    Reminder.status.in_(
                        [
                            ReminderStatus.PENDING,
                            ReminderStatus.PROCESSING,
                            ReminderStatus.PARTIALLY_SENT,
                        ]
                    ),
                    Reminder.attempt_count == task_self.request.retries,
                )
                .values(
                    status=ReminderStatus.PROCESSING,
                    last_attempt_at=func.now(),
                    attempt_count=Reminder.attempt_count + 1,
                )
                .returning(Reminder)
            )
            result = await db.execute(claim_stmt)
            reminder = result.scalar_one_or_none()

            if not reminder:
                logger.info(
                    f"Reminder {reminder_id} not claimable (already SENT/CANCELLED or not found), skipping."
                )
                return

            await db.commit()

            # Load the user
            stmt_user = select(User).where(User.id == reminder.user_id)
            result_user = await db.execute(stmt_user)
            user = result_user.scalar_one_or_none()

            if not user:
                await _finalize_reminder(
                    db, reminder.id, ReminderStatus.FAILED, None, None, "User not found"
                )
                return

            # Track per-channel results for this attempt
            # Preserve prior success from earlier retries
            email_status = reminder.email_status
            whatsapp_status = reminder.whatsapp_status
            failures = []

            # ── Email Delivery ──────────────────────────────────────
            if email_status != ReminderStatus.SENT.value:
                if not user.email_verified:
                    logger.info(
                        f"Reminder {reminder.id}: Skipping email delivery (unverified)."
                    )
                    email_status = ReminderStatus.FAILED.value
                    failures.append("Email: Address not verified")
                else:
                    try:
                        escaped_name = html.escape(user.first_name or "")
                        escaped_message = html.escape(reminder.message or "")

                        params = {
                            "from": f"{settings.RESEND_FROM_NAME} <{settings.RESEND_FROM_EMAIL}>",
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
                        email_status = ReminderStatus.SENT.value
                    except Exception as e:
                        logger.exception(
                            "Failed to send reminder email via Resend",
                            extra={"reminder_id": reminder.id, "user_id": user.id},
                        )
                        email_status = ReminderStatus.FAILED.value
                        failures.append(f"Email: {e!s}")
            else:
                logger.info(f"Reminder {reminder.id}: email already SENT, skipping.")

            # ── WhatsApp Delivery ───────────────────────────────────
            from app.services.auth_service import check_premium_entitlement

            if user.whatsapp_number:
                if not check_premium_entitlement(user):
                    logger.info(
                        f"Reminder {reminder.id}: Skipping WhatsApp delivery (FREE tier)."
                    )
                    whatsapp_status = ReminderStatus.FAILED.value
                    failures.append("WhatsApp: Premium entitlement required")
                elif not user.whatsapp_verified:
                    logger.info(
                        f"Reminder {reminder.id}: Skipping WhatsApp delivery (unverified)."
                    )
                    whatsapp_status = ReminderStatus.FAILED.value
                    failures.append("WhatsApp: Number not verified")
                elif whatsapp_status != ReminderStatus.SENT.value:
                    try:
                        wa_number = user.whatsapp_number.replace("+", "")

                        is_active = await is_conversation_window_active(db, wa_number)
                        if is_active:
                            wa_message = f'⏰ *Reminder for {user.first_name}:*\n\n"{reminder.message}"\n\nHave a great day! 🤖'
                            await send_whatsapp_message(wa_number, wa_message)
                        else:
                            template_name = settings.WHATSAPP_REMINDER_TEMPLATE_NAME
                            language = settings.WHATSAPP_TEMPLATE_LANGUAGE
                            components = [
                                {
                                    "type": "body",
                                    "parameters": [
                                        {"type": "text", "text": user.first_name or ""},
                                        {
                                            "type": "text",
                                            "text": reminder.message or "",
                                        },
                                    ],
                                }
                            ]
                            await send_whatsapp_template(
                                db, wa_number, template_name, language, components
                            )

                        whatsapp_status = ReminderStatus.SENT.value
                    except Exception as wa_e:
                        logger.exception(
                            "Failed to send WhatsApp reminder",
                            extra={
                                "reminder_id": reminder.id,
                                "user_id": user.id,
                            },
                        )
                        whatsapp_status = ReminderStatus.FAILED.value
                        failures.append(f"WhatsApp: {wa_e!s}")
                else:
                    logger.info(
                        f"Reminder {reminder.id}: WhatsApp already SENT, skipping."
                    )
            else:
                whatsapp_status = None

            # ── Derive overall status ──────────────────────────────
            failure_reason = " | ".join(failures) if failures else None
            final_status = _derive_overall_status(email_status, whatsapp_status)

            # ── Decide: retry or finalize ──────────────────────────
            if final_status in (ReminderStatus.FAILED, ReminderStatus.PARTIALLY_SENT):
                if task_self.request.retries < task_self.max_retries:
                    # Save per-channel state so the next attempt skips succeeded channels
                    await _save_channel_state(
                        db, reminder.id, email_status, whatsapp_status, failure_reason
                    )
                    logger.info(
                        f"Reminder {reminder.id}: retrying (attempt {task_self.request.retries + 1}/{task_self.max_retries})"
                    )
                    raise task_self.retry(
                        exc=Exception(f"Channel failures: {failure_reason}"),
                        countdown=RETRY_BACKOFF_BASE * (2**task_self.request.retries),
                    )
                else:
                    # Final attempt exhausted — save the accurate terminal status
                    logger.warning(
                        f"Reminder {reminder.id}: retries exhausted, finalizing as {final_status.value}"
                    )
                    await _finalize_reminder(
                        db,
                        reminder.id,
                        final_status,
                        email_status,
                        whatsapp_status,
                        failure_reason,
                    )
            else:
                # Both channels succeeded (or only applicable channel succeeded)
                await _finalize_reminder(
                    db,
                    reminder.id,
                    final_status,
                    email_status,
                    whatsapp_status,
                    failure_reason,
                )

    except task_self.MaxRetriesExceededError:
        # Celery raises this when retry() is called past max_retries
        logger.error(f"Reminder {reminder_id}: max retries exceeded.")
    except Exception as e:
        from celery.exceptions import Retry

        if isinstance(e, Retry):
            raise
        # Unexpected exception (DB error, import error, etc.)
        logger.exception(
            "Unexpected error processing reminder", extra={"reminder_id": reminder_id}
        )
        try:
            async with get_celery_db() as db:
                await _finalize_reminder(
                    db,
                    reminder_id,
                    ReminderStatus.FAILED,
                    None,
                    None,
                    f"Unexpected error: {e!s}",
                )
        except Exception:
            logger.exception("Failed to mark reminder as FAILED after unexpected error")
        raise e


def _derive_overall_status(email_status, whatsapp_status):
    """Derive the overall reminder status from per-channel results."""
    # Normalize: None means "not applicable" (no WA number, etc.)
    email_ok = (email_status == ReminderStatus.SENT.value) or email_status is None
    wa_ok = (whatsapp_status == ReminderStatus.SENT.value) or whatsapp_status is None

    if email_ok and wa_ok:
        return ReminderStatus.SENT

    # Both channels attempted and both failed
    email_failed = email_status == ReminderStatus.FAILED.value
    wa_failed = (
        whatsapp_status == ReminderStatus.FAILED.value
    ) or whatsapp_status is None
    if email_failed and wa_failed:
        return ReminderStatus.FAILED

    # One succeeded, one failed
    return ReminderStatus.PARTIALLY_SENT


async def _save_channel_state(
    db, reminder_id, email_status, whatsapp_status, failure_reason
):
    """Persist per-channel statuses without changing the overall status (stays PROCESSING)."""
    stmt = (
        update(Reminder)
        .where(Reminder.id == reminder_id)
        .values(
            email_status=email_status,
            whatsapp_status=whatsapp_status,
            failure_reason=failure_reason,
        )
    )
    await db.execute(stmt)
    await db.commit()


async def _finalize_reminder(
    db, reminder_id, final_status, email_status, whatsapp_status, failure_reason
):
    """Set the terminal overall status plus channel statuses."""
    stmt = (
        update(Reminder)
        .where(Reminder.id == reminder_id)
        .values(
            status=final_status,
            email_status=email_status,
            whatsapp_status=whatsapp_status,
            failure_reason=failure_reason,
        )
    )
    await db.execute(stmt)
    await db.commit()
