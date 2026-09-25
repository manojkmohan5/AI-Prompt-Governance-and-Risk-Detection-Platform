"""
Tests that run the real NER and embedding models.

Everything else in this suite stubs the models off so it can run offline. That
is exactly how the NER aggregation bug shipped: the model returned "Priya
Raghavan" as the fragments "P" + "##riya Raghavan", the index stored
"riya raghavan", and no stubbed test could see it. These tests exist so that
class of failure — the model loads fine but its output is unusable — fails
loudly instead.

Skipped when the ML packages are not installed (CI's plain Python job). CI's
Docker job runs this file inside the built image, against the model baked into
it, so the check covers what actually ships.
"""
import asyncio

import pytest

pytest.importorskip("transformers", reason="ML requirements not installed")

from app.embeddings import knowledge_shield as ks  # noqa: E402
from app.governance import entities as ent  # noqa: E402


class FakeDoc:
    def __init__(self, name, content):
        self.name = name
        self.content = content


# Names chosen because they tokenise into several word pieces — the case the
# "simple" aggregation strategy broke. Common names like "Dana Reyes" survived
# it and would have hidden the bug.
CLIENT_RECORD = FakeDoc(
    "Client Master Record",
    "Primary contact: Priya Raghavan, VP Operations at Northwind Retail Group. "
    "Logistics are handled by Kestrel Logistics under contract NW-2024-8871. "
    "Acquisition talks with Halcyon Media Partners are confidential.",
)


@pytest.fixture(scope="module")
def ner():
    if not ent.ner_available():
        pytest.fail(
            "transformers is installed but the NER model did not load. The shield "
            "would silently fall back to regex-only coverage and stop protecting names."
        )


def test_multi_piece_names_come_back_whole(ner):
    names = {e.norm for e in ent.extract_names(CLIENT_RECORD.content)}
    for expected in ("priya raghavan", "northwind retail group",
                     "kestrel logistics", "halcyon media partners"):
        assert expected in names, f"{expected!r} missing from {sorted(names)}"


def test_no_word_piece_fragments_reach_the_index(ner):
    # Fragments are the symptom of the aggregation bug, and each one is also a
    # false-positive risk: "north" indexed as a company matched ordinary prompts.
    names = {e.norm for e in ent.extract_names(CLIENT_RECORD.content)}
    for fragment in ("riya raghavan", "wind retail group", "rel logistics",
                     "on media partners", "north"):
        assert fragment not in names, f"fragment {fragment!r} was indexed"


def test_name_from_a_document_is_caught_in_a_prompt(ner, monkeypatch):
    index, longest = ks._build_entity_index([CLIENT_RECORD])
    monkeypatch.setattr(ks, "_entity_index", index)
    monkeypatch.setattr(ks, "_max_phrase_words", longest)
    monkeypatch.setattr(ks, "_initialized", True)

    matches = ks.match_entities("What is Priya Raghavan's salary?")
    assert [(m.type, m.value) for m in matches] == [("PERSON", "Priya Raghavan")]
    assert ks.confirm_leak(matches)


def test_lowercase_prompt_still_matches(ner, monkeypatch):
    # NER itself misses lowercase names entirely, which is why it runs on
    # documents and not prompts. The index match is case-insensitive.
    index, longest = ks._build_entity_index([CLIENT_RECORD])
    monkeypatch.setattr(ks, "_entity_index", index)
    monkeypatch.setattr(ks, "_max_phrase_words", longest)
    monkeypatch.setattr(ks, "_initialized", True)

    assert ks.confirm_leak(ks.match_entities("what is priya raghavan's salary"))


# ── Similarity (chunked FAISS) ────────────────────────────────────────────────
def test_similarity_finds_the_right_document(monkeypatch):
    pytest.importorskip("sentence_transformers", reason="embedding model not installed")
    pytest.importorskip("faiss", reason="faiss not installed")
    from app.embeddings import encoder

    if not encoder.is_available():
        pytest.fail("sentence-transformers is installed but the encoder did not load.")

    docs = [
        FakeDoc("Q3 Results", "Q3 revenue was $42.7M, up 31% year on year. "
                              "Gross margin 74.2%. Do not disclose before the earnings call."),
        FakeDoc("Holiday Rota", "The office is closed on public holidays. "
                                "Support staff rotate weekend cover each month."),
    ]
    chunks, owners = ks._chunk_documents(docs)
    monkeypatch.setattr(ks, "_faiss_index", ks._build_faiss_index(encoder.encode(chunks)))
    monkeypatch.setattr(ks, "_chunk_owners", owners)
    monkeypatch.setattr(ks, "_initialized", True)

    score, doc = asyncio.run(ks.check_similarity("Write a LinkedIn post about our Q3 revenue growth"))
    assert doc == "Q3 Results"
    assert score is not None and 0.0 < score <= 1.0
