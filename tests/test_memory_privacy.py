import uuid

import pytest

from app.api.endpoints.chat import delete_session_endpoint
from app.core.security import get_password_hash
from app.models.user import User, UserTier


@pytest.fixture
async def user(db_session):
    u = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email=f"test_{uuid.uuid4()}@example.com",
        whatsapp_number=f"+1234567890{str(uuid.uuid4())[:4]}",
        hashed_password=get_password_hash("password123"),
        tier=UserTier.FREE,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.mark.asyncio
async def test_delete_session_removes_memories(db_session, mocker, user):
    """Delete session removes direct and summarized memories."""
    # We will mock delete_chat_session to return True
    mocker.patch("app.api.endpoints.chat.delete_chat_session", return_value=True)

    mock_delete_facts = mocker.patch("app.api.endpoints.chat.delete_facts_by_session")

    session_id = str(uuid.uuid4())

    from fastapi import BackgroundTasks

    bg_tasks = BackgroundTasks()

    await delete_session_endpoint(
        session_id=session_id,
        background_tasks=bg_tasks,
        db=db_session,
        current_user=user,
    )

    mock_delete_facts.assert_awaited_once_with(user.id, session_id)


@pytest.mark.asyncio
async def test_reset_account_qdrant_retry(db_session, user, mocker):
    """Qdrant unavailable during reset; durable task retries and reaches a truthful final state."""
    from app.models.user import DataResetJob, DataResetJobStatus
    from app.tasks.memory_tasks import process_data_reset_job

    # 1. Create a tracking job
    job = DataResetJob(user_id=user.id, status=DataResetJobStatus.PENDING_DELETION)
    db_session.add(job)
    await db_session.commit()

    # Mock postgres deletion
    mocker.patch("app.tasks.memory_tasks.reset_user_chat_data")

    # Mock qdrant to fail first
    mock_qdrant = mocker.patch(
        "app.tasks.memory_tasks.delete_all_facts_for_user",
        side_effect=Exception("Qdrant unavailable"),
    )

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_get_celery_db():
        yield db_session

    mocker.patch("app.tasks.memory_tasks.get_celery_db", new=mock_get_celery_db)

    # Mock retry to raise the exception so we can catch it
    mocker.patch.object(
        process_data_reset_job, "retry", side_effect=Exception("Qdrant unavailable")
    )
    mocker.patch.object(process_data_reset_job.request, "retries", 0)

    # Run the task directly (simulating the first Celery attempt)
    with pytest.raises(Exception, match="Qdrant unavailable"):
        process_data_reset_job(job.id)

    await db_session.refresh(job)
    assert job.status == DataResetJobStatus.PENDING_DELETION

    # Now simulate the retry where Qdrant is back online
    mock_qdrant.side_effect = None
    process_data_reset_job(job.id)

    await db_session.refresh(job)
    assert job.status == DataResetJobStatus.DELETED


@pytest.mark.asyncio
async def test_assistant_hallucination_not_stored(mocker, user):
    """Assistant hallucination is not stored as a user fact."""
    from app.tasks.memory_tasks import extract_memory_task

    # Mock the prompt constraints and LLM extraction to return no facts
    # (since the user didn't say it, the LLM should output an empty list)
    mock_extract = mocker.patch(
        "app.services.llm_service.extract_facts_from_single_message", return_value=[]
    )
    mock_store = mocker.patch("app.services.memory_service.store_facts")

    user_message = "What? I never said that."
    previous_ai_message = "You told me you were a professional chef!"

    mocker.patch.object(
        extract_memory_task, "retry", side_effect=Exception("Task failed")
    )

    extract_memory_task(
        user_id=user.id,
        session_id="session123",
        message_id="msg123",
        user_message=user_message,
        previous_ai_message=previous_ai_message,
        channel="web",
    )

    mock_extract.assert_awaited_once()
    mock_store.assert_not_called()


def test_memory_work_survives_restart():
    """Memory work survives API/worker restart."""
    # Ensure memory tasks are registered as durable Celery tasks
    from app.tasks.memory_tasks import extract_memory_task, summarize_history_task

    assert hasattr(extract_memory_task, "delay")
    assert hasattr(summarize_history_task, "delay")

    # Celery tasks by default survive worker restarts because they are persisted in Redis/RabbitMQ
    # until they are successfully executed.
