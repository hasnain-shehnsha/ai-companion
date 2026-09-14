from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


from contextlib import asynccontextmanager


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_celery_db():
    """
    Creates a new async engine and session for use inside Celery tasks.
    This avoids sharing the global engine across forks.
    """
    local_engine = create_async_engine(db_url, echo=False)
    LocalAsyncSession = async_sessionmaker(
        local_engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with LocalAsyncSession() as session:
            yield session
    finally:
        await local_engine.dispose()
