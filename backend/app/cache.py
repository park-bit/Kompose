import time
import json
import logging
from typing import Any
import redis.asyncio as aioredis
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis: aioredis.Redis | None = None
_redis_disabled = False
_in_memory_cache: dict[str, tuple[float, str]] = {}


async def get_redis() -> aioredis.Redis | None:
    global _redis, _redis_disabled
    if _redis_disabled:
        return None
    if _redis is None and settings.redis_url:
        try:
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            await r.ping()
            _redis = r
        except Exception as exc:
            logger.info("Redis not available (%s), using in-memory cache fallback.", exc)
            _redis_disabled = True
            return None
    return _redis


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    if r:
        try:
            value = await r.get(key)
            if value:
                return json.loads(value)
        except Exception:
            pass

    # In-memory cache fallback
    item = _in_memory_cache.get(key)
    if item:
        exp, val = item
        if time.time() < exp:
            return json.loads(val)
        else:
            del _in_memory_cache[key]
    return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    raw = json.dumps(value, default=str)
    r = await get_redis()
    if r:
        try:
            await r.setex(key, ttl, raw)
            return
        except Exception:
            pass

    # In-memory cache fallback
    _in_memory_cache[key] = (time.time() + ttl, raw)


async def close_redis():
    global _redis
    if _redis:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None
