import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

os.environ["ENVIRONMENT"] = "test"
# Ensure we don't accidentally wipe the production database!
if "TEST_DATABASE_URL" in os.environ:
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    # Use SQLite by default for tests to avoid hitting the prod remote DB
    # Using shared cache so :memory: persists across connections
    os.environ["DATABASE_URL"] = (
        "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"
    )

from app.core.config import settings
from app.core.database import Base, get_db
from main import app


@pytest_asyncio.fixture
async def db_session():
    """Yield a database session and rollback all changes after each test."""
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    is_sqlite = db_url.startswith("sqlite")
    pool_class = StaticPool if is_sqlite else NullPool
    engine = create_async_engine(
        db_url,
        echo=False,
        poolclass=pool_class,
        **({"connect_args": {"check_same_thread": False}} if is_sqlite else {}),
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    connection = await engine.connect()
    trans = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await connection.close()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def async_client(db_session):
    """Yield an AsyncClient for FastAPI endpoint testing with db override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_external_services(mocker):
    """Automatically mock all external network calls (Qdrant, Groq, Celery, Resend)."""
    # Mock Qdrant
    mocker.patch("app.services.memory_service.QdrantClient")
    mocker.patch("app.services.memory_service.TextEmbedding")

    # Mock Groq LLM
    mocker.patch(
        "app.services.llm_service.generate_chat_completion",
        return_value="Mock LLM response",
    )
    mocker.patch(
        "app.services.ai_service.generate_chat_completion",
        return_value="Mock LLM response",
    )
    mocker.patch(
        "app.api.endpoints.chat.generate_session_title",
        return_value="Test Conversation",
    )
    mocker.patch(
        "app.services.llm_gateway.generate_llm_response",
        return_value=(
            '{"intent": "CHAT", "datetime_iso": null, "reminder_text": null, "is_general_question": false, "search_query": null}',
            None,
        ),
    )

    # Mock Celery Tasks
    mocker.patch("app.tasks.reminder_tasks.send_reminder_email.apply_async")

    # Mock external WhatsApp sender
    mocker.patch(
        "app.services.whatsapp_service.send_whatsapp_message", return_value=True
    )


@pytest.fixture(autouse=True)
def disable_rate_limits(mocker):
    """Disable slowapi rate limits during testing."""
    # Patch the global limiter instance in main
    mocker.patch("main.limiter.enabled", False)
