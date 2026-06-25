"""
Embedding encoder – wraps SentenceTransformers with a graceful fallback.
All imports are lazy so the server starts without ML packages.
"""
from typing import List, Optional

from app.core.config import settings

_model = None
_available = False


def _load_model():
    global _model, _available
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        _available = True
    except Exception as e:
        print(f"[KnowledgeShield] SentenceTransformer unavailable: {e}")
        _available = False


def encode(texts: List[str]) -> Optional[object]:
    """Return numpy array of shape (N, dim) or None if unavailable."""
    if _model is None:
        _load_model()
    if not _available or _model is None:
        return None
    return _model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def is_available() -> bool:
    if _model is None:
        _load_model()
    return _available
