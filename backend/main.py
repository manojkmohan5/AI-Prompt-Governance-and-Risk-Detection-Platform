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


# Flags no detector raises any more. They came from the DistilBERT classifier,
# which was removed; a rule matching one can never fire, but still displays as
# active — so an admin reading "Block Toxic Content" believes toxicity is blocked.
_RETIRED_FLAGS = ("ML_HIGH_RISK", "IP_LEAK", "TOXICITY",
                  "RESPONSE_UNSAFE_CONTENT", "RESPONSE_INJECTION_ATTEMPT")
_RETIRED_NOTE = "Retired: no detector raises this flag any more. "


async def _migrate_policy_rules(conn) -> None:
    """
    Bring policy rules in databases seeded before the classifier was removed
    in line with the flags the detectors actually raise. Safe to run on every
    startup: each statement only touches rows still in the old state.

    Seeding skips a database that already has users, so without this an old
    database kept its document-leak rule keyed to KNOWLEDGE_SHIELD. Nothing
    raises that flag now, so a name leak (70 points) or two weak values from
    one document (60) fell through to "Warn High Risk" — and WARN forwards the
    prompt to the LLM unchanged.
    """
    await conn.execute(text(
        "UPDATE policy_rules SET condition_value = 'CONFIDENTIAL_DOC_LEAK' "
        "WHERE condition_value = 'KNOWLEDGE_SHIELD'"
    ))
    await conn.execute(text(
        "UPDATE policy_rules SET description = :new WHERE description = :old"
    ), {
        "old": "Block prompts that match confidential document embeddings.",
        "new": "Block prompts containing a value confirmed to come from a protected document.",
    })
    # Deactivated rather than deleted, and marked, so an admin can see what
    # happened and why. The marker also makes this one-shot per rule: an admin
    # who deliberately switches one back on is not overridden on next startup.
    placeholders = ", ".join(f":f{i}" for i in range(len(_RETIRED_FLAGS)))
    await conn.execute(text(
        f"UPDATE policy_rules SET is_active = 0, "
        f"description = :note || COALESCE(description, '') "
        f"WHERE condition_value IN ({placeholders}) "
        f"AND COALESCE(description, '') NOT LIKE 'Retired:%'"
    ), {"note": _RETIRED_NOTE, **{f"f{i}": f for i, f in enumerate(_RETIRED_FLAGS)}})


async def _remove_unloadable_policy_rules(conn) -> None:
    """
    Delete policy rules whose condition type or action is not a valid value.

    Such a row cannot be loaded, and the policy engine loads every active rule
    on every prompt - one of them fails every prompt, and GET /policies too, so
    it cannot be removed from the UI. The API now refuses them, but one saved
    before that stays until removed here. A rule that cannot be loaded has no
    behaviour to preserve; each deletion is logged so it can be recreated.
    """
    from app.models.policy_rule import ActionType, ConditionType

    # Stored as enum member names, e.g. FLAG_CONTAINS, BLOCK.
    conditions = [c.name for c in ConditionType]
    actions = [a.name for a in ActionType]
    params = {**{f"c{i}": v for i, v in enumerate(conditions)},
              **{f"a{i}": v for i, v in enumerate(actions)}}
    where = (f"condition_type NOT IN ({', '.join(f':c{i}' for i in range(len(conditions)))}) "
             f"OR action NOT IN ({', '.join(f':a{i}' for i in range(len(actions)))})")
    bad = (await conn.execute(
        text(f"SELECT name, condition_type, action FROM policy_rules WHERE {where}"), params
    )).fetchall()
    for name, condition, action in bad:
        print(f"[Migrate] Removed unloadable policy rule {name!r} "
              f"(condition_type={condition!r}, action={action!r}); recreate it on the Settings page.")
    if bad:
        await conn.execute(text(f"DELETE FROM policy_rules WHERE {where}"), params)


async def _migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(prompts)"))
        existing = {row[1] for row in result.fetchall()}
        for col_name, col_type in _NEW_COLUMNS:
            if col_name not in existing:
                await conn.execute(text(f"ALTER TABLE prompts ADD COLUMN {col_name} {col_type}"))
        await _remove_unloadable_policy_rules(conn)
        await _migrate_policy_rules(conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Apply non-destructive column migrations
    await _migrate()

    # Build the confidential-document entity index. Nothing is fine-tuned at
    # boot any more; NER runs only over documents already in the database.
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
