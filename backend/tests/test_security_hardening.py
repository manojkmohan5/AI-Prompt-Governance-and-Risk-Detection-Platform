"""
Defaults that were unsafe out of the box.

Each of these shipped enabled: stack traces returned to callers, tokens signed
with a key published in the repository, a login response that revealed which
emails have accounts, and uploads read whole into memory before the size check.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints import auth
from app.api.v1.endpoints import knowledge_shield as ks_routes
from app.core import config
from app.core.database import get_db
from app.models.user import User, UserRole
from app.services import document_text


# ── Stack traces ──────────────────────────────────────────────────────────────
def test_debug_mode_is_off_unless_asked_for():
    import main
    assert main.app.debug is False
    assert config.settings.DEBUG is False


# ── Signing key ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("published", [
    "change-this-to-a-long-random-secret-key",                   # config.py default
    "change-this-to-a-long-random-secret-key-in-production",     # .env.example, compose
])
def test_a_published_placeholder_key_is_never_used(published):
    s = config.Settings(SECRET_KEY=published, _env_file=None)
    config.ensure_secret_key(s)
    assert s.SECRET_KEY != published
    assert len(s.SECRET_KEY) >= 64


def test_each_process_gets_a_different_random_key():
    keys = set()
    for _ in range(3):
        s = config.Settings(SECRET_KEY="change-this", _env_file=None)
        config.ensure_secret_key(s)
        keys.add(s.SECRET_KEY)
    assert len(keys) == 3


def test_a_key_someone_chose_is_left_alone():
    s = config.Settings(SECRET_KEY="a-real-deployment-secret-9f3b1c", _env_file=None)
    config.ensure_secret_key(s)
    assert s.SECRET_KEY == "a-real-deployment-secret-9f3b1c"


def test_the_running_app_is_not_signing_with_a_placeholder():
    assert not config.settings.SECRET_KEY.startswith("change-this")


# ── Login timing ──────────────────────────────────────────────────────────────
class _NoUsers:
    async def execute(self, *_a, **_k):
        class R:
            def scalar_one_or_none(self):
                return None
        return R()


def test_an_unknown_email_costs_the_same_bcrypt_check_as_a_wrong_password(monkeypatch):
    checks = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda p, h: checks.append(h) or real(p, h))

    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_db] = lambda: _NoUsers()
    resp = TestClient(app).post("/auth/login", json={"email": "nobody@acme.corp", "password": "guess"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"        # same message as a wrong password
    assert checks == [auth._UNKNOWN_ACCOUNT_HASH]                 # and the same work


# ── Upload size ───────────────────────────────────────────────────────────────
class _SpyFile:
    """Records how many bytes the handler asked to read."""

    def __init__(self):
        self.requested = None
        self.filename = "huge.txt"
        self.content_type = "text/plain"

    async def read(self, size=-1):
        self.requested = size
        return b"x" * (document_text.MAX_UPLOAD_BYTES + 1)


def test_an_oversized_upload_is_refused_after_reading_only_one_byte_past_the_limit():
    import asyncio
    from fastapi import HTTPException

    admin = User(email="a@acme.corp", username="a", hashed_password="x",
                 role=UserRole.ADMIN, is_active=True)
    spy = _SpyFile()
    with pytest.raises(HTTPException) as e:
        asyncio.run(ks_routes.upload_document(file=spy, name=None, category="general",
                                              db=None, _=admin))
    assert e.value.status_code == 413
    assert spy.requested == document_text.MAX_UPLOAD_BYTES + 1   # never the whole file
