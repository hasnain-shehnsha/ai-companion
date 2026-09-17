import redis.asyncio as redis

from app.core.config import settings

# Create a globally reusable asynchronous Redis client
# We use decode_responses=True so that strings are returned instead of bytes.
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
