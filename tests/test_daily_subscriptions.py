import random
import uuid
from datetime import UTC, datetime, time
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.subscription import DailySubscription
from app.models.subscription_delivery import DeliveryStatus, SubscriptionDelivery
from app.models.user import User
from app.tasks.scheduler_tasks import (
    _process_subscriptions_async,
    _recover_pending_deliveries_async,
)
from app.tasks.subscription_tasks import _process_delivery_async


@pytest.fixture
async def test_user_sub(db_session):
    user = User(
        email=f"subtest_{uuid.uuid4()}@example.com",
        hashed_password="test",
        first_name="Sub",
        last_name="Test",
        tier="PAID",
        whatsapp_number=f"+92{random.randint(3000000000, 3999999999)}",
        whatsapp_verified=True,
        timezone="UTC",
    )
    db_session.add(user)
    await db_session.commit()

    # Subscription due now
    now_utc = datetime.now(UTC)
    sub = DailySubscription(
        user_id=user.id,
        topic="Motivation",
        time_of_day=time(hour=now_utc.hour, minute=now_utc.minute),
        is_active=True,
    )
    db_session.add(sub)
    await db_session.commit()

    yield user, sub

    await db_session.delete(sub)
    await db_session.delete(user)
    await db_session.commit()


@pytest.mark.asyncio
@patch("app.tasks.subscription_tasks.process_daily_delivery.delay")
async def test_scheduler_enqueues_delivery(mock_delay, test_user_sub, db_session):
    user, sub = test_user_sub

    # Run scheduler
    await _process_subscriptions_async()

    # Check that a SubscriptionDelivery was created
    stmt = select(SubscriptionDelivery).where(
        SubscriptionDelivery.subscription_id == sub.id
    )
    result = await db_session.execute(stmt)
    delivery = result.scalar_one_or_none()

    assert delivery is not None
    assert delivery.status == DeliveryStatus.PENDING
    mock_delay.assert_called_once_with(delivery.id)

    # Cleanup
    await db_session.delete(delivery)
    await db_session.commit()


@pytest.mark.asyncio
@patch("app.services.llm_gateway.generate_llm_response")
@patch("app.tasks.subscription_tasks.send_whatsapp_template")
async def test_process_delivery_success(mock_send, mock_llm, test_user_sub, db_session):
    user, sub = test_user_sub

    mock_llm.return_value = ("Hello Motivation!", None)
    mock_send.return_value = True

    # Create PENDING delivery
    delivery = SubscriptionDelivery(
        subscription_id=sub.id,
        delivery_date=datetime.now(UTC).date(),
        status=DeliveryStatus.PENDING,
    )
    db_session.add(delivery)
    await db_session.commit()

    # Process
    await _process_delivery_async(delivery.id)

    # Refresh
    await db_session.refresh(delivery)
    await db_session.refresh(sub)

    assert delivery.status == DeliveryStatus.SENT
    assert delivery.attempt_count == 1
    assert sub.last_successful_delivery_date == delivery.delivery_date

    # Cleanup
    await db_session.delete(delivery)
    await db_session.commit()


@pytest.mark.asyncio
@patch("app.services.llm_gateway.generate_llm_response")
async def test_process_delivery_failure_is_retryable(
    mock_llm, test_user_sub, db_session
):
    user, sub = test_user_sub

    # Simulate LLM failure
    mock_llm.side_effect = Exception("LLM Error")

    # Create PENDING delivery
    delivery = SubscriptionDelivery(
        subscription_id=sub.id,
        delivery_date=datetime.now(UTC).date(),
        status=DeliveryStatus.PENDING,
    )
    db_session.add(delivery)
    await db_session.commit()

    # Process (will fail)
    try:
        await _process_delivery_async(delivery.id)
    except Exception as e:
        assert str(e) == "LLM Error"

    # Refresh
    await db_session.refresh(delivery)
    await db_session.refresh(sub)

    # Should be marked FAILED, but parent subscription last_successful is NOT updated
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.failure_reason == "LLM Error"
    assert sub.last_successful_delivery_date is None

    # Recover should pick it up
    with patch(
        "app.tasks.subscription_tasks.process_daily_delivery.delay"
    ) as mock_delay:
        await _recover_pending_deliveries_async()
        mock_delay.assert_called_once_with(delivery.id)

    # Cleanup
    await db_session.delete(delivery)
    await db_session.commit()
