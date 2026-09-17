import logging

from sqlalchemy import update
from sqlalchemy.sql import func

from app.api.endpoints.whatsapp import process_message
from app.core.celery_app import celery_app
from app.core.database import get_celery_db
from app.models.webhook_event import WebhookEvent, WebhookStatus

logger = logging.getLogger(__name__)


@celery_app.task
def process_whatsapp_webhook(msg_id: str):
    """
    Celery task to handle incoming WhatsApp messages atomically.
    """
    from app.core.async_utils import run_async

    run_async(_process_whatsapp_webhook_async(msg_id))


async def _process_whatsapp_webhook_async(msg_id: str):
    try:
        async with get_celery_db() as db:
            # Phase 1: Atomically claim the webhook event
            stmt = (
                update(WebhookEvent)
                .where(
                    WebhookEvent.id == msg_id,
                    WebhookEvent.status.in_(
                        [WebhookStatus.RECEIVED, WebhookStatus.FAILED]
                    ),
                )
                .values(
                    status=WebhookStatus.PROCESSING,
                    last_attempt_at=func.now(),
                    attempt_count=WebhookEvent.attempt_count + 1,
                )
                .returning(WebhookEvent)
            )
            result = await db.execute(stmt)
            event = result.scalar_one_or_none()

            if not event:
                logger.debug(f"Webhook event {msg_id} already processing or processed")
                return

            # Commit the claim immediately so other workers see it as PROCESSING
            await db.commit()

            # Phase 2: Process the message (handles user lookup, AI completion, and reply)
            try:
                await process_message(event.wa_id, event.text, db=db)
                final_status = WebhookStatus.PROCESSED
                failure_reason = None
            except Exception as e:
                logger.exception("Error processing webhook message")
                final_status = WebhookStatus.FAILED
                failure_reason = str(e)
                # Finalize status and then raise to let Celery know it failed
                final_update_stmt = (
                    update(WebhookEvent)
                    .where(WebhookEvent.id == event.id)
                    .values(status=final_status, failure_reason=failure_reason)
                )
                await db.execute(final_update_stmt)
                await db.commit()
                raise e

            # Phase 3: Finalize status on success
            final_update_stmt = (
                update(WebhookEvent)
                .where(WebhookEvent.id == event.id)
                .values(status=final_status, failure_reason=failure_reason)
            )
            await db.execute(final_update_stmt)
            await db.commit()
    except Exception as e:
        logger.exception("Error in process_whatsapp_webhook", extra={"msg_id": msg_id})
        raise e
