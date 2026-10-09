import asyncio
import importlib
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
def db_engine(tmp_path):
    """
    An empty database with every table created, for one test.

    A SQLite file by default. With TEST_DATABASE_URL set - CI runs the suite a
    second time against a real Postgres - that database, emptied first. The two
    differ in ways that only show at runtime (boolean literals, enforced
    VARCHAR lengths), so the same tests run on both.

    NullPool: tests drive the app through several asyncio.run calls, each with
    its own event loop, and an asyncpg connection cannot move between loops.
    """
    from app.core.database import Base
    importlib.import_module("app.models")      # registers every table on Base.metadata

    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(url, poolclass=NullPool)

    async def _fresh():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_fresh())
    yield engine
    asyncio.run(engine.dispose())
