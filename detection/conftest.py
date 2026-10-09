import asyncio
import importlib
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture(autouse=True)
def _reset_cache_module_state():
    """detection/cache.py caches its Redis client + availability flag at
    module level; reset between tests so one test's Redis-down simulation
    doesn't leak into the next test's happy-path check."""
    from detection import cache

    def _reset():
        cache._client = None
        cache._client_unavailable = False
        cache._async_client = None
        cache._async_client_unavailable = False

    _reset()
    yield
    _reset()


@pytest.fixture
def db_engine(tmp_path):
    """
    An empty database with every table created, for one test: a SQLite file,
    or with TEST_DATABASE_URL set (CI's second run) a real Postgres, emptied
    first. NullPool, because an asyncpg connection cannot move between the
    event loops of separate asyncio.run calls.
    """
    from detection.database import Base
    importlib.import_module("detection.models")    # registers the table on Base.metadata

    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(url, poolclass=NullPool)

    async def _fresh():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_fresh())
    yield engine
    asyncio.run(engine.dispose())
