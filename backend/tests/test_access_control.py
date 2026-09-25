"""
Who may read prompt records, and who may create accounts.

Prompt records keep the original prompt verbatim - including prompts blocked
for carrying confidential data - so reading someone else's is a leak in
itself. GET /prompts/{id} used to return any user's record to any logged-in
user; the list endpoint filtered, the single-record endpoint did not.

Account creation used to be public. Anyone who could reach the API could
enrol themselves and spend the LLM quota through the platform.

Runs through the real routes and dependency chain against an on-disk SQLite
database; only the caller's identity is set per request.
"""
import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.api.v1.endpoints import auth, prompts
from app.core import database
from app.core.security import hash_password
from app.models.prompt import PolicyAction, PromptRecord
from app.models.user import User, UserRole


def _user(name, role):
    return User(id=uuid.uuid4(), email=f"{name}@acme.corp", username=name,
                hashed_password=hash_password("Password1!"), role=role,
                department="Engineering", is_active=True)


ADMIN = _user("admin", UserRole.ADMIN)
JAMES = _user("james", UserRole.EMPLOYEE)
LISA = _user("lisa", UserRole.EMPLOYEE)


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'access.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    records = {}

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        async with sessions() as s:
            s.add_all([User(**{c: getattr(u, c) for c in
                               ("id", "email", "username", "hashed_password", "role",
                                "department", "is_active")}) for u in (ADMIN, JAMES, LISA)])
            for owner, text in ((JAMES, "Look up SSN 492-83-7291 for payroll"),
                                (LISA, "Summarise the vendor agreement")):
                r = PromptRecord(user_id=owner.id, username=owner.username, prompt_text=text,
                                 policy_action=PolicyAction.BLOCK, is_blocked=True)
                s.add(r)
                await s.flush()
                records[owner.username] = str(r.id)
            await s.commit()

    asyncio.run(_setup())
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    yield records
    asyncio.run(engine.dispose())


def _client(caller):
    app = FastAPI()
    app.include_router(prompts.router)
    app.include_router(auth.router)
    if caller is not None:
        app.dependency_overrides[get_current_user] = lambda: caller
    return TestClient(app)


# ── Reading prompt records ────────────────────────────────────────────────────
def test_an_employee_can_read_their_own_record(db):
    resp = _client(JAMES).get(f"/prompts/{db['james']}")
    assert resp.status_code == 200
    assert "492-83-7291" in resp.json()["prompt_text"]


def test_an_employee_cannot_read_another_users_record(db):
    # Lisa asking for James's blocked prompt - the one holding an SSN.
    resp = _client(LISA).get(f"/prompts/{db['james']}")
    assert resp.status_code == 404
    assert "492-83-7291" not in resp.text


def test_someone_elses_record_looks_the_same_as_a_missing_one(db):
    # Anything else would confirm that a prompt exists at that ID.
    other = _client(LISA).get(f"/prompts/{db['james']}")
    missing = _client(LISA).get(f"/prompts/{uuid.uuid4()}")
    assert (other.status_code, other.json()) == (missing.status_code, missing.json())


def test_an_admin_can_read_any_record(db):
    for owner in ("james", "lisa"):
        assert _client(ADMIN).get(f"/prompts/{db[owner]}").status_code == 200


def test_the_history_list_shows_employees_only_their_own(db):
    texts = [p["prompt_text"] for p in _client(LISA).get("/prompts").json()["items"]]
    assert texts == ["Summarise the vendor agreement"]
    assert len(_client(ADMIN).get("/prompts").json()["items"]) == 2


# ── Creating accounts ─────────────────────────────────────────────────────────
NEW = {"email": "new.hire@acme.corp", "username": "newhire", "password": "Str0ngPassw0rd"}


def test_registration_requires_a_login(db):
    assert _client(None).post("/auth/register", json=NEW).status_code == 401


def test_employees_cannot_create_accounts(db):
    assert _client(JAMES).post("/auth/register", json=NEW).status_code == 403


def test_an_admin_can_create_an_employee_or_an_admin(db):
    resp = _client(ADMIN).post("/auth/register", json=NEW)
    assert resp.status_code == 201 and resp.json()["role"] == "employee"
    resp = _client(ADMIN).post("/auth/register", json={
        "email": "second.admin@acme.corp", "username": "admin2",
        "password": "Str0ngPassw0rd", "role": "admin"})
    assert resp.status_code == 201 and resp.json()["role"] == "admin"


@pytest.mark.parametrize("change, expected", [
    ({"role": "superuser"}, 422),                 # not a role that exists
    ({"password": "short"}, 422),                 # under 8 characters
    ({"username": ""}, 422),
    ({"email": "james@acme.corp"}, 400),          # email taken
    ({"username": "james"}, 400),                 # username taken - was a 500
])
def test_bad_account_requests_are_refused_with_a_reason(db, change, expected):
    resp = _client(ADMIN).post("/auth/register", json={**NEW, **change})
    assert resp.status_code == expected, resp.text
