import pytest


@pytest.fixture(autouse=True)
def _reset_cache_module_state():
    """app/core/cache.py caches its Redis client + availability flag at
    module level; reset between tests so one test's Redis-down simulation
    doesn't leak into the next test's happy-path check."""
    from app.core import cache

    def _reset():
        cache._client = None
        cache._client_unavailable = False
        cache._async_client = None
        cache._async_client_unavailable = False

    _reset()
    yield
    _reset()
