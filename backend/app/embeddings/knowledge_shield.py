"""
Knowledge Shield
Detects semantic similarity between user prompts and protected confidential documents.
Uses SentenceTransformers + FAISS for vector search.
All heavy imports are lazy so the server starts even without ML packages installed.
"""
import asyncio
from typing import Optional

from app.core.config import settings
from app.embeddings import encoder

_faiss_index = None
_doc_names: list[str] = []
_initialized = False


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
    global _faiss_index, _doc_names, _initialized

    if not encoder.is_available():
        print("[KnowledgeShield] Encoder unavailable – shield disabled.")
        _initialized = True
        return

    try:
        from app.core.database import AsyncSessionLocal
        from app.models.confidential_doc import ConfidentialDocument
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ConfidentialDocument))
            docs = list(result.scalars().all())

        if not docs:
            print("[KnowledgeShield] No confidential documents – shield in standby.")
            _initialized = True
            return

        texts = [d.content for d in docs]
        _doc_names = [d.name for d in docs]

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(None, encoder.encode, texts)

        if embeddings is not None:
            _faiss_index = _build_faiss_index(embeddings)
            print(f"[KnowledgeShield] Index built with {len(docs)} documents.")
        _initialized = True

    except Exception as e:
        print(f"[KnowledgeShield] Initialization error: {e}")
        _initialized = True


async def check_similarity(prompt_text: str) -> Optional[float]:
    if not _initialized or _faiss_index is None:
        return None
    if not encoder.is_available():
        return None

    try:
        import numpy as np
        loop = asyncio.get_event_loop()
        emb = await loop.run_in_executor(None, encoder.encode, [prompt_text])
        if emb is None:
            return None
        emb_f32 = emb.astype(np.float32)
        scores, _ = _faiss_index.search(emb_f32, k=1)
        return float(scores[0][0])
    except Exception as e:
        print(f"[KnowledgeShield] Similarity check error: {e}")
        return None


async def rebuild():
    global _faiss_index, _doc_names, _initialized
    _faiss_index = None
    _doc_names = []
    _initialized = False
    await initialize()
