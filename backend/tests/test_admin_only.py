"""
Only admins may add to, read, or remove the protected document set.

Employees are exactly the people the Knowledge Shield protects documents
*from*: an employee who could list the protected set would learn what is
protected, and one who could delete a document would switch its protection
off. Every route on the router is checked, not just upload, because the guard
is per-route and a new route can be added without it.

The documents live in the detection service, which never sees an end user's
token: these routes are the only guard. Runs through FastAPI's real dependency
chain (require_admin -> get_current_user) with only the user lookup, the
database and the detection service replaced, so a route that forgets the guard
fails here - and a refused request must never reach the detection service.
"""
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints import knowledge_shield as ks_routes
from app.core.database import get_db
from app.models.user import User, UserRole
from app.services import detection_client

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
def forwarded(monkeypatch):
    """Stands in for the detection service and records what reached it."""
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/v1/status":
            return httpx.Response(200, json={"documents": 0})
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(201, json={"id": str(uuid.uuid4()), "name": "notes", "category": "general",
                                         "created_at": "2026-01-01T00:00:00Z"})

    monkeypatch.setattr(detection_client, "_transport", httpx.MockTransport(handler))
    return requests


def _user(role):
    return User(email=f"{role.value}@acme.corp", username=role.value, hashed_password="x",
                role=role, department="Engineering", is_active=True)


def _client(user):
    app = FastAPI()
    app.include_router(ks_routes.router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None   # the guard must refuse before any lookup
    return TestClient(app)


@pytest.mark.parametrize("method, path, kwargs", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_employees_are_refused_on_every_route(method, path, kwargs, forwarded):
    resp = getattr(_client(_user(UserRole.EMPLOYEE)), method)(path, **kwargs)
    assert resp.status_code == 403, resp.text
    assert forwarded == []


@pytest.mark.parametrize("method, path, kwargs", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_requests_without_a_token_are_refused(method, path, kwargs, forwarded):
    resp = getattr(_client(None), method)(path, **kwargs)
    assert resp.status_code == 401, resp.text
    assert forwarded == []


def test_an_admin_can_upload(forwarded):
    # Proves the 403s above come from the role check, not from a route that is
    # broken for everyone.
    _, path, kwargs = ROUTES[2]
    resp = _client(_user(UserRole.ADMIN)).post(path, **kwargs)
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "notes"
    [sent] = forwarded
    assert sent.url.path == "/v1/documents/upload"
    assert b"Contract number NW-2024-8871 is active." in sent.content    # the file itself


def test_the_route_list_above_covers_the_whole_router():
    declared = {(m.upper(), p.replace(DOC_ID, "{doc_id}")) for m, p, _ in ROUTES}
    actual = {(method, route.path)
              for route in ks_routes.router.routes for method in route.methods}
    assert actual == declared, f"unchecked routes: {actual - declared}"
