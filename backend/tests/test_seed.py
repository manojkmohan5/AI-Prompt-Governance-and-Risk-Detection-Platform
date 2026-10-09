"""
The seeded demo history is what the pipeline produces, and seeding never
calls the LLM provider.

The history used to be written by hand. It still carried the removed
classifier's flags (TOXICITY, ML_HIGH_RISK, ML_SENSITIVE) and made-up
confidences, so the dashboards opened on detections this system cannot make.

The real detection service runs in-process here, on its own database, so the
history comes from the same checks a live request gets - and a change to what
either side sends or expects fails this file.
"""
import asyncio
import pathlib
import sys

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import database
from app.core.config import settings
from app.governance.policy_engine import POLICY_FLAGS
from app.models.prompt import PromptRecord
from app.services import detection_client, llm_service, prompt_service
from seed_data import seed as seed_module

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "detection"))
from detection import database as detection_db, encoder, entities as ent, knowledge_shield as ks
from detection.main import app as detection_app

RESPONSE_FLAGS = {"RESPONSE_DOC_LEAK", "RESPONSE_PII_LEAK", "RESPONSE_SECRET_LEAK"}


@pytest.fixture
def seeded(db_engine, tmp_path, monkeypatch):
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(seed_module, "engine", db_engine)
    monkeypatch.setattr(seed_module, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)

    # The detection service, on a database of its own, as in Docker Compose.
    detection_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'detection.db'}",
                                           poolclass=NullPool)

    async def _create():
        async with detection_engine.begin() as conn:
            await conn.run_sync(detection_db.Base.metadata.create_all)
    asyncio.run(_create())
    monkeypatch.setattr(detection_db, "AsyncSessionLocal",
                        async_sessionmaker(detection_engine, class_=AsyncSession, expire_on_commit=False))
    monkeypatch.setattr(ent, "ner_available", lambda: False)          # offline
    monkeypatch.setattr(encoder, "is_available", lambda: False)
    for name, value in (("_entity_index", {}), ("_doc_names", []), ("_faiss_index", None),
                        ("_chunk_owners", []), ("_initialized", False), ("_max_phrase_words", 1)):
        monkeypatch.setattr(ks, name, value)
    monkeypatch.setattr(detection_client, "_transport", httpx.ASGITransport(app=detection_app))

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
    asyncio.run(detection_engine.dispose())
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


def test_a_prompt_without_a_model_uses_the_configured_one(seeded):
    # The API schema and the console each pinned a model name of their own,
    # so GROQ_MODEL was never read - and when Groq retired that model, every
    # answer became an error until code changed in several places.
    records, _ = seeded
    assert {r.model_used for r in records} == {settings.GROQ_MODEL}


# ── The recorded primary category is the most severe flag ────────────────────
@pytest.mark.parametrize("flags, expected", [
    (["PII_DETECTED", "CONFIDENTIAL_DOC_LEAK"], "CONFIDENTIAL_DOC_LEAK"),
    (["SENSITIVE_DATA", "PROMPT_INJECTION"], "PROMPT_INJECTION"),
    (["KNOWLEDGE_SHIELD_SIMILAR"], "KNOWLEDGE_SHIELD_SIMILAR"),
    ([], None),
])
def test_primary_category_is_the_most_severe_flag(flags, expected):
    assert prompt_service.primary_category(flags) == expected


def test_the_documents_are_seeded_into_the_detection_service(seeded):
    assert sorted(ks._doc_names) == sorted(d["name"] for d in seed_module.CONFIDENTIAL_DOCS)
