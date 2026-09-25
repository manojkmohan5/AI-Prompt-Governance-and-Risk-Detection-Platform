"""
Only admins may add to, read, or remove the protected document set.

Employees are exactly the people the Knowledge Shield protects documents
*from*: an employee who could list the protected set would learn what is
protected, and one who could delete a document would switch its protection
off. Every route on the router is checked, not just upload, because the guard
is per-route and a new route can be added without it.

Runs through FastAPI's real dependency chain (require_admin -> get_current_user)
with only the user lookup and database replaced, so a route that forgets the
guard fails here.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints import knowledge_shield as ks_routes
from app.core.database import get_db
from app.models.user import User, UserRole

DOC_ID = str(uuid.uuid4())

# Every route on the router. If a route is added, add it here too — the last
# test fails until you do, so an unguarded route cannot slip in unnoticed.
ROUTES = [
    ("get", "/knowledge-shield/documents", {}),
    ("post", "/knowledge-shield/documents", {"json": {"name": "x", "content": "y"}}),
    ("post", "/knowledge-shield/documents/upload",
     {"files": {"file": ("notes.txt", b"Contract number NW-2024-8871 is active.", "text/plain")}}),
    ("delete", f"/knowledge-shield/documents/{DOC_ID}", {}),
    ("get", "/knowledge-shield/status", {}),
]


@pytest.fixture(autouse=True)
def _no_index_rebuild(monkeypatch):
    """
    Adding or removing a document rebuilds the index from the real database.
    Stubbed for every test, not just the admin one: if a guard ever regresses,
    an employee request reaches the handler, and the failing test must not
    open the app's real database on its way to failing.
    """
    async def _noop():
        pass
    monkeypatch.setattr(ks_routes.knowledge_shield, "rebuild", _noop)


def _user(role):
    return User(email=f"{role.value}@acme.corp", username=role.value, hashed_password="x",
                role=role, department="Engineering", is_active=True)


class _FakeDB:
    """Just enough session for the upload handler to reach its response."""

    def add(self, obj):
        obj.id = obj.id or uuid.uuid4()
        obj.created_at = obj.created_at or datetime.now(timezone.utc)

    async def flush(self):
        pass


def _client(user):
    app = FastAPI()
    app.include_router(ks_routes.router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    return TestClient(app)


@pytest.mark.parametrize("method, path, kwargs", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_employees_are_refused_on_every_route(method, path, kwargs):
    resp = getattr(_client(_user(UserRole.EMPLOYEE)), method)(path, **kwargs)
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("method, path, kwargs", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_requests_without_a_token_are_refused(method, path, kwargs):
    resp = getattr(_client(None), method)(path, **kwargs)
    assert resp.status_code == 401, resp.text


def test_an_admin_can_upload():
    # Proves the 403s above come from the role check, not from a route that is
    # broken for everyone.
    _, path, kwargs = ROUTES[2]
    resp = _client(_user(UserRole.ADMIN)).post(path, **kwargs)
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "notes"


def test_the_route_list_above_covers_the_whole_router():
    declared = {(m.upper(), p.replace(DOC_ID, "{doc_id}")) for m, p, _ in ROUTES}
    actual = {(method, route.path)
              for route in ks_routes.router.routes for method in route.methods}
    assert actual == declared, f"unchecked routes: {actual - declared}"
