"""
The seeded demo history is what the pipeline produces, and seeding never
calls the LLM provider.

The history used to be written by hand. It still carried the removed
classifier's flags (TOXICITY, ML_HIGH_RISK, ML_SENSITIVE) and made-up
confidences, so the dashboards opened on detections this system cannot make.
"""
import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core import database
from app.embeddings import encoder
from app.embeddings import knowledge_shield as ks
from app.governance import entities as ent
from app.governance.policy_engine import POLICY_FLAGS
from app.models.prompt import PromptRecord
from app.services import llm_service, prompt_service
from seed_data import seed as seed_module

RESPONSE_FLAGS = {"RESPONSE_DOC_LEAK", "RESPONSE_PII_LEAK", "RESPONSE_SECRET_LEAK"}


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)     # the shield's own reads
    monkeypatch.setattr(ent, "ner_available", lambda: False)          # offline
    monkeypatch.setattr(encoder, "is_available", lambda: False)
    for name, value in (("_entity_index", {}), ("_doc_names", []), ("_faiss_index", None),
                        ("_chunk_owners", []), ("_initialized", False), ("_max_phrase_words", 1)):
        monkeypatch.setattr(ks, name, value)

    provider_calls = []

    async def _provider(prompt, model=None):          # stands in for the real Groq call
        provider_calls.append(prompt)
        return "from the provider", 0

    monkeypatch.setattr(llm_service, "complete", _provider)

    asyncio.run(seed_module.seed())

    async def _records():
        async with sessions() as db:
            return list((await db.execute(select(PromptRecord))).scalars())

    records = asyncio.run(_records())
    asyncio.run(engine.dispose())
    return records, provider_calls


def test_every_sample_prompt_is_recorded(seeded):
    records, _ = seeded
    assert len(records) == len(seed_module.SAMPLE_PROMPTS)


def test_the_history_only_contains_flags_the_platform_raises(seeded):
    records, _ = seeded
    raised = {f for r in records for f in (r.flags or [])}
    assert raised <= POLICY_FLAGS | RESPONSE_FLAGS, raised - (POLICY_FLAGS | RESPONSE_FLAGS)


def test_no_record_claims_a_model_confidence(seeded):
    records, _ = seeded
    assert all(r.ml_confidence is None for r in records)


def test_blocked_prompts_have_no_answer_and_allowed_ones_do(seeded):
    records, _ = seeded
    assert all(r.response_text is None for r in records if r.is_blocked)
    assert all(r.response_text for r in records if not r.is_blocked)


def test_the_history_includes_blocks_and_redactions(seeded):
    # A demo history of nothing but ALLOW would show off nothing.
    records, _ = seeded
    actions = {r.policy_action.value if hasattr(r.policy_action, "value") else r.policy_action
               for r in records}
    assert {"ALLOW", "BLOCK", "REDACT"} <= actions


def test_seeding_never_calls_the_llm_provider(seeded):
    _, provider_calls = seeded
    assert provider_calls == []
    assert llm_service.complete.__name__ == "_provider"   # and the swap was undone


# ── The recorded primary category is the most severe flag ────────────────────
@pytest.mark.parametrize("flags, expected", [
    (["PII_DETECTED", "CONFIDENTIAL_DOC_LEAK"], "CONFIDENTIAL_DOC_LEAK"),
    (["SENSITIVE_DATA", "PROMPT_INJECTION"], "PROMPT_INJECTION"),
    (["KNOWLEDGE_SHIELD_SIMILAR"], "KNOWLEDGE_SHIELD_SIMILAR"),
    ([], None),
])
def test_primary_category_is_the_most_severe_flag(flags, expected):
    assert prompt_service.primary_category(flags) == expected
