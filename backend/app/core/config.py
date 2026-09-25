import secrets
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AI Governance Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite+aiosqlite:///./governance.db"

    SECRET_KEY: str = "change-this-to-a-long-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Groq (OpenAI-compatible)
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Blocking and warning thresholds are policy rules in the database, not
    # settings. This one only sets when the advisory same-topic warning fires.
    KNOWLEDGE_SHIELD_THRESHOLD: float = 0.55

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # NER model for pulling names and organisations out of uploaded documents.
    # Runs at document upload only, never per prompt. Optional: if it cannot be
    # loaded, documents are indexed by regex identifiers alone and the shield
    # keeps working with reduced name coverage.
    NER_MODEL: str = "dslim/distilbert-NER"

    # Redis cache for the Knowledge Shield similarity search, the one call left
    # that runs a transformer forward pass. Optional: if REDIS_URL is
    # unreachable or the redis package isn't installed, it falls back to
    # running uncached rather than failing.
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = {"env_file": ".env", "extra": "ignore"}


# Every placeholder key in this repository - the default above, .env.example,
# docker-compose.yml - starts with this. They are all public.
_PLACEHOLDER_KEY_PREFIX = "change-this"


def ensure_secret_key(s: "Settings") -> None:
    """
    Never sign tokens with a key published in this repository.

    Anyone who reads the repo could otherwise mint a valid token for any user,
    and `docker compose up` without a SECRET_KEY used exactly such a key. A
    placeholder is swapped for a random key for this process: sign-ins end on
    restart, which is fine for development, and a real deployment sets
    SECRET_KEY anyway. A key someone actually chose is left alone.
    """
    if s.SECRET_KEY.startswith(_PLACEHOLDER_KEY_PREFIX):
        s.SECRET_KEY = secrets.token_urlsafe(64)
        print("[Security] SECRET_KEY is a placeholder published in this repository; "
              "using a random key for this process. Sign-ins end when it restarts - "
              "set SECRET_KEY to keep them.")


settings = Settings()
ensure_secret_key(settings)
