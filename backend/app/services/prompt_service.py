"""
Prompt Service — orchestrates the full governance pipeline for each prompt.

Pipeline:
  1. Detection service: inspection (regex entities + injection phrases), the
     Knowledge Shield (document entity index + advisory similarity) and the
     risk score, in one call
  2. Anomaly Detection (Z-score per-user baseline)
  3. Compliance Mapping
  4. Policy Enforcement
  5. LLM Call (if not blocked), with leaked spans masked
  6. Detection service: the answer is checked, and masked where it leaks
  7. Persist

Steps 1 and 6 fail closed: if the detection service cannot answer,
DetectionUnavailable propagates, nothing is persisted, and the caller gets a
503 - a prompt is never sent, and an answer never delivered, unchecked.
"""
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.governance import compliance_mapper, policy_engine
from app.models.audit_log import AuditLog
from app.models.prompt import PolicyAction, PromptRecord, RiskLevel
from app.models.risk_event import RiskEvent, RiskEventSeverity
from app.models.user import User
from app.services import anomaly_service, detection_client, llm_service


# Most severe first. The stored "primary category" was flags[0] - whichever
# detector happened to append first - so a prompt blocked for a document
# leak that also contained PII was filed under PII_DETECTED.
_SEVERITY_ORDER = (
    "CONFIDENTIAL_DOC_LEAK", "PROMPT_INJECTION", "PII_DETECTED", "SENSITIVE_DATA",
    "USER_ANOMALY", "KNOWLEDGE_SHIELD_SIMILAR", "EXCESSIVE_LENGTH",
)


def primary_category(flags):
    """The most severe flag present, or None for a clean prompt."""
    return next((f for f in _SEVERITY_ORDER if f in flags), flags[0] if flags else None)


async def process(
    prompt_text: str,
    user: Optional[User],
    model: Optional[str],
    department: Optional[str],
    db: AsyncSession,
) -> PromptRecord:
    t_start = time.monotonic()
    # Resolved here so the record names the model that actually answered.
    model = model or settings.GROQ_MODEL

    username = user.username if user else "anonymous"
    dept = department or (user.department if user else None)

    # ── 1. Detection: inspection, Knowledge Shield, risk score ────────────────
    check = await detection_client.check_prompt(prompt_text)
    risk_score = check["risk_score"]
    risk_level = RiskLevel(check["risk_level"])
    flags = list(check["flags"])
    ks_score = check["similarity"]

    # Primary risk category for record storage. There is no model confidence
    # to record: most flags are exact matches, and the one soft signal
    # (KNOWLEDGE_SHIELD_SIMILAR) has a similarity score, stored separately in
    # knowledge_shield_score. Writing 1.0 here told the audit trail that an
    # advisory same-topic warning was a certainty.
    ml_category = primary_category(flags)
    ml_confidence = None

    # ── 2. Anomaly Detection ──────────────────────────────────────────────────
    is_anomaly, anomaly_z, _baseline_avg = await anomaly_service.check(user, risk_score, db)
    if is_anomaly and "USER_ANOMALY" not in flags:
        flags.append("USER_ANOMALY")
        risk_score = min(risk_score + 10, 100)

    # ── 3. Compliance Mapping ─────────────────────────────────────────────────
    compliance_tags = compliance_mapper.get_tags(flags)

    # ── 4. Policy Enforcement ─────────────────────────────────────────────────
    policy_action = await policy_engine.determine_action(risk_score, flags, dept, db)

    # ── 5. LLM Call (if not blocked) ─────────────────────────────────────────
    response_text: Optional[str] = None
    redacted_prompt: Optional[str] = None
    tokens_used = 0
    is_blocked = policy_action == PolicyAction.BLOCK.value

    if not is_blocked:
        send_text = prompt_text
        if policy_action == PolicyAction.REDACT.value:
            # PII, credentials and every value traced to a protected document,
            # masked by the detection service.
            redacted_prompt = check["redacted_text"]
            send_text = redacted_prompt

        response_text, tokens_used = await llm_service.complete(send_text, model)

        # ── 6. Detection: the answer ──────────────────────────────────────────
        answer = await detection_client.check_response(response_text)
        if answer["flags"]:
            flags.extend(answer["flags"])
            compliance_tags = compliance_mapper.get_tags(flags)
            # Flagging alone would still hand the leaked value to the caller.
            response_text = answer["redacted_text"]

    latency_ms = int((time.monotonic() - t_start) * 1000)

    # ── 7. Persist PromptRecord ───────────────────────────────────────────────
    record = PromptRecord(
        user_id=user.id if user else None,
        prompt_text=prompt_text,
        redacted_prompt=redacted_prompt,
        response_text=response_text,
        model_used=model,
        department=dept,
        username=username,
        risk_score=risk_score,
        risk_level=risk_level,
        flags=flags,
        policy_action=policy_action,
        is_blocked=is_blocked,
        tokens_used=tokens_used or None,
        latency_ms=latency_ms,
        knowledge_shield_score=ks_score,
        ml_risk_category=ml_category,
        ml_confidence=round(ml_confidence, 4) if ml_confidence else None,
        compliance_tags=compliance_tags,
        anomaly_detected=is_anomaly,
        anomaly_z_score=anomaly_z,
    )
    db.add(record)
    await db.flush()

    # ── 8. Audit Log ─────────────────────────────────────────────────────────
    audit = AuditLog(
        prompt_id=record.id,
        user_id=user.id if user else None,
        event_type="PROMPT_PROCESSED",
        event_data={
            "risk_score":       risk_score,
            "risk_level":       risk_level.value,
            "policy_action":    policy_action,
            "flags":            flags,
            "is_blocked":       is_blocked,
            "latency_ms":       latency_ms,
            "entities":         check["entities"],
            "injection_spans":  check["injection_spans"],
            "doc_matches":      check["doc_matches"],
            "shield_similarity": round(ks_score, 4) if ks_score is not None else None,
            "ml_category":      ml_category,
            "anomaly_detected": is_anomaly,
            "compliance_tags":  compliance_tags,
        },
        username=username,
        department=dept,
    )
    db.add(audit)

    # ── 9. Risk Events ───────────────────────────────────────────────────────
    _severity = {
        "PROMPT_INJECTION":      RiskEventSeverity.CRITICAL,
        "CONFIDENTIAL_DOC_LEAK": RiskEventSeverity.CRITICAL,
        "RESPONSE_DOC_LEAK":     RiskEventSeverity.CRITICAL,
        "RESPONSE_PII_LEAK":     RiskEventSeverity.HIGH,
        "RESPONSE_SECRET_LEAK":  RiskEventSeverity.CRITICAL,
        "PII_DETECTED":          RiskEventSeverity.HIGH,
        "SENSITIVE_DATA":        RiskEventSeverity.MEDIUM,
        "USER_ANOMALY":          RiskEventSeverity.HIGH,
    }
    for flag in flags:
        if flag in _severity:
            db.add(RiskEvent(
                prompt_id=record.id,
                risk_type=flag,
                severity=_severity[flag],
                details={
                    "risk_score":  risk_score,
                    "username":    username,
                    "ml_category": ml_category,
                    "documents":   check["documents"],
                    "doc_matches": check["doc_matches"],
                },
            ))

    await db.flush()
    return record
