"""
Knowledge Shield — stops confidential document content reaching the LLM.

Two independent signals, deliberately weighted very differently:

  1. Entity match (primary, exact).  Every uploaded document is indexed into
     its constituent entities — identifiers by regex, names by NER. A prompt is
     checked against that index. A hit means a value that literally exists in a
     protected document was typed into the prompt. This is evidence, not a
     guess, so it is what actually drives blocking and redaction.

  2. Cosine similarity (secondary, advisory).  FAISS nearest-neighbour over
     document embeddings. This only ever says "this prompt is about the same
     subject as a protected document" — which is true of plenty of harmless
     prompts — so on its own it warns and never blocks.

Splitting them this way is the point: similarity alone produced false alarms on
unrelated prompts that merely shared a topic, and it missed calmly-worded
prompts that quoted a document verbatim. The entity index catches the second
case exactly, and the first case no longer stops anyone's work.

All heavy imports are lazy so the server starts even without ML packages.
"""
import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.embeddings import encoder
from app.governance import entities as ent

# ── Index state ────────────────────────────────────────────────────────────────
_faiss_index = None
_doc_names: List[str] = []
_initialized = False
_index_version = "none"

# normalised entity value → the document occurrences it came from
_entity_index: Dict[str, List["DocEntity"]] = {}
_ner_used = False

# Longest indexed phrase, in words. Bounds prompt n-gram generation so we never
# build n-grams larger than anything we could possibly match.
_max_phrase_words = 1

# Which document each embedded chunk came from, parallel to the FAISS index.
_chunk_owners: List[str] = []

# Documents are embedded in overlapping chunks rather than whole. A ten-page
# contract collapsed into one 384-dim vector averages into mush that is roughly
# equidistant from everything; chunking keeps each passage's meaning intact, so
# a prompt resembling one clause actually scores high instead of being diluted
# by the other nine pages. The overlap stops a passage being split mid-sentence
# across a boundary and matching neither side.
_CHUNK_CHARS = 600
_CHUNK_OVERLAP = 120

# A match on these is conclusive on its own: the value is specific enough that
# it appearing in both a protected document and a prompt is not coincidence.
_HIGH_SPECIFICITY = frozenset({
    "SSN", "CREDIT_CARD", "EMAIL", "PHONE", "IBAN", "PASSPORT",
    "API_KEY", "REF_NUMBER", "PERSON",
})
# A match on these is weak alone — dates, sums and company names collide with
# innocent prompts constantly — so two from the same document are required.
_LOW_SPECIFICITY = frozenset({"DATE", "MONEY", "ORG", "LOC"})


@dataclass(frozen=True)
class DocEntity:
    doc_name: str
    type: str
    value: str


@dataclass(frozen=True)
class DocMatch:
    """One confidential value found in a prompt, and where it came from."""
    type: str
    value: str
    doc_name: str
    start: int
    end: int

    @property
    def conclusive(self) -> bool:
        return self.type in _HIGH_SPECIFICITY


@dataclass
class ShieldResult:
    matches: List[DocMatch] = field(default_factory=list)
    similarity: Optional[float] = None
    similar_document: Optional[str] = None
    confirmed_leak: bool = False       # entity evidence — drives block/redact
    topic_similar: bool = False        # cosine only — advisory

    @property
    def documents(self) -> List[str]:
        return sorted({m.doc_name for m in self.matches})


# ── Index construction ─────────────────────────────────────────────────────────
def _index_document(name: str, content: str) -> Tuple[Dict[str, List[DocEntity]], int]:
    """Extract every entity in one document and key it by normalised value."""
    index: Dict[str, List[DocEntity]] = {}
    longest = 1
    for e in ent.extract_all(content, use_ner=True):
        if not e.norm:
            continue
        index.setdefault(e.norm, []).append(DocEntity(name, e.type, e.value))
        if e.type in ent.PHRASE_TYPES:
            longest = max(longest, len(e.norm.split()))
    return index, longest


def _build_entity_index(docs) -> Tuple[Dict[str, List[DocEntity]], int]:
    merged: Dict[str, List[DocEntity]] = {}
    longest = 1
    for doc in docs:
        index, doc_longest = _index_document(doc.name, doc.content)
        for norm, occurrences in index.items():
            merged.setdefault(norm, []).extend(occurrences)
        longest = max(longest, doc_longest)
    return merged, longest


def _chunk_documents(docs) -> Tuple[List[str], List[str]]:
    """Split every document into overlapping passages. Returns (texts, owners)."""
    texts: List[str] = []
    owners: List[str] = []
    step = _CHUNK_CHARS - _CHUNK_OVERLAP
    for doc in docs:
        content = doc.content or ""
        for start in range(0, max(len(content), 1), step):
            chunk = content[start:start + _CHUNK_CHARS]
            if not chunk.strip():
                continue
            texts.append(chunk)
            owners.append(doc.name)
            if start + _CHUNK_CHARS >= len(content):
                break
    return texts, owners


def _build_faiss_index(embeddings):
    try:
        import faiss
        import numpy as np
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings.astype(np.float32))
        return index
    except Exception as e:
        print(f"[KnowledgeShield] FAISS unavailable: {e}")
        return None


async def initialize():
    global _faiss_index, _doc_names, _initialized, _index_version
    global _entity_index, _max_phrase_words, _ner_used, _chunk_owners

    try:
        from app.core.database import AsyncSessionLocal
        from app.models.confidential_doc import ConfidentialDocument
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ConfidentialDocument))
            docs = list(result.scalars().all())

        if not docs:
            print("[KnowledgeShield] No confidential documents – shield in standby.")
            _index_version = "none"
            _initialized = True
            return

        _doc_names = [d.name for d in docs]
        # Content is hashed, not just names: replacing a document's body under
        # the same name must invalidate every cached verdict about it.
        _index_version = hashlib.sha256(
            "|".join(sorted(f"{d.name}:{d.content}" for d in docs)).encode()
        ).hexdigest()[:16]

        loop = asyncio.get_event_loop()

        # Entity index. Independent of the encoder: this is the signal that
        # actually blocks leaks, so it must survive sentence-transformers being
        # absent. NER inside is blocking, hence the executor.
        _entity_index, _max_phrase_words = await loop.run_in_executor(
            None, _build_entity_index, docs
        )
        _ner_used = ent.ner_available()
        print(
            f"[KnowledgeShield] Entity index: {len(_entity_index)} values from "
            f"{len(docs)} documents (NER {'on' if _ner_used else 'off — regex only'})."
        )

        # Chunked embedding index (advisory similarity only).
        if encoder.is_available():
            chunks, _chunk_owners = _chunk_documents(docs)
            embeddings = await loop.run_in_executor(None, encoder.encode, chunks)
            if embeddings is not None:
                _faiss_index = _build_faiss_index(embeddings)
                print(
                    f"[KnowledgeShield] Similarity index built "
                    f"({len(chunks)} chunks from {len(docs)} documents)."
                )
        else:
            print("[KnowledgeShield] Encoder unavailable – similarity signal disabled.")

        _initialized = True

    except Exception as e:
        print(f"[KnowledgeShield] Initialization error: {e}")
        _initialized = True


# ── Prompt checking ────────────────────────────────────────────────────────────
def match_entities(prompt_text: str) -> List[DocMatch]:
    """
    Find values in *prompt_text* that exist in a protected document.

    Identifiers are regexed out of the prompt and looked up by normalised value,
    so reformatting ("492 83 7291" for "492-83-7291") does not evade the check.
    Names are found by intersecting the prompt's n-grams with the index, which
    avoids running NER on the hot path.
    """
    if not _entity_index or not prompt_text:
        return []

    matches: List[DocMatch] = []
    claimed: List[Tuple[int, int]] = []

    def _claim(start: int, end: int) -> bool:
        if any(start < e and s < end for s, e in claimed):
            return False
        claimed.append((start, end))
        return True

    # 1. Identifiers present verbatim in the prompt.
    for e in ent.extract_identifiers(prompt_text):
        for occurrence in _entity_index.get(e.norm, []):
            if _claim(e.start, e.end):
                matches.append(DocMatch(
                    occurrence.type, e.value, occurrence.doc_name, e.start, e.end,
                ))
            break

    # 2. Any other alphanumeric run that is in the index verbatim. The index
    #    holds only values taken from protected documents, so checking loose
    #    runs against it costs almost no precision while closing the gap where
    #    a value is reformatted into a shape none of the regexes recognise.
    #    Digit runs are scanned separately from mixed runs so that a label
    #    glued straight onto a value ("SSN492837291") still resolves to the
    #    digits the document actually contains.
    import re as _re
    for pattern in (r"[A-Za-z0-9][A-Za-z0-9-]{6,}", r"\d{7,}"):
        for m in _re.finditer(pattern, prompt_text):
            norm = ent.normalise("REF_NUMBER", m.group(0))
            occurrences = _entity_index.get(norm)
            if not occurrences or not _claim(m.start(), m.end()):
                continue
            matches.append(DocMatch(
                occurrences[0].type, m.group(0), occurrences[0].doc_name,
                m.start(), m.end(),
            ))

    # 3. Names/orgs, via n-gram intersection. Longest phrases first so
    #    "Dana Reyes" is preferred over a bare "Dana".
    grams = ent.ngrams(prompt_text, max_n=_max_phrase_words)
    for phrase in sorted(grams, key=lambda p: -len(p.split())):
        occurrences = _entity_index.get(phrase)
        if not occurrences:
            continue
        occurrence = next(
            (o for o in occurrences if o.type in ent.PHRASE_TYPES), occurrences[0]
        )
        if occurrence.type not in ent.PHRASE_TYPES:
            continue        # identifier already handled above with a real span
        start, end = grams[phrase]
        if _claim(start, end):
            matches.append(DocMatch(
                occurrence.type, prompt_text[start:end], occurrence.doc_name, start, end,
            ))

    return sorted(matches, key=lambda m: m.start)


async def check_similarity(prompt_text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Top-1 cosine against document chunks. Advisory signal only.

    Returns (score, document name) — chunking means the nearest neighbour
    identifies a specific passage, so the audit trail can name which document
    a prompt resembled instead of just how strongly it resembled something.
    """
    if not _initialized or _faiss_index is None:
        return None, None
    if not encoder.is_available():
        return None, None

    from app.core import cache
    key = cache.build_key("kshield", prompt_text, cache.knowledge_shield_fingerprint())
    cached = await cache.cache_get_async(key)
    if cached is not None:
        score_str, _, doc = cached.partition("|")
        try:
            return float(score_str), (doc or None)
        except ValueError:
            pass  # corrupt cache entry — fall through and recompute

    try:
        import numpy as np
        loop = asyncio.get_event_loop()
        emb = await loop.run_in_executor(None, encoder.encode, [prompt_text])
        if emb is None:
            return None, None
        scores, indices = _faiss_index.search(emb.astype(np.float32), k=1)
        result = float(scores[0][0])
        idx = int(indices[0][0])
        doc = _chunk_owners[idx] if 0 <= idx < len(_chunk_owners) else None
        await cache.cache_set_async(key, f"{result}|{doc or ''}")
        return result, doc
    except Exception as e:
        print(f"[KnowledgeShield] Similarity check error: {e}")
        return None, None


def confirm_leak(matches: List[DocMatch]) -> bool:
    """
    Decide whether the matches amount to a leak.

    One conclusive match is enough. Otherwise two weak matches from the SAME
    document are required — a single shared date or dollar figure is the kind
    of coincidence that would otherwise stop people doing ordinary work.
    """
    if any(m.conclusive for m in matches):
        return True
    per_doc: Dict[str, int] = {}
    for m in matches:
        if m.type in _LOW_SPECIFICITY:
            per_doc[m.doc_name] = per_doc.get(m.doc_name, 0) + 1
    return any(count >= 2 for count in per_doc.values())


async def check_prompt(prompt_text: str) -> ShieldResult:
    """
    Full shield check: exact entity evidence plus advisory topic similarity.

    A leak is confirmed by one conclusive entity match, or by two weak matches
    that come from the same document — one shared date or dollar figure is
    coincidence, two values from the same file is not.
    """
    result = ShieldResult()
    if not _initialized:
        return result

    result.matches = match_entities(prompt_text)
    result.confirmed_leak = confirm_leak(result.matches)

    result.similarity, result.similar_document = await check_similarity(prompt_text)
    if result.similarity is not None:
        result.topic_similar = result.similarity >= settings.KNOWLEDGE_SHIELD_THRESHOLD

    return result


def redact_matches(prompt_text: str, matches: List[DocMatch]) -> str:
    """Mask only the confidential spans, leaving the rest of the prompt usable."""
    return ent.redact(prompt_text, [
        ent.Entity(m.type, m.value, m.start, m.end, "") for m in matches
    ])


async def rebuild():
    global _faiss_index, _doc_names, _initialized, _entity_index
    global _max_phrase_words, _chunk_owners
    _faiss_index = None
    _doc_names = []
    _entity_index = {}
    _chunk_owners = []
    _max_phrase_words = 1
    _initialized = False
    await initialize()


def index_stats() -> dict:
    return {
        "documents":        len(_doc_names),
        "chunks":           len(_chunk_owners),
        "indexed_values":   len(_entity_index),
        "ner_enabled":      _ner_used,
        "similarity_ready": _faiss_index is not None,
        "index_version":    _index_version,
    }
