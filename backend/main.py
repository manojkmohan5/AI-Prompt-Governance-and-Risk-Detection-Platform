from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, engine

# New columns added in the ML upgrade — added safely via ALTER TABLE
_NEW_COLUMNS = [
    ("ml_risk_category", "VARCHAR(50)"),
    ("ml_confidence",    "FLOAT"),
    ("compliance_tags",  "JSON"),
    ("anomaly_detected", "BOOLEAN DEFAULT 0"),
    ("anomaly_z_score",  "FLOAT"),
]


async def _migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(prompts)"))
        existing = {row[1] for row in result.fetchall()}
        for col_name, col_type in _NEW_COLUMNS:
            if col_name not in existing:
                await conn.execute(text(f"ALTER TABLE prompts ADD COLUMN {col_name} {col_type}"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Apply non-destructive column migrations
    await _migrate()

    # Pre-load / fine-tune DistilBERT classifier so first request is fast
    from app.governance import ml_classifier
    ml_classifier.initialize()

    # Initialize Knowledge Shield
    from app.embeddings import knowledge_shield
    await knowledge_shield.initialize()

    yield

    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    debug=True,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.v1.router import router as api_router
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
