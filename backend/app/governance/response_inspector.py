"""
Response Inspection — ML-based, zero regex.

Scans LLM output for credential leakage, harmful instructions, and injection
attempts using the same fine-tuned DistilBERT multi-label classifier used for
prompt inspection.

Long responses are split into overlapping character windows; the worst-case
(maximum) confidence per category wins. Thresholds are intentionally higher
than prompt thresholds so that explanatory / educational LLM responses about
security topics do not produce false positives.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from app.governance import ml_classifier

# Character window size per chunk (~300 words, well within BERT's 512-token limit)
_CHUNK_SIZE = 900
_CHUNK_OVERLAP = 150

# Category → response flag
_CATEGORY_TO_FLAG: Dict[str, str] = {
    "SENSITIVE_DATA":   "RESPONSE_SECRET_LEAK",
    "ML_HIGH_RISK":     "RESPONSE_SECRET_LEAK",
    "TOXICITY":         "RESPONSE_UNSAFE_CONTENT",
    "PROMPT_INJECTION": "RESPONSE_INJECTION_ATTEMPT",
}

# Higher thresholds than prompt inspection: a response explaining security topics
# (e.g. "API keys look like sk-...") should NOT trigger; only genuinely harmful
# or leaking content should.
_THRESHOLDS: Dict[str, float] = {
    "SENSITIVE_DATA":   0.55,
    "ML_HIGH_RISK":     0.52,
    "TOXICITY":         0.58,
    "PROMPT_INJECTION": 0.55,
}


@dataclass
class ResponseInspectionResult:
    secrets_detected: bool = False
    unsafe_content: bool = False
    flags: List[str] = field(default_factory=list)
    ml_scores: Dict[str, float] = field(default_factory=dict)


def _chunks(text: str) -> List[str]:
    if len(text) <= _CHUNK_SIZE:
        return [text]
    parts, start = [], 0
    while start < len(text):
        parts.append(text[start: start + _CHUNK_SIZE])
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return parts


def inspect_response(text: str) -> ResponseInspectionResult:
    result = ResponseInspectionResult()
    if not text or not text.strip():
        return result

    # Accumulate maximum confidence per tracked category across all chunks
    max_scores: Dict[str, float] = {cat: 0.0 for cat in _CATEGORY_TO_FLAG}

    for chunk in _chunks(text):
        scores = ml_classifier.classify(chunk)
        for cat in _CATEGORY_TO_FLAG:
            if scores.get(cat, 0.0) > max_scores[cat]:
                max_scores[cat] = scores[cat]

    result.ml_scores = max_scores

    for cat, flag in _CATEGORY_TO_FLAG.items():
        if max_scores[cat] >= _THRESHOLDS.get(cat, 0.55) and flag not in result.flags:
            result.flags.append(flag)
            if flag == "RESPONSE_SECRET_LEAK":
                result.secrets_detected = True
            elif flag == "RESPONSE_UNSAFE_CONTENT":
                result.unsafe_content = True

    return result
