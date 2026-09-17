import os

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine.reflection import Inspector

from alembic import command


def test_fresh_database_migrations():
    if "TEST_DATABASE_URL" not in os.environ:
        pytest.skip(
            "Skipping migration tests because TEST_DATABASE_URL is not set. Refusing to wipe the production database or run Postgres migrations on SQLite."
        )

    # Use the existing test database URL
    os.environ["ENVIRONMENT"] = "test"
    from app.core.config import settings

    db_url = settings.DATABASE_URL
    sync_db_url = db_url.replace("+asyncpg", "") if "+asyncpg" in db_url else db_url

    engine = create_engine(sync_db_url, isolation_level="AUTOCOMMIT")

    # Clear the database schema completely
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    alembic_cfg = Config("alembic.ini")

    try:
        # Run all migrations up to head
        command.upgrade(alembic_cfg, "head")

        # Connect to the freshly migrated database and check its tables
        inspector = Inspector.from_engine(engine)
        tables = inspector.get_table_names()

        required_tables = [
            "users",
            "chat_sessions",
            "messages",
            "usage_records",
            "reminders",
            "webhook_events",
            "daily_subscriptions",
        ]

        for table in required_tables:
            assert (
                table in tables
            ), f"Table '{table}' is missing from the database after running migrations!"

        # Verify indexes and constraints for a critical table like usage_records
        usage_indexes = [idx["name"] for idx in inspector.get_indexes("usage_records")]
        assert (
            "ix_usage_records_id" in usage_indexes
        ), "Missing primary index on usage_records"

        usage_fks = inspector.get_foreign_keys("usage_records")
        assert any(
            fk["referred_table"] == "users" for fk in usage_fks
        ), "Missing foreign key to users in usage_records"

        # Requirement 1: Application smoke test
        # We can quickly test that the FastApi app can start up and the database connection works
        import asyncio

        from httpx import ASGITransport, AsyncClient

        from main import app

        async def run_smoke_test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get("/health/live")
                assert response.status_code == 200
                assert response.json() == {"status": "alive"}

        asyncio.run(run_smoke_test())

    finally:
        # Clean up so we don't interfere with other tests that use create_all
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
