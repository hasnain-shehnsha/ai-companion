import socket
from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings


def force_ipv4_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname:
        try:
            ipv4 = socket.gethostbyname(parsed.hostname)
            new_netloc = parsed.netloc.replace(parsed.hostname, ipv4)
            parsed = parsed._replace(netloc=new_netloc)
            return urlunparse(parsed)
        except OSError:
            pass
    return url


db_url = settings.DATABASE_URL
db_url = force_ipv4_url(db_url)
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Limit pool_size and max_overflow to avoid exhausting Supabase's PgBouncer (pool_size: 15).
# By default, SQLAlchemy uses pool_size=5, max_overflow=10, which easily exceeds the limit when multiple workers are running.
# Base engine arguments
engine_kwargs = {}

if not db_url.startswith("sqlite"):
    engine_kwargs.update(
        {
            "pool_size": 2,
            "max_overflow": 2,
            "pool_timeout": 10,
            "pool_recycle": 1800,
        }
    )

engine = create_async_engine(db_url, echo=False, **engine_kwargs)

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
    Creates a new async session for use inside Celery tasks.
    Since we use NullPool in Celery, we can just use AsyncSessionLocal directly.
    """
    async with AsyncSessionLocal() as session:
        yield session
