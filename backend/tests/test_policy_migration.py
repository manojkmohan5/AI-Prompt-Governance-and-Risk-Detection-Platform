"""
Tests for the startup migration that repairs policy rules in old databases.

Seeding skips any database that already has users, so a database seeded before
the classifier was removed kept rules keyed to flags nothing raises any more.
The one that mattered was the document-leak rule on KNOWLEDGE_SHIELD: with it
dead, a name leak fell through to WARN, which forwards the prompt unchanged.

Uses a real in-memory SQLite database through the ORM, so rows are stored
exactly as the app stores them rather than as the test assumes they are.
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.policy_rule import ActionType, ConditionType, PolicyRule
from main import _migrate_policy_rules

OLD_LEAK_DESCRIPTION = "Block prompts that match confidential document embeddings."


def _rule(name, value, action=ActionType.BLOCK, description=None, active=True):
    return PolicyRule(
        name=name, description=description, condition_type=ConditionType.FLAG_CONTAINS,
        condition_value=value, action=action, priority=50, is_active=active,
    )


async def _run(rows, migrations=1, between=None):
    """Seed *rows*, run the migration *migrations* times, return rules by name."""
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with Session() as db:
        db.add_all(rows)
        await db.commit()

    for i in range(migrations):
        async with engine.begin() as conn:
            await _migrate_policy_rules(conn)
        if between and i < migrations - 1:
            async with Session() as db:
                await between(db)
                await db.commit()

    async with Session() as db:
        rules = {r.name: r for r in (await db.execute(select(PolicyRule))).scalars()}
    await engine.dispose()
    return rules


def test_old_leak_rule_is_rekeyed_to_the_flag_that_is_raised():
    rules = asyncio.run(_run([_rule("Block KS", "KNOWLEDGE_SHIELD", description=OLD_LEAK_DESCRIPTION)]))
    leak = rules["Block KS"]
    assert leak.condition_value == "CONFIDENTIAL_DOC_LEAK"
    assert leak.is_active
    assert "embeddings" not in leak.description


def test_rules_on_retired_flags_are_switched_off_and_say_why():
    rules = asyncio.run(_run([_rule("Block Toxic Content", "TOXICITY"),
                              _rule("Warn IP Leak", "IP_LEAK", action=ActionType.WARN)]))
    for name in ("Block Toxic Content", "Warn IP Leak"):
        assert not rules[name].is_active
        assert rules[name].description.startswith("Retired:")


def test_rules_on_live_flags_are_left_alone():
    rules = asyncio.run(_run([_rule("Redact PII", "PII_DETECTED", action=ActionType.REDACT,
                                    description="Redact before the LLM.")]))
    pii = rules["Redact PII"]
    assert (pii.condition_value, pii.is_active, pii.description) == \
           ("PII_DETECTED", True, "Redact before the LLM.")


def test_running_on_every_startup_changes_nothing_the_second_time():
    rules = asyncio.run(_run([_rule("Block Toxic Content", "TOXICITY", description="Toxicity.")],
                             migrations=3))
    assert rules["Block Toxic Content"].description.count("Retired:") == 1


def test_an_admin_who_switches_a_retired_rule_back_on_is_not_overridden():
    async def reactivate(db):
        rule = (await db.execute(select(PolicyRule))).scalar_one()
        rule.is_active = True

    rules = asyncio.run(_run([_rule("Block Toxic Content", "TOXICITY")],
                             migrations=2, between=reactivate))
    assert rules["Block Toxic Content"].is_active
