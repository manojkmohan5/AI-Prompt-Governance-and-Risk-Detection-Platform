"""
Policy rules are validated before they can be saved, and a rule that cannot
be loaded can no longer take the platform down.

Found while auditing the API: the create endpoint stored any string. A rule
saved with a typo ("BLCOK") could not be loaded back, and the policy engine
loads every active rule on every prompt - so one bad rule failed every prompt,
and GET /policies failed too, leaving no way to remove it from the UI.
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401  (registers every table on Base)
from app.api.deps import get_current_user
from app.api.v1.endpoints import policies
from app.core import database
from app.governance import policy_engine
from app.models.policy_rule import ActionType, ConditionType, PolicyRule
from app.models.user import User, UserRole
from main import _remove_unloadable_policy_rules

ADMIN = User(email="admin@acme.corp", username="admin", hashed_password="x",
             role=UserRole.ADMIN, is_active=True)
VALID = {"name": "Block leaks", "condition_type": "flag_contains",
         "condition_value": "CONFIDENTIAL_DOC_LEAK", "action": "BLOCK", "priority": 90}


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rules.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
    asyncio.run(_create())
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)

    app = FastAPI()
    app.include_router(policies.router)
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    # Server errors as responses, not exceptions: one test asserts the outage's 500.
    yield TestClient(app, raise_server_exceptions=False), engine, sessions
    asyncio.run(engine.dispose())


# ── The API refuses rules that could not work ─────────────────────────────────
def test_the_settings_page_payload_is_accepted(env):
    client, _, _ = env
    resp = client.post("/policies", json=VALID)
    assert resp.status_code == 201, resp.text
    assert (resp.json()["condition_type"], resp.json()["action"]) == ("flag_contains", "BLOCK")


@pytest.mark.parametrize("change", [
    {"action": "BLCOK"},                                             # the typo that took the app down
    {"condition_type": "nonsense"},
    {"condition_value": "TOXICITY"},                                 # raised by nothing now
    {"condition_value": "RESPONSE_DOC_LEAK"},                        # raised after the decision
    {"condition_type": "risk_score_above", "condition_value": "eighty"},
    {"condition_type": "risk_score_above", "condition_value": "150"},
    {"condition_type": "department_is", "condition_value": "  "},
    {"name": ""},
    {"priority": -1},
])
def test_a_rule_that_could_not_work_is_refused(env, change):
    client, _, _ = env
    resp = client.post("/policies", json={**VALID, **change})
    assert resp.status_code == 422, resp.text
    assert client.get("/policies").status_code == 200   # and nothing broke


def test_the_refusal_says_what_to_use_instead(env):
    client, _, _ = env
    detail = client.post("/policies", json={**VALID, "condition_value": "TOXICITY"}).json()["detail"]
    assert "CONFIDENTIAL_DOC_LEAK" in str(detail)


def test_an_always_rule_needs_no_value(env):
    client, _, _ = env
    resp = client.post("/policies", json={**VALID, "condition_type": "always", "condition_value": ""})
    assert resp.status_code == 201, resp.text


# ── An unloadable row already in the database is removed at startup ──────────
def test_startup_removes_a_rule_that_cannot_be_loaded_and_keeps_the_rest(env):
    client, engine, sessions = env

    async def _run():
        async with sessions() as db:
            db.add(PolicyRule(name="good", condition_type=ConditionType.FLAG_CONTAINS,
                              condition_value="PII_DETECTED", action=ActionType.REDACT, priority=70))
            await db.commit()
        async with engine.begin() as conn:   # saved before validation existed
            await conn.execute(text(
                "INSERT INTO policy_rules (id, name, condition_type, condition_value, action, "
                "priority, is_active, created_at) VALUES ('00000000000000000000000000000001', "
                "'typo', 'FLAG_CONTAINS', 'PII_DETECTED', 'BLCOK', 1, 1, '2026-01-01 00:00:00')"))

    asyncio.run(_run())
    assert client.get("/policies").status_code == 500          # the outage, reproduced

    async def _repair_and_evaluate():
        async with engine.begin() as conn:
            await _remove_unloadable_policy_rules(conn)
        async with sessions() as db:
            names = [r.name for r in (await db.execute(select(PolicyRule))).scalars()]
            action = await policy_engine.determine_action(10, ["PII_DETECTED"], None, db)
        return names, action

    names, action = asyncio.run(_repair_and_evaluate())
    assert names == ["good"]
    assert action == "REDACT"                                  # prompts are processed again
    assert client.get("/policies").status_code == 200
