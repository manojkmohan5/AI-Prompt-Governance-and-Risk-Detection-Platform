"""
When the detection service cannot answer, nothing unchecked gets through.

Splitting detection into its own service added a failure the monolith did not
have: the API up while the checks are down. Forwarding prompts unchecked then
would make every outage a leak, so the platform fails closed - the prompt is
refused with a 503 and never reaches the LLM, and an answer that cannot be
checked is never delivered. Everything that needs no check keeps working.

Runs the real app and pipeline; only the caller, the LLM and the detection
service's network replies are replaced.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import main
from app.api.deps import get_current_user
from app.core import database
from app.models.prompt import PromptRecord
from app.models.user import User, UserRole
from app.services import detection_client, llm_service

JAMES = User(id=uuid.uuid4(), email="james@acme.corp", username="james", hashed_password="x",
             role=UserRole.EMPLOYEE, department="Engineering", is_active=True,
             created_at=datetime.now(timezone.utc))
CLEAN = {"risk_score": 0, "risk_level": "LOW", "flags": [], "entities": [], "injection_spans": [],
         "doc_matches": [], "documents": [], "similarity": None, "redacted_text": "Summarise our Q3 goals"}


@pytest.fixture
def env(db_engine, monkeypatch):
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)

    async def _add_user():          # records reference it, and Postgres checks
        async with sessions() as db:
            db.add(User(**{c: getattr(JAMES, c) for c in
                           ("id", "email", "username", "hashed_password", "role", "department",
                            "is_active", "created_at")}))
            await db.commit()
    asyncio.run(_add_user())
    llm_calls = []

    async def _llm(prompt, model=None):
        llm_calls.append(prompt)
        return "The goals are in the deck.", 7
    monkeypatch.setattr(llm_service, "complete", _llm)
    main.app.dependency_overrides[get_current_user] = lambda: JAMES
    # Not entered as a context manager: no lifespan, so the app's own database is never opened.
    yield TestClient(main.app), llm_calls, sessions
    main.app.dependency_overrides.clear()


def _detection(monkeypatch, handler):
    monkeypatch.setattr(detection_client, "_transport", httpx.MockTransport(handler))


def _records(sessions):
    async def _count():
        async with sessions() as db:
            return (await db.execute(select(func.count()).select_from(PromptRecord))).scalar()
    return asyncio.run(_count())


def _submit(client):
    return client.post("/api/v1/prompts", json={"prompt": "Summarise our Q3 goals"})


def _down(request):
    raise httpx.ConnectError("connection refused")


def _slow(request):
    raise httpx.ReadTimeout("timed out")


@pytest.mark.parametrize("handler", [
    _down,
    lambda request: httpx.Response(500),
    _slow,
    # A token mismatch between the services is this platform's fault. Passed
    # through as a 401 it would sign the employee out.
    lambda request: httpx.Response(401, json={"detail": "Invalid service token"}),
], ids=["unreachable", "server error", "timeout", "token mismatch"])
def test_a_prompt_that_cannot_be_checked_is_refused_and_never_sent(env, monkeypatch, handler):
    client, llm_calls, sessions = env
    _detection(monkeypatch, handler)
    resp = _submit(client)
    assert resp.status_code == 503, resp.text
    assert "detection service is unavailable" in resp.json()["detail"]
    assert llm_calls == []
    assert _records(sessions) == 0


def test_an_answer_that_cannot_be_checked_is_not_delivered(env, monkeypatch):
    client, llm_calls, sessions = env

    def handler(request):
        if request.url.path == "/v1/check/prompt":
            return httpx.Response(200, json=CLEAN)
        raise httpx.ConnectError("went down mid-request")
    _detection(monkeypatch, handler)

    resp = _submit(client)
    assert resp.status_code == 503, resp.text
    assert len(llm_calls) == 1                         # the prompt was checked and sent...
    assert "The goals are in the deck." not in resp.text   # ...but the answer is withheld
    assert _records(sessions) == 0


def test_with_detection_up_the_checked_answer_is_what_is_delivered(env, monkeypatch):
    client, llm_calls, _ = env

    def handler(request):
        if request.url.path == "/v1/check/prompt":
            return httpx.Response(200, json=CLEAN)
        return httpx.Response(200, json={"flags": ["RESPONSE_PII_LEAK"], "redacted_text": "[MASKED]"})
    _detection(monkeypatch, handler)

    resp = _submit(client)
    assert resp.status_code == 201, resp.text
    assert resp.json()["response_text"] == "[MASKED]"
    assert "RESPONSE_PII_LEAK" in resp.json()["flags"]


def test_what_needs_no_check_keeps_working_while_detection_is_down(env, monkeypatch):
    client, _, _ = env
    _detection(monkeypatch, _down)
    assert client.get("/api/v1/prompts").status_code == 200       # history
    assert client.get("/api/v1/auth/me").status_code == 200       # the session
    assert client.get("/health").status_code == 200
