"""
A document is protected the moment it is added, and unprotected when removed.

Found in the live end-to-end run: the add, upload and delete handlers rebuilt
the index before their transaction committed, and the rebuild reads through a
separate connection - so it saw the document set as it was BEFORE the change.
A freshly uploaded document stayed unprotected until some later upload, delete
or restart happened to rebuild again; a deleted one stayed protected.

Uses a real on-disk SQLite database and the real get_db. An in-memory database
on a shared connection would hide the bug: the rebuild would see the
uncommitted row through the same connection.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.api.v1.endpoints import knowledge_shield as ks_routes
from app.core import database
from app.embeddings import encoder
from app.embeddings import knowledge_shield as ks
from app.governance import entities as ent
from app.models.user import User, UserRole

ADMIN = User(email="admin@acme.corp", username="admin", hashed_password="x",
             role=UserRole.ADMIN, department="Security", is_active=True)
DOC = b"Contractor agreement. Contract number CT-7731-QX, day rate $1,850."
PROMPT = "What is the status of contract CT-7731-QX?"


@pytest.fixture
def client(tmp_path, monkeypatch):
    import asyncio

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'shield.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
    asyncio.run(_create())

    # Both the request's get_db and the index rebuild open sessions from here.
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(ent, "ner_available", lambda: False)     # offline
    monkeypatch.setattr(encoder, "is_available", lambda: False)  # no embeddings
    for name, value in (("_entity_index", {}), ("_doc_names", []), ("_faiss_index", None),
                        ("_chunk_owners", []), ("_initialized", False), ("_max_phrase_words", 1)):
        monkeypatch.setattr(ks, name, value)

    app = FastAPI()
    app.include_router(ks_routes.router)
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    yield TestClient(app)
    asyncio.run(engine.dispose())


def test_an_uploaded_document_is_protected_immediately(client):
    assert ks.match_entities(PROMPT) == []
    resp = client.post("/knowledge-shield/documents/upload",
                       files={"file": ("contractor.txt", DOC, "text/plain")})
    assert resp.status_code == 201, resp.text
    assert [m.value for m in ks.match_entities(PROMPT)] == ["CT-7731-QX"]


def test_a_pasted_document_is_protected_immediately(client):
    resp = client.post("/knowledge-shield/documents",
                       json={"name": "Contractor", "content": DOC.decode()})
    assert resp.status_code == 201, resp.text
    assert [m.value for m in ks.match_entities(PROMPT)] == ["CT-7731-QX"]


def test_a_deleted_document_stops_being_protected_immediately(client):
    doc_id = client.post("/knowledge-shield/documents",
                         json={"name": "Contractor", "content": DOC.decode()}).json()["id"]
    assert ks.match_entities(PROMPT)
    assert client.delete(f"/knowledge-shield/documents/{doc_id}").status_code == 204
    assert ks.match_entities(PROMPT) == []
