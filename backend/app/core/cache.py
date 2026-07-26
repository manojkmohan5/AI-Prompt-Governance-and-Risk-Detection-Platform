"""
Redis-backed cache for the two expensive transformer forward passes in the
governance pipeline: the DistilBERT classifier (app.governance.ml_classifier)
and the Knowledge Shield similarity search (app.embeddings.knowledge_shield).

Optional by design, same pattern as app/embeddings/encoder.py: if Redis is
unreachable or the redis package isn't installed, every call here is a no-op
and callers fall back to running the forward pass uncached rather than
failing. Redis is never a hard dependency of the app.

Cache keys are namespaced with a fingerprint of the underlying model/index
(see classifier_fingerprint / knowledge_shield_fingerprint) so a retrain or
a Knowledge Shield document change naturally invalidates old entries instead
of silently serving stale scores under an unchanged key.
"""
import hashlib
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None
_client_unavailable = False

_async_client = None
_async_client_unavailable = False


def _get_client():
    global _client, _client_unavailable
    if _client_unavailable or not settings.CACHE_ENABLED:
        return None
    if _client is not None:
        return _client
    try:
        import redis
        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        _client = client
        logger.info("Redis cache connected: %s", settings.REDIS_URL)
        return _client
    except Exception as e:
        logger.warning("Redis unavailable, running without cache: %s", e)
        _client_unavailable = True
        return None


def _get_async_client():
    global _async_client, _async_client_unavailable
    if _async_client_unavailable or not settings.CACHE_ENABLED:
        return None
    if _async_client is not None:
        return _async_client
    try:
        import redis.asyncio as aioredis
        _async_client = aioredis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        return _async_client
    except Exception as e:
        logger.warning("Redis (async) unavailable, running without cache: %s", e)
        _async_client_unavailable = True
        return None


def build_key(namespace: str, text: str, fingerprint: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"governance:{namespace}:{fingerprint}:{digest}"


def cache_get(key: str) -> str | None:
    global _client_unavailable
    client = _get_client()
    if client is None:
        return None
    try:
        val = client.get(key)
        return val.decode("utf-8") if val is not None else None
    except Exception as e:
        logger.warning("Redis GET failed, disabling cache: %s", e)
        _client_unavailable = True
        return None


def cache_set(key: str, value: str, ttl: int | None = None) -> None:
    global _client_unavailable
    client = _get_client()
    if client is None:
        return
    try:
        client.setex(key, ttl or settings.CACHE_TTL_SECONDS, value)
    except Exception as e:
        logger.warning("Redis SET failed, disabling cache: %s", e)
        _client_unavailable = True


async def cache_get_async(key: str) -> str | None:
    global _async_client_unavailable
    client = _get_async_client()
    if client is None:
        return None
    try:
        val = await client.get(key)
        return val.decode("utf-8") if val is not None else None
    except Exception as e:
        logger.warning("Redis (async) GET failed, disabling cache: %s", e)
        _async_client_unavailable = True
        return None


async def cache_set_async(key: str, value: str, ttl: int | None = None) -> None:
    global _async_client_unavailable
    client = _get_async_client()
    if client is None:
        return
    try:
        await client.setex(key, ttl or settings.CACHE_TTL_SECONDS, value)
    except Exception as e:
        logger.warning("Redis (async) SET failed, disabling cache: %s", e)
        _async_client_unavailable = True


def classifier_fingerprint() -> str:
    """Changes whenever the fine-tuned classifier is retrained, so stale
    cache entries from a previous model version are never served."""
    from app.governance.ml_classifier import MODEL_CACHE
    weights = MODEL_CACHE / "model.safetensors"
    try:
        stat = weights.stat()
        return f"{stat.st_mtime_ns}-{stat.st_size}"
    except FileNotFoundError:
        return "untrained"


def knowledge_shield_fingerprint() -> str:
    """Changes whenever the Knowledge Shield document set is (re)built."""
    from app.embeddings import knowledge_shield
    return getattr(knowledge_shield, "_index_version", "none")
