"""
Risk Scoring Engine.

Every signal is now evidence: entities found by regex, values matched against
the confidential document index, injection phrases matched verbatim. Scores are
flat points for what was actually found rather than a probability scaled by
model confidence, because there is no longer a model producing one.

The one soft signal, embedding similarity to a protected document, is scored
low on purpose. It says "same subject", which describes plenty of legitimate
work, so it can warn but must never reach the block threshold by itself.

Score = sum of contributions, capped at 100.
"""
from typing import List, Optional, Sequence, Tuple

from app.governance import entities as ent
from app.governance.inspector import InspectionResult
from app.models.prompt import RiskLevel

# ── Evidence-based points ──────────────────────────────────────────────────────
# A confirmed document leak outweighs everything else: the value in the prompt
# is known to exist in a protected file, which is the exact thing this platform
# is for. Identifier leaks outrank name leaks because a matching SSN cannot be
# coincidence, whereas a matching name occasionally can.
_LEAK_IDENTIFIER = 85     # SSN/card/email/phone/ref from a protected doc
_LEAK_NAME       = 70     # PERSON from a protected doc
_LEAK_WEAK       = 60     # 2+ dates/sums/orgs from the same protected doc

# Standalone PII in the prompt (not traced to any document), by worst type seen.
_PII_STRONG = 50          # SSN, card, passport, IBAN
_PII_MODERATE = 30        # email, phone
_PII_PER_EXTRA = 5        # each additional distinct PII value

_STRONG_PII_TYPES = frozenset({"SSN", "CREDIT_CARD", "PASSPORT", "IBAN"})

# Topic similarity with no entity evidence. Deliberately small — it means
# "same subject as a protected document", which describes plenty of legitimate
# work, so on its own it must never reach the block threshold.
_TOPIC_ONLY = 15

# ── Pattern-matched points ─────────────────────────────────────────────────────
# Flat, not confidence-scaled: these come from regex hits, which are binary.
# There is no probability left to weight now that the classifier is gone.
_BASE = {
    "PROMPT_INJECTION": 80,
    "SENSITIVE_DATA":   45,
}

_NON_RISK_FLAGS = frozenset({"EXCESSIVE_LENGTH", "KNOWLEDGE_SHIELD_SIMILAR"})


def _pii_points(entities: Sequence[ent.Entity]) -> int:
    pii = [e for e in entities if e.type in ent.PII_TYPES]
    if not pii:
        return 0
    base = _PII_STRONG if any(e.type in _STRONG_PII_TYPES for e in pii) else _PII_MODERATE
    return base + _PII_PER_EXTRA * (len({e.norm for e in pii}) - 1)


def _leak_points(doc_matches: Sequence) -> int:
    """Points for the strongest document match present. Duck-typed on .type."""
    if not doc_matches:
        return 0
    types = {m.type for m in doc_matches}
    if types - {"PERSON", "DATE", "MONEY", "ORG", "LOC"}:
        return _LEAK_IDENTIFIER
    if "PERSON" in types:
        return _LEAK_NAME
    return _LEAK_WEAK


def score(
    result: InspectionResult,
    doc_matches: Optional[Sequence] = None,
    topic_similar: bool = False,
) -> Tuple[int, RiskLevel, List[str]]:
    """Return (risk_score 0–100, RiskLevel, active_flags)."""
    flags = list(result.flags)
    s = 0

    # ── Confirmed leak from a protected document ──────────────────────────────
    if doc_matches:
        s += _leak_points(doc_matches)
        if "CONFIDENTIAL_DOC_LEAK" not in flags:
            flags.append("CONFIDENTIAL_DOC_LEAK")
    elif topic_similar:
        # Similarity with nothing to back it up: warn, never block.
        s += _TOPIC_ONLY
        if "KNOWLEDGE_SHIELD_SIMILAR" not in flags:
            flags.append("KNOWLEDGE_SHIELD_SIMILAR")

    # ── PII present in the prompt ─────────────────────────────────────────────
    s += _pii_points(result.entities)

    # ── Pattern signals ───────────────────────────────────────────────────────
    for flag, base in _BASE.items():
        if flag in flags:
            s += base

    # ── Co-occurrence bonus (complexity spike) ────────────────────────────────
    risk_flags = [f for f in flags if f not in _NON_RISK_FLAGS]
    if len(risk_flags) >= 3:
        s += 15
    elif len(risk_flags) == 2:
        s += 8

    if result.prompt_length > 4000:
        s += 5
    elif result.prompt_length > 2000:
        s += 2

    s = min(s, 100)

    if s >= 80:
        level = RiskLevel.CRITICAL
    elif s >= 60:
        level = RiskLevel.HIGH
    elif s >= 30:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    return s, level, flags
