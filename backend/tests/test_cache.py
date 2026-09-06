"""
Tests for app/core/cache.py — the optional Redis cache for the classifier
and Knowledge Shield. Deliberately doesn't import torch/transformers (ML
deps aren't installed in CI); and
knowledge_shield_fingerprint() only touch a file path / a module attribute,
so they're safe to exercise without a trained model.
"""
import pytest

from app.core import cache
from app.core.config import settings


def test_build_key_is_deterministic():
    k1 = cache.build_key("ns", "hello world", "fp1")
    k2 = cache.build_key("ns", "hello world", "fp1")
    assert k1 == k2


def test_build_key_differs_by_text():
    k1 = cache.build_key("ns", "hello", "fp1")
    k2 = cache.build_key("ns", "world", "fp1")
    assert k1 != k2


def test_build_key_differs_by_fingerprint():
    k1 = cache.build_key("ns", "hello", "fp1")
    k2 = cache.build_key("ns", "hello", "fp2")
    assert k1 != k2


def test_cache_set_get_roundtrip():
    key = cache.build_key("test", "roundtrip-check", "fp")
    cache.cache_set(key, "the-value", ttl=30)
    assert cache.cache_get(key) == "the-value"


def test_cache_get_miss_returns_none():
    key = cache.build_key("test", "never-set-this-key", "fp")
    assert cache.cache_get(key) is None


@pytest.mark.asyncio
async def test_cache_set_get_roundtrip_async():
    key = cache.build_key("test-async", "roundtrip-check-async", "fp")
    await cache.cache_set_async(key, "the-async-value", ttl=30)
    assert await cache.cache_get_async(key) == "the-async-value"
    # Close explicitly within this test's still-active event loop, otherwise
    # the connection's __del__ fires after loop teardown and pytest reports
    # a spurious "Event loop is closed" warning.
    await cache._async_client.aclose()


def test_cache_degrades_gracefully_when_redis_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:1/0")
    key = cache.build_key("test", "should-not-crash", "fp")
    cache.cache_set(key, "value")  # must not raise
    assert cache.cache_get(key) is None  # must not raise


def test_knowledge_shield_fingerprint_returns_nonempty_string():
    fp = cache.knowledge_shield_fingerprint()
    assert isinstance(fp, str) and len(fp) > 0
