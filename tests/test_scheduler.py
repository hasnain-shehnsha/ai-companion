import datetime
import uuid

import pytest

from app.core.security import get_password_hash
from app.models.subscription import DailySubscription
from app.models.user import User
from app.tasks.scheduler_tasks import _process_subscriptions_async


@pytest.fixture
async def subscription_users(db_session):
    karachi_time = datetime.time(
        9, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5))
    )
    new_york_time = datetime.time(
        9, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-5))
    )
    users = [
        User(
            id=str(uuid.uuid4()),
            first_name="Karachi",
            last_name="User",
            email="sub@example.com",
            hashed_password=get_password_hash("password123"),
            timezone="Asia/Karachi",
            whatsapp_number="+923001234567",
        ),
        User(
            id=str(uuid.uuid4()),
            first_name="New York",
            last_name="User",
            email="foreign@example.com",
            hashed_password=get_password_hash("password123"),
            timezone="America/New_York",
            whatsapp_number="+14155552671",
        ),
    ]
    db_session.add_all(users)
    await db_session.flush()
    db_session.add_all(
        [
            DailySubscription(
                id=str(uuid.uuid4()),
                user_id=users[0].id,
                topic="morning motivation",
                time_of_day=karachi_time,
                is_active=True,
            ),
            DailySubscription(
                id=str(uuid.uuid4()),
                user_id=users[1].id,
                topic="morning motivation",
                time_of_day=new_york_time,
                is_active=True,
            ),
            DailySubscription(
                id=str(uuid.uuid4()),
                user_id=users[0].id,
                topic="disabled topic",
                time_of_day=karachi_time,
                is_active=False,
            ),
        ]
    )
    await db_session.commit()
    return users


def mock_scheduler_time(mocker):
    mock_now_utc = datetime.datetime(2025, 1, 1, 4, 0, 0, tzinfo=datetime.UTC)

    class MockDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return mock_now_utc if tz == datetime.UTC else mock_now_utc.astimezone(tz)

    mocker.patch("app.tasks.scheduler_tasks.datetime", MockDatetime)


async def test_scheduler_correct_timezone(subscription_users, mocker, db_session):
    mock_scheduler_time(mocker)
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.scheduler_tasks.get_celery_db", test_celery_db)
    mock_delay = mocker.patch(
        "app.tasks.subscription_tasks.process_daily_delivery.delay"
    )

    await _process_subscriptions_async()

    # It should enqueue the task for the Karachi user
    mock_delay.assert_called_once()


async def test_scheduler_does_not_send_same_subscription_twice(
    subscription_users, mocker, db_session
):
    mock_scheduler_time(mocker)
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def test_celery_db():
        yield db_session

    mocker.patch("app.tasks.scheduler_tasks.get_celery_db", test_celery_db)
    mock_delay = mocker.patch(
        "app.tasks.subscription_tasks.process_daily_delivery.delay"
    )

    await _process_subscriptions_async()
    await _process_subscriptions_async()

    # Still only called once because the second run sees the delivery already exists
    mock_delay.assert_called_once()
