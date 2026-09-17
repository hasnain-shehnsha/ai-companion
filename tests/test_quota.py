import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.core.exceptions import QuotaExceededException
from app.services.llm_gateway import generate_llm_response


@pytest.mark.asyncio
async def test_concurrent_quota_requests(mocker):
    """Multiple simultaneous requests at the final quota slot allow only the permitted number."""
    # Mock LLM client so it doesn't actually call Groq
    mock_llm = mocker.patch("app.services.llm_gateway.client.chat.completions.create")
    mock_llm.return_value.choices = []
    mocker.patch("app.services.llm_gateway.log_usage_task.delay")

    # We want 3 concurrent requests, but only 1 slot remaining.
    quota_limit = 1
    user_id = f"user_concurrent_{uuid.uuid4()}"

    async def make_request():
        try:
            await generate_llm_response(
                messages=[{"role": "user", "content": "hi"}],
                user_id=user_id,
                quota_limit=quota_limit,
                request_type="chat",
            )
            return True
        except QuotaExceededException:
            return False

    # Run 5 requests concurrently
    results = await asyncio.gather(*(make_request() for _ in range(5)))

    # Exactly 1 should succeed, 4 should fail
    successes = sum(results)
    assert successes == 1
    assert results.count(False) == 4


@pytest.mark.asyncio
async def test_all_llm_request_types_appear_in_usage(mocker):
    """All LLM request types appear in usage totals."""
    mock_llm = mocker.patch("app.services.llm_gateway.client.chat.completions.create")
    mock_llm.return_value.choices = []

    mock_log_usage = mocker.patch("app.services.llm_gateway.log_usage_task.delay")

    # Send a memory extraction request
    await generate_llm_response(
        messages=[{"role": "user", "content": "extract"}],
        user_id="user_usage",
        request_type="memory_extraction",
        channel="background",
    )

    # Send a chat request
    await generate_llm_response(
        messages=[{"role": "user", "content": "hi"}],
        user_id="user_usage",
        request_type="chat",
        channel="whatsapp",
    )

    assert mock_log_usage.call_count == 2

    # Check that the first call logged the memory extraction
    call1 = mock_log_usage.call_args_list[0]
    assert call1.args[4] == "memory_extraction"
    assert call1.args[5] == "background"

    # Check that the second call logged the chat
    call2 = mock_log_usage.call_args_list[1]
    assert call2.args[4] == "chat"
    assert call2.args[5] == "whatsapp"


@pytest.mark.asyncio
async def test_user_local_daily_reset_boundary(mocker):
    """User-local daily reset boundary is correct."""
    # We'll patch datetime.now in llm_gateway to return a fixed UTC time
    # where the local date differs by timezone.

    class MockDatetime:
        @classmethod
        def now(cls, tz=None):
            # Let's say it's 2024-05-01 02:00:00 UTC
            dt = datetime(2024, 5, 1, 2, 0, 0, tzinfo=UTC)
            if tz:
                return dt.astimezone(tz)
            return dt

    mocker.patch("app.services.llm_gateway.datetime", MockDatetime)

    mock_llm = mocker.patch("app.services.llm_gateway.client.chat.completions.create")
    mock_llm.return_value.choices = []
    mocker.patch("app.services.llm_gateway.log_usage_task.delay")
    mock_incr = mocker.patch(
        "app.services.llm_gateway.redis_client.incr", return_value=1
    )
    mock_expire = mocker.patch("app.services.llm_gateway.redis_client.expire")

    # For a user in UTC, the date is 2024-05-01
    await generate_llm_response(
        messages=[{"role": "user", "content": "hi"}],
        user_id="user_utc",
        user_timezone="UTC",
        quota_limit=10,
        request_type="chat",
    )

    mock_incr.assert_called_with("quota:chat:user_utc:2024-05-01")

    # For a user in America/Los_Angeles (UTC-7), the date is STILL 2024-04-30 !
    await generate_llm_response(
        messages=[{"role": "user", "content": "hi"}],
        user_id="user_la",
        user_timezone="America/Los_Angeles",
        quota_limit=10,
        request_type="chat",
    )

    mock_incr.assert_called_with("quota:chat:user_la:2024-04-30")
