from limits.storage import RedisStorage
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Determine the correct redis URL scheme (limits doesn't support redis+asyncio or redis:// for strict sync operations by default, but it supports standard redis://)
redis_url = settings.REDIS_URL

# SlowAPI is synchronous. Make sure the redis driver is compatible.
try:
    storage = RedisStorage(redis_url)
    limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)
except Exception:
    # Fallback to memory if redis fails to connect
    limiter = Limiter(key_func=get_remote_address)
