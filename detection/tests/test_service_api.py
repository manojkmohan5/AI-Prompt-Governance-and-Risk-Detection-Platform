"""
The detection service's HTTP API: what the backend sends and gets back.

The backend acts on these answers without looking at the text itself - it
forwards redacted_text to the LLM on a REDACT policy and delivers the checked
answer's redacted_text - so the masking has to be right here, at the boundary.
"""
import pytest
from fastapi.testclient import TestClient

from detection import config
from detection import entities as ent
from detection import knowledge_shield as ks
from detection.main import app


class FakeDoc:
    def __init__(self, name, content):
        self.name = name
        self.content = content


PAYROLL = FakeDoc("Payroll 2025", "Employee Dana Reyes, SSN 492-83-7291, salary $185,000.")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(ent, "ner_available", lambda: False)    # offline
    index, longest = ks._build_entity_index([PAYROLL])
    monkeypatch.setattr(ks, "_entity_index", index)
    monkeypatch.setattr(ks, "_max_phrase_words", longest)
    monkeypatch.setattr(ks, "_initialized", True)
    monkeypatch.setattr(ks, "_faiss_index", None)                # no similarity model
    monkeypatch.setattr(config.settings, "DETECTION_TOKEN", "")
    return TestClient(app)   # not entered: no lifespan, so no database is opened


def test_a_prompt_quoting_a_protected_value_is_a_confirmed_leak(client):
    check = client.post("/v1/check/prompt", json={"text": "Is SSN 492-83-7291 still on payroll?"}).json()
    assert "CONFIDENTIAL_DOC_LEAK" in check["flags"]
    assert check["risk_level"] == "CRITICAL"
    assert check["documents"] == ["Payroll 2025"]
    assert check["doc_matches"] == [{"type": "SSN", "value": "492-83-7291", "documents": ["Payroll 2025"]}]


def test_redacted_text_masks_secrets_and_document_values_but_keeps_the_question(client):
    check = client.post("/v1/check/prompt", json={
        "text": "Why does api_key='sk-proj-9Ha7Kd2mNvQ4rTb8XwZc3Lp6' fail for SSN 492-83-7291?"}).json()
    sent = check["redacted_text"]
    assert "sk-proj-9Ha7Kd2mNvQ4rTb8XwZc3Lp6" not in sent
    assert "492-83-7291" not in sent
    assert sent.startswith("Why does api_key=")


def test_a_clean_prompt_scores_zero_and_is_unchanged(client):
    text = "In one sentence, what is a reverse proxy?"
    check = client.post("/v1/check/prompt", json={"text": text}).json()
    assert (check["risk_score"], check["risk_level"], check["flags"]) == (0, "LOW", [])
    assert check["redacted_text"] == text


def test_an_answer_naming_a_protected_value_is_masked(client):
    check = client.post("/v1/check/response", json={"text": "Their SSN is 492-83-7291, all fine."}).json()
    assert "RESPONSE_DOC_LEAK" in check["flags"]
    assert "492-83-7291" not in check["redacted_text"]
    assert "all fine" in check["redacted_text"]


def test_a_clean_answer_is_returned_unchanged(client):
    answer = "A reverse proxy forwards client requests to backend servers."
    assert client.post("/v1/check/response", json={"text": answer}).json() == {
        "flags": [], "redacted_text": answer}


# ── Service token ─────────────────────────────────────────────────────────────
def test_with_a_token_set_requests_without_it_are_refused(client, monkeypatch):
    monkeypatch.setattr(config.settings, "DETECTION_TOKEN", "s3cret-shared-token")
    body = {"json": {"text": "hello"}}
    assert client.post("/v1/check/prompt", **body).status_code == 401
    assert client.post("/v1/check/prompt", headers={"Authorization": "Bearer wrong"}, **body).status_code == 401
    assert client.post("/v1/check/prompt", headers={"Authorization": "Bearer s3cret-shared-token"},
                       **body).status_code == 200


def test_every_route_but_health_requires_the_token(client, monkeypatch):
    monkeypatch.setattr(config.settings, "DETECTION_TOKEN", "s3cret-shared-token")
    for route in app.routes:
        for method in getattr(route, "methods", ()):
            if route.path == "/health":
                continue
            path = route.path.replace("{doc_id}", "00000000-0000-0000-0000-000000000001")
            assert client.request(method, path).status_code == 401, (method, route.path)
    assert client.get("/health").status_code == 200
