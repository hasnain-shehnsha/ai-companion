import asyncio
import logging

from sqlalchemy import select, update

from app.core.celery_app import celery_app
from app.core.database import get_celery_db
from app.crud.chat_crud import reset_user_chat_data
from app.models.user import DataResetJob, DataResetJobStatus
from app.services.memory_service import delete_all_facts_for_user

logger = logging.getLogger(__name__)

# Maximum number of retries
MAX_RETRIES = 5
# Initial backoff delay
RETRY_BACKOFF = 15


@celery_app.task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def process_data_reset_job(self, job_id: str):
    """
    Durable task to delete all user chat data from PostgreSQL and facts from Qdrant.
    It will retry automatically on failure.
    """

    async def _run():
        async with get_celery_db() as db:
            result = await db.execute(
                select(DataResetJob).filter(DataResetJob.id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job or job.status != DataResetJobStatus.PENDING_DELETION:
                return

            try:
                # 1. Reset Postgres Data
                await reset_user_chat_data(db, job.user_id)

                # 2. Reset Qdrant Data
                await delete_all_facts_for_user(job.user_id)

                # If both succeeded, mark as DELETED
                job.status = DataResetJobStatus.DELETED
                await db.commit()
                logger.info(
                    f"DataResetJob {job_id} successfully completed. User {job.user_id} data wiped."
                )
            except Exception as e:
                # We will log the error and let Celery retry if we haven't maxed out retries
                logger.error(f"Error processing DataResetJob {job_id}: {e!s}")
                # If this is the last retry, the autoretry_for won't catch it and it will raise.
                # However, autoretry_for handles the retries implicitly. We need to let it raise.
                raise e

    try:
        from app.core.async_utils import run_async

        run_async(_run())
    except Exception as exc:
        # If we reach here, it means we might have exhausted retries or something else failed.
        # Check if we should mark as FAILED
        if self.request.retries >= self.max_retries:

            async def _mark_failed():
                async with get_celery_db() as db:
                    await db.execute(
                        update(DataResetJob)
                        .where(DataResetJob.id == job_id)
                        .values(
                            status=DataResetJobStatus.FAILED,
                            error_message="Retries exhausted"[:255],
                        )
                    )
                    await db.commit()

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(_mark_failed())

        raise exc


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def extract_memory_task(
    self,
    user_id: str,
    session_id: str,
    message_id: str,
    user_message: str,
    previous_ai_message: str,
    channel: str,
):
    """
    Celery task to dynamically extract new facts from a single user message in real-time.
    """
    from app.services.llm_service import extract_facts_from_single_message
    from app.services.memory_service import store_facts

    async def _run():
        async with get_celery_db() as db:
            new_facts = await extract_facts_from_single_message(
                message=user_message,
                previous_ai_message=previous_ai_message,
                db=db,
                user_id=user_id,
                channel=channel,
            )
            if new_facts and isinstance(new_facts, list) and len(new_facts) > 0:
                await store_facts(
                    user_id,
                    new_facts,
                    source_message_ids=[message_id],
                    source_session_id=session_id,
                )

    try:
        from app.core.async_utils import run_async

        run_async(_run())
    except Exception as exc:
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(exc, SQLAlchemyError):
            logger.warning(f"Retrying extract_memory_task due to DB error: {exc}")
            raise self.retry(exc=exc)
        logger.error(f"Error in extract_memory_task: {exc}")
        raise exc


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def summarize_history_task(
    self,
    user_id: str,
    message_ids: list[str],
    channel: str,
):
    """
    Celery task to summarize older conversation history into memory facts.
    """
    from app.models.chat import Message
    from app.services.llm_service import extract_atomic_facts
    from app.services.memory_service import store_facts

    async def _run():
        from app.core.redis_client import redis_client

        lock_name = f"summarize_lock_{user_id}"
        lock = redis_client.lock(lock_name, timeout=300)
        acquired = await lock.acquire(blocking=False)

        if not acquired:
            logger.info(
                f"Summarization for user {user_id} is already in progress, skipping.",
                extra={"user_id": user_id},
            )
            return

        try:
            async with get_celery_db() as db:
                result = await db.execute(
                    select(Message)
                    .where(Message.id.in_(message_ids), Message.is_summarized == False)
                    .order_by(Message.created_at.asc())
                )
                msgs = result.scalars().all()
                if not msgs:
                    return

                conversation_text = "\n".join(
                    [f"{msg.role}: {msg.content}" for msg in msgs]
                )
                new_facts = await extract_atomic_facts(
                    conversation_text,
                    db=db,
                    user_id=user_id,
                    channel=channel,
                )

                if new_facts:
                    await store_facts(user_id, new_facts)

                for msg in msgs:
                    msg.is_summarized = True

                await db.commit()
                logger.info(
                    "Successfully summarized old history in background",
                    extra={"user_id": user_id, "messages_count": len(msgs)},
                )
        finally:
            # Only release if we successfully acquired it, which is true if we are in this block
            try:
                await lock.release()
            except Exception as e:
                logger.warning(f"Failed to release Redis lock {lock_name}: {e}")

    try:
        from app.core.async_utils import run_async

        run_async(_run())
    except Exception as exc:
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(exc, SQLAlchemyError):
            logger.warning(f"Retrying summarize_history_task due to DB error: {exc}")
            raise self.retry(exc=exc)
        logger.error(f"Error in summarize_history_task: {exc}")
        raise exc
