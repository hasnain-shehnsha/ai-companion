import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from groq import AsyncGroq, GroqError

from app.core.config import settings
from app.core.exceptions import QuotaExceededException
from app.core.redis_client import redis_client
from app.tasks.usage_tasks import log_usage_task

logger = logging.getLogger(__name__)

client = AsyncGroq(api_key=settings.GROQ_API_KEY)
MODEL = "qwen/qwen3.8-27b"
FALLBACK_MODEL = "openai/gpt-oss-120b"


def _completion_content(chat_completion) -> tuple[str, str | None]:
    choice = chat_completion.choices[0] if chat_completion.choices else None
    content = choice.message.content if choice else ""
    return content or "", getattr(choice, "finish_reason", None)


async def generate_llm_response(
    messages: list[dict],
    user_id: str | None = None,
    user_timezone: str = "UTC",
    quota_limit: int | None = None,
    model: str = MODEL,
    channel: str = "web",
    request_type: str = "chat",
    max_tokens: int = 800,
    **kwargs,
) -> tuple[str, str]:
    """
    Central gateway for all LLM calls.
    Handles quota reservation, execution, telemetry, and error reconciliation.
    Returns (content, finish_reason).
    """
    # 1. Quota Reservation Phase (Only for 'chat' requests where user is known)
    quota_key = None
    if request_type == "chat" and user_id and quota_limit is not None:
        try:
            user_tz = ZoneInfo(user_timezone)
        except ZoneInfoNotFoundError:
            user_tz = ZoneInfo("UTC")

        local_date_str = datetime.now(user_tz).strftime("%Y-%m-%d")
        quota_key = f"quota:chat:{user_id}:{local_date_str}"

        try:
            count = await redis_client.incr(quota_key)
            if count == 1:
                await redis_client.expire(quota_key, 86400 * 2)  # 2 days expiry

            if count > quota_limit:
                await redis_client.decr(quota_key)
                raise QuotaExceededException(
                    f"You've reached your daily limit of {quota_limit} messages. Please try again tomorrow!"
                )
        except Exception as e:
            if isinstance(e, QuotaExceededException):
                raise
            # If Redis fails, log it and bypass quota check rather than failing the request
            logger.warning(f"Redis quota check failed: {e}")
            quota_key = None

    # 2. Execution Phase
    start_time = time.time()
    chat_completion = None
    error_state = None
    content = ""
    finish_reason = ""

    try:
        chat_completion = await client.chat.completions.create(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            **kwargs,
        )
        content, finish_reason = _completion_content(chat_completion)

        # If the primary model unexpectedly returns empty content, treat it as a failure
        if not content or not content.strip():
            logger.warning(
                f"Primary model {model} returned empty content, triggering fallback."
            )
            raise GroqError("Empty response content from primary model")

    except GroqError as e:
        error_state = f"GroqError: {e!s}"
        logger.error(f"Primary LLM model failed: {e}")

        # Fallback attempt
        try:
            chat_completion = await client.chat.completions.create(
                messages=messages,
                model=FALLBACK_MODEL,
                max_tokens=max_tokens,
                **kwargs,
            )
            model = FALLBACK_MODEL
            content, finish_reason = _completion_content(chat_completion)
            error_state = None  # Recovered

            if not content or not content.strip():
                error_state = "Fallback model also returned empty content"
                logger.error(error_state)
        except GroqError as fallback_err:
            error_state = f"GroqError(Fallback): {fallback_err!s}"
            logger.error(f"Fallback LLM model also failed: {fallback_err}")

    except Exception as e:
        error_state = f"Unexpected Error: {e!s}"
        logger.exception("Unexpected error in generate_llm_response")

    # Reconciliation Phase
    if not chat_completion and quota_key:
        try:
            await redis_client.decr(quota_key)
        except Exception as e:
            logger.warning(f"Failed to reconcile quota in Redis: {e}")

    # 3. Telemetry Phase
    latency_ms = (time.time() - start_time) * 1000.0
    input_tokens = 0
    output_tokens = 0
    cost = 0.0

    if chat_completion:
        usage = getattr(chat_completion, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        cost = (input_tokens + output_tokens) * 0.0000005

    log_usage_task.delay(
        user_id,
        model,
        input_tokens,
        output_tokens,
        request_type,
        channel,
        cost,
        latency_ms,
        error_state,
    )

    if error_state and not chat_completion:
        raise Exception(error_state)

    return content, finish_reason
