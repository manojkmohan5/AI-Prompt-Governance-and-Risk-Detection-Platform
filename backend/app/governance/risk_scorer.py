"""
Risk Scoring Engine — ML-confidence-driven.

Score = sum of per-category contributions, where each contribution is
  base_points × confidence_scale (capped at base_points).
This means a BERT category detected at 0.90 scores higher than one at 0.42.
"""
from typing import List, Tuple

from app.governance.inspector import InspectionResult
from app.models.prompt import RiskLevel

# Base risk points per category (at maximum confidence)
_BASE: dict = {
    "PII_DATA":         50,
    "PROMPT_INJECTION": 80,
    "SENSITIVE_DATA":   45,
    "TOXICITY":         75,
    "IP_LEAK":          40,
    "ML_HIGH_RISK":     70,
}

# Normalisation: score = base × clamp(confidence / norm, 0, 1)
# norm set so confidence at the detection threshold (~0.36-0.40) yields ~65% of base,
# and confidence ≥0.55 yields full base score.
_NORM: dict = {
    "PII_DATA":         0.55,
    "PROMPT_INJECTION": 0.55,
    "SENSITIVE_DATA":   0.55,
    "TOXICITY":         0.55,
    "IP_LEAK":          0.50,
    "ML_HIGH_RISK":     0.50,
}

_CATEGORY_FROM_FLAG = {
    "PII_DETECTED":     "PII_DATA",
    "PROMPT_INJECTION": "PROMPT_INJECTION",
    "SENSITIVE_DATA":   "SENSITIVE_DATA",
    "TOXICITY":         "TOXICITY",
    "IP_LEAK":          "IP_LEAK",
    "ML_HIGH_RISK":     "ML_HIGH_RISK",
}


def score(result: InspectionResult) -> Tuple[int, RiskLevel, List[str]]:
    """Return (risk_score 0–100, RiskLevel, active_flags)."""
    s = 0

    for flag in result.flags:
        category = _CATEGORY_FROM_FLAG.get(flag)
        if category is None:
            continue
        confidence = result.ml_scores.get(category, 0.0)
        base = _BASE[category]
        norm = _NORM[category]
        contribution = int(base * min(confidence / norm, 1.0))
        s += contribution

    # Multi-flag co-occurrence bonus (complexity spike)
    risk_flags = [f for f in result.flags if f not in ("EXCESSIVE_LENGTH",)]
    if len(risk_flags) >= 3:
        s = min(s + 15, 100)
    elif len(risk_flags) == 2:
        s = min(s + 8, 100)

    # Length penalty
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

    return s, level, list(result.flags)
