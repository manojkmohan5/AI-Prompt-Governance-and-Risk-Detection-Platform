"""
A document is protected the moment it is added, and unprotected when removed.

Found in the live end-to-end run: the add, upload and delete handlers rebuilt
the index before their transaction committed, and the rebuild reads through a
separate connection - so it saw the document set as it was BEFORE the change.
A freshly uploaded document stayed unprotected until some later upload, delete
or restart happened to rebuild again; a deleted one stayed protected.

Uses a real database (an on-disk SQLite file, or Postgres in CI) and the real
get_db. An in-memory database on a shared connection would hide the bug: the
rebuild would see the uncommitted row through the same connection.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from detection import database, encoder
from detection import entities as ent
from detection import knowledge_shield as ks
from detection.main import router

DOC = b"Contractor agreement. Contract number CT-7731-QX, day rate $1,850."
PROMPT = "What is the status of contract CT-7731-QX?"


@pytest.fixture
def client(db_engine, monkeypatch):
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    # Both the request's get_db and the index rebuild open sessions from here.
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(ent, "ner_available", lambda: False)     # offline
    monkeypatch.setattr(encoder, "is_available", lambda: False)  # no embeddings
    for name, value in (("_entity_index", {}), ("_doc_names", []), ("_faiss_index", None),
                        ("_chunk_owners", []), ("_initialized", False), ("_max_phrase_words", 1)):
        monkeypatch.setattr(ks, name, value)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_an_uploaded_document_is_protected_immediately(client):
    assert ks.match_entities(PROMPT) == []
    resp = client.post("/v1/documents/upload",
                       files={"file": ("contractor.txt", DOC, "text/plain")})
    assert resp.status_code == 201, resp.text
    assert [m.value for m in ks.match_entities(PROMPT)] == ["CT-7731-QX"]


def test_a_pasted_document_is_protected_immediately(client):
    resp = client.post("/v1/documents",
                       json={"name": "Contractor", "content": DOC.decode()})
    assert resp.status_code == 201, resp.text
    assert [m.value for m in ks.match_entities(PROMPT)] == ["CT-7731-QX"]


def test_a_deleted_document_stops_being_protected_immediately(client):
    doc_id = client.post("/v1/documents",
                         json={"name": "Contractor", "content": DOC.decode()}).json()["id"]
    assert ks.match_entities(PROMPT)
    assert client.delete(f"/v1/documents/{doc_id}").status_code == 204
    assert ks.match_entities(PROMPT) == []


def test_a_batch_is_protected_immediately(client):
    resp = client.post("/v1/documents/batch", json=[
        {"name": "Contractor", "content": DOC.decode()},
        {"name": "Vendor", "content": "Vendor agreement, purchase order PO-5521-ZK."},
    ])
    assert resp.status_code == 201, resp.text
    assert [d["name"] for d in resp.json()] == ["Contractor", "Vendor"]
    assert [m.value for m in ks.match_entities(PROMPT)] == ["CT-7731-QX"]
    assert [m.value for m in ks.match_entities("Chase PO-5521-ZK")] == ["PO-5521-ZK"]
