from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = False

    # This service's own database: it holds the protected documents, which no
    # other service reads. SQLite when run directly; Docker Compose points it
    # at its own database on the Postgres server.
    DATABASE_URL: str = "sqlite+aiosqlite:///./detection.db"

    # Shared with the backend, which sends it as a bearer token. Empty means
    # requests are not authenticated, and the service relies on not being
    # reachable: Docker Compose does not publish it and keeps it on a network
    # the frontend is not on. Set it wherever other workloads share the network.
    DETECTION_TOKEN: str = ""

    # Similarity at which the advisory same-topic warning fires. Blocking is
    # decided by policy rules in the backend, never by this number.
    KNOWLEDGE_SHIELD_THRESHOLD: float = 0.55

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # NER model for pulling names and organisations out of uploaded documents.
    # Runs at document upload only, never per prompt. Optional: if it cannot be
    # loaded, documents are indexed by regex identifiers alone and the shield
    # keeps working with reduced name coverage.
    NER_MODEL: str = "dslim/distilbert-NER"

    # Redis cache for the similarity search, the one call that runs a
    # transformer forward pass per prompt. Optional: if REDIS_URL is
    # unreachable or the redis package isn't installed, it runs uncached.
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
