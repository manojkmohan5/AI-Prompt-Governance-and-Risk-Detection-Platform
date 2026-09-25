"""
The LLM's answer is checked and masked before the caller sees it.

A document can leak in an answer to a prompt that contained nothing
confidential, and a model can emit credentials or personal data on its own.
Flagging alone is not enough: the flagged answer would still reach the user,
so these tests check what the caller actually receives.
"""
import pytest

from app.embeddings import knowledge_shield as ks
from app.governance import entities as ent
from app.governance import response_inspector as ri


class FakeDoc:
    def __init__(self, name, content):
        self.name = name
        self.content = content


MORTGAGE = FakeDoc(
    "Mortgage File",
    "Borrower Thomas Nakamura, SSN 205-71-6634. Loan reference LN-5583-0042, closing 2025-11-14.",
)


@pytest.fixture(autouse=True)
def _indexed(monkeypatch):
    monkeypatch.setattr(ent, "ner_available", lambda: False)   # offline
    index, longest = ks._build_entity_index([MORTGAGE])
    monkeypatch.setattr(ks, "_entity_index", index)
    monkeypatch.setattr(ks, "_max_phrase_words", longest)
    monkeypatch.setattr(ks, "_initialized", True)


def _deliver(answer):
    """What the pipeline does with an answer: inspect, then mask if flagged."""
    result = ri.inspect_response(answer)
    delivered = ri.redact_response(answer, result) if result.flags else answer
    return result, delivered


def test_a_protected_value_in_the_answer_is_masked_before_delivery():
    result, delivered = _deliver(
        "The borrower on file is under SSN 205-71-6634, and the loan is on track."
    )
    assert "RESPONSE_DOC_LEAK" in result.flags
    assert "205-71-6634" not in delivered
    assert "the loan is on track" in delivered


def test_a_reformatted_protected_value_is_still_caught():
    result, delivered = _deliver("Their SSN is 205 71 6634.")
    assert "RESPONSE_DOC_LEAK" in result.flags
    assert "205 71 6634" not in delivered


def test_credentials_the_model_emits_are_masked():
    result, delivered = _deliver("Set api_key='sk-proj-9Ha7Kd2mNvQ4rTb8XwZc3Lp6' and retry.")
    assert result.secrets_detected
    assert "sk-proj-9Ha7Kd2mNvQ4rTb8XwZc3Lp6" not in delivered
    assert "and retry" in delivered


def test_personal_data_not_from_any_document_is_masked_too():
    # PII the model produces is a leak whether or not a document contains it.
    result, delivered = _deliver("You can reach her at jane.doe@example.com.")
    assert "RESPONSE_PII_LEAK" in result.flags
    assert "jane.doe@example.com" not in delivered


def test_a_clean_answer_is_delivered_unchanged():
    answer = "Containers package an app with its dependencies so it runs the same everywhere."
    result, delivered = _deliver(answer)
    assert result.flags == []
    assert delivered == answer
