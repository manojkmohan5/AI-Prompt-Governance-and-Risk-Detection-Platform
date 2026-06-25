"""
Prompt Service — orchestrates the full governance pipeline for each prompt.

Pipeline:
  1. BERT Inspection  (ML-only, no regex)
  2. Risk Scoring     (confidence-weighted)
  3. Knowledge Shield (FAISS semantic search)
  4. Anomaly Detection (Z-score per-user baseline)
  5. Compliance Mapping
  6. Policy Enforcement
  7. LLM Call (if not blocked)
  8. Response Inspection
  9. Persist
"""
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.embeddings import knowledge_shield
from app.governance import inspector as insp_module
from app.governance import ml_classifier, compliance_mapper, policy_engine, response_inspector, risk_scorer
from app.models.audit_log import AuditLog
from app.models.prompt import PolicyAction, PromptRecord, RiskLevel
from app.models.risk_event import RiskEvent, RiskEventSeverity
from app.models.user import User
from app.services import anomaly_service, llm_service


async def process(
    prompt_text: str,
    user: Optional[User],
    model: str,
    department: Optional[str],
    db: AsyncSession,
) -> PromptRecord:
    t_start = time.monotonic()

    username = user.username if user else "anonymous"
    dept = department or (user.department if user else None)

    # ── 1. ML Inspection (fine-tuned DistilBERT, zero regex) ──────────────────
    inspection = insp_module.inspector.inspect(prompt_text)
    ml_scores = inspection.ml_scores

    # ── 2. Risk Scoring (confidence-weighted per category) ────────────────────
    risk_score, risk_level, flags = risk_scorer.score(inspection)

    # Derive primary ML category for record storage (highest above-threshold score)
    ml_category, ml_confidence = ml_classifier.top_category(ml_scores)

    # ── 3. Knowledge Shield ───────────────────────────────────────────────────
    ks_score = None
    if risk_score >= 20:
        ks_score = await knowledge_shield.check_similarity(prompt_text)
        if ks_score is not None and ks_score >= settings.KNOWLEDGE_SHIELD_THRESHOLD:
            if "KNOWLEDGE_SHIELD" not in flags:
                flags.append("KNOWLEDGE_SHIELD")
            risk_score = min(risk_score + 20, 100)
            if risk_score >= 80:
                risk_level = RiskLevel.CRITICAL
            elif risk_score >= 60:
                risk_level = RiskLevel.HIGH

    # ── 4. Anomaly Detection ──────────────────────────────────────────────────
    is_anomaly, anomaly_z, _baseline_avg = await anomaly_service.check(user, risk_score, db)
    if is_anomaly and "USER_ANOMALY" not in flags:
        flags.append("USER_ANOMALY")
        risk_score = min(risk_score + 10, 100)

    # ── 5. Compliance Mapping ─────────────────────────────────────────────────
    compliance_tags = compliance_mapper.get_tags(flags)

    # ── 6. Policy Enforcement ─────────────────────────────────────────────────
    policy_action = await policy_engine.determine_action(risk_score, flags, dept, db)

    # ── 7. LLM Call (if not blocked) ─────────────────────────────────────────
    response_text: Optional[str] = None
    redacted_prompt: Optional[str] = None
    tokens_used = 0
    is_blocked = policy_action == PolicyAction.BLOCK.value

    if not is_blocked:
        send_text = prompt_text
        if policy_action == PolicyAction.REDACT.value:
            redacted_prompt = insp_module.inspector.redact_pii(prompt_text)
            send_text = redacted_prompt

        response_text, tokens_used = await llm_service.complete(send_text, model)

        # ── 8. Response Inspection ────────────────────────────────────────────
        resp_result = response_inspector.inspect_response(response_text)
        if resp_result.flags:
            flags.extend(resp_result.flags)
            compliance_tags = compliance_mapper.get_tags(flags)

    latency_ms = int((time.monotonic() - t_start) * 1000)

    # ── 9. Persist PromptRecord ───────────────────────────────────────────────
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

    # ── 10. Audit Log ─────────────────────────────────────────────────────────
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
            "ml_scores":        {k: round(v, 3) for k, v in ml_scores.items()},
            "ml_category":      ml_category,
            "ml_confidence":    round(ml_confidence, 4) if ml_confidence else None,
            "anomaly_detected": is_anomaly,
            "compliance_tags":  compliance_tags,
        },
        username=username,
        department=dept,
    )
    db.add(audit)

    # ── 11. Risk Events ───────────────────────────────────────────────────────
    _severity = {
        "PROMPT_INJECTION": RiskEventSeverity.CRITICAL,
        "KNOWLEDGE_SHIELD": RiskEventSeverity.HIGH,
        "TOXICITY":         RiskEventSeverity.CRITICAL,
        "PII_DETECTED":     RiskEventSeverity.HIGH,
        "SENSITIVE_DATA":   RiskEventSeverity.MEDIUM,
        "IP_LEAK":          RiskEventSeverity.HIGH,
        "ML_HIGH_RISK":     RiskEventSeverity.HIGH,
        "USER_ANOMALY":     RiskEventSeverity.HIGH,
    }
    for flag in flags:
        if flag in _severity:
            db.add(RiskEvent(
                prompt_id=record.id,
                risk_type=flag,
                severity=_severity[flag],
                details={
                    "risk_score":    risk_score,
                    "username":      username,
                    "ml_category":   ml_category,
                    "ml_confidence": round(ml_confidence, 4) if ml_confidence else None,
                    "ml_scores":     {k: round(v, 3) for k, v in ml_scores.items()},
                },
            ))

    await db.flush()
    return record
