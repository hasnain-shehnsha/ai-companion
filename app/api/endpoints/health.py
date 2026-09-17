import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import redis_client
from app.services import memory_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/live", status_code=status.HTTP_200_OK)
async def live():
    """Liveness probe: Just returns 200 OK to indicate the process is running."""
    return {"status": "alive"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def ready(db: AsyncSession = Depends(get_db)):
    """Readiness probe: Checks PostgreSQL, Redis, Qdrant, and Config."""
    issues = []

    # 1. PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"PostgreSQL readiness check failed: {e}")
        issues.append("PostgreSQL unreachable")

    # 2. Redis / Celery broker
    try:
        await redis_client.ping()
    except Exception as e:
        logger.error(f"Redis readiness check failed: {e}")
        issues.append("Redis unreachable")

    # 3. Qdrant
    qdrant_client = memory_service.client
    if qdrant_client is not None:
        try:
            # get_collections is synchronous in QdrantClient
            await asyncio.to_thread(qdrant_client.get_collections)
        except Exception as e:
            logger.error(f"Qdrant readiness check failed: {e}")
            issues.append("Qdrant unreachable")
    else:
        # If QDRANT_URL is set but client is None, it failed to initialize.
        if settings.QDRANT_URL or settings.ENVIRONMENT == "production":
            logger.error("Qdrant client not initialized.")
            issues.append("Qdrant uninitialized")

    # 4. Required Configuration
    if settings.ENVIRONMENT == "production":
        if not settings.SECRET_KEY or settings.SECRET_KEY == "testsecret12345":
            issues.append("Invalid SECRET_KEY in production")
        if not settings.RESEND_API_KEY:
            issues.append("Missing RESEND_API_KEY in production")
        if not settings.WHATSAPP_TOKEN:
            issues.append("Missing WHATSAPP_TOKEN in production")
        if not settings.RESEND_FROM_EMAIL or not settings.RESEND_FROM_NAME:
            issues.append("Missing RESEND_FROM identity configuration")

    if issues:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "issues": issues},
        )

    return {"status": "ready"}
