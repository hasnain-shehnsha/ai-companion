import logging
import uuid

from app.core.celery_app import celery_app
from app.core.database import get_celery_db
from app.models.usage import UsageRecord

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def log_usage_task(
    self,
    user_id: str,
    selected_model: str,
    input_tokens: int,
    output_tokens: int,
    request_type: str,
    channel: str,
    estimated_cost: float,
    latency_ms: float = None,
    error_state: str = None,
):
    """
    Durable Celery task to record LLM usage in the background.
    """
    try:
        from app.core.async_utils import run_async

        run_async(
            _log_usage_async(
                user_id,
                selected_model,
                input_tokens,
                output_tokens,
                request_type,
                channel,
                estimated_cost,
                latency_ms,
                error_state,
            )
        )
    except Exception as exc:
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(exc, SQLAlchemyError):
            logger.warning(f"Retrying log_usage_task due to DB error: {exc}")
            raise self.retry(exc=exc)
        logger.error(f"Error in log_usage_task: {exc}")
        raise exc


async def _log_usage_async(
    user_id: str,
    selected_model: str,
    input_tokens: int,
    output_tokens: int,
    request_type: str,
    channel: str,
    estimated_cost: float,
    latency_ms: float,
    error_state: str,
):
    async with get_celery_db() as db:
        record = UsageRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            model=selected_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_type=request_type,
            channel=channel,
            estimated_cost=estimated_cost,
            latency_ms=latency_ms,
            error_state=error_state,
        )
        db.add(record)
        await db.commit()
        logger.info(
            "Successfully recorded LLM usage durably", extra={"user_id": user_id}
        )
