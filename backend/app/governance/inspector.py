"""
Prompt Inspection Engine — ML-only, zero regex.

Detection is entirely performed by the fine-tuned DistilBERT classifier in ml_classifier.py.
Each risk category above its calibrated sigmoid threshold is promoted to a governance flag.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from app.governance import ml_classifier

# Maps BERT output category → governance flag name
_CATEGORY_TO_FLAG: Dict[str, str] = {
    "PII_DATA":         "PII_DETECTED",
    "PROMPT_INJECTION": "PROMPT_INJECTION",
    "SENSITIVE_DATA":   "SENSITIVE_DATA",
    "TOXICITY":         "TOXICITY",
    "IP_LEAK":          "IP_LEAK",
    "ML_HIGH_RISK":     "ML_HIGH_RISK",
}


@dataclass
class InspectionResult:
    flags: List[str] = field(default_factory=list)
    ml_scores: Dict[str, float] = field(default_factory=dict)
    prompt_length: int = 0

    # Convenience accessors for downstream code
    @property
    def pii_detected(self) -> bool:
        return "PII_DETECTED" in self.flags

    @property
    def injection_detected(self) -> bool:
        return "PROMPT_INJECTION" in self.flags

    @property
    def sensitive_data_detected(self) -> bool:
        return "SENSITIVE_DATA" in self.flags

    @property
    def toxicity_detected(self) -> bool:
        return "TOXICITY" in self.flags


class PromptInspector:
    def inspect(self, text: str) -> InspectionResult:
        result = InspectionResult(prompt_length=len(text))

        # Run fine-tuned DistilBERT → per-category sigmoid probabilities
        result.ml_scores = ml_classifier.classify(text)

        # Promote categories above their threshold to governance flags
        for category, score in result.ml_scores.items():
            threshold = ml_classifier.THRESHOLDS.get(category, 0.38)
            if score >= threshold:
                flag = _CATEGORY_TO_FLAG.get(category)
                if flag and flag not in result.flags:
                    result.flags.append(flag)

        if len(text) > 4000:
            result.flags.append("EXCESSIVE_LENGTH")

        return result

    def redact_pii(self, text: str) -> str:
        """ML-based entity redaction using a BERT NER model."""
        return ml_classifier.redact_entities(text)


inspector = PromptInspector()
