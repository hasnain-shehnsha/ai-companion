import os
import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine.reflection import Inspector

def test_fresh_database_migrations():
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
            "daily_subscriptions"
        ]

        for table in required_tables:
            assert table in tables, f"Table '{table}' is missing from the database after running migrations!"
    finally:
        # Clean up so we don't interfere with other tests that use create_all
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

