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
    # The one default model. Groq retires models; when it does, change this
    # (or GROQ_MODEL in .env) - nothing else names a model.
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # The detection service checks every prompt and answer; see
    # app/services/detection_client.py. If it cannot answer, prompts are
    # refused (503) rather than sent unchecked. DETECTION_TOKEN must match the
    # service's own; empty on both means unauthenticated, for local use.
    DETECTION_URL: str = "http://localhost:8002"
    DETECTION_TOKEN: str = ""
    DETECTION_TIMEOUT_SECONDS: float = 10.0

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
