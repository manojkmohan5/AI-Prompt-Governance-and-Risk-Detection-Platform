"""
Prompt Inspection Engine — no model on the hot path.

Every per-prompt check here is regex or a dict lookup:

  entities.py → PII and confidential identifiers (SSN, card, email, phone,
                contract dates, money, reference numbers, API keys), returned
                as exact character spans so a value can be masked without
                destroying the sentence around it.

  _INJECTION  → a phrase list for the common prompt-injection openers.

The fine-tuned DistilBERT classifier this module used to call has been removed.
It cost a 268MB download and a ~3 minute fine-tune on every fresh boot, it was
trained on roughly 200 synthetic examples written by hand in a single source
file, and for PII it was strictly worse than a regex — it could only score a
whole string, never tell you which characters were the SSN.

Known ceiling: the injection phrase list catches the common openers verbatim
and is beaten by paraphrase, which a classifier would have handled. Toxicity
detection is gone entirely rather than replaced by a word list, which is
trivially evaded and false-positives on ordinary words. If either matters,
the right upgrade is a hosted moderation endpoint (the openai package is
already a dependency) rather than another local model.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List

from app.governance import entities as ent

# ── Prompt-injection phrase list ───────────────────────────────────────────────
# Anchored on the instruction-override verbs rather than on any single wording,
# so minor rephrasings inside a pattern still match.
_INJECTION: List[re.Pattern] = [
    re.compile(p, re.I) for p in (
        r"\b(?:ignore|disregard|forget|override)\b[^.!?\n]{0,40}?"
        r"\b(?:instruction|rule|guideline|constraint|polic|direction|prompt|training)",
        r"\bbypass\b[^.!?\n]{0,40}?\b(?:filter|guideline|rule|restriction|polic|safety|check)",
        r"\bact\s+as\b[^.!?\n]{0,20}?\b(?:unrestricted|uncensored|unfiltered|jailbroken|dan)\b",
        r"\byou\s+(?:have|are)\s+no\b[^.!?\n]{0,20}?"
        r"\b(?:restriction|limit|rule|constraint|filter|guideline)",
        r"\bjailbreak\b",
        r"\bpretend\s+(?:you|to\s+be)\b[^.!?\n]{0,30}?\bno\b[^.!?\n]{0,20}?"
        r"\b(?:restriction|rule|limit|filter)",
        r"\b(?:reveal|show|print|repeat)\b[^.!?\n]{0,30}?\b(?:system\s+prompt|initial\s+instruction)",
        r"\b(?:developer|god|admin)\s+mode\b",
    )
]


@dataclass
class InspectionResult:
    flags: List[str] = field(default_factory=list)
    entities: List[ent.Entity] = field(default_factory=list)
    injection_spans: List[str] = field(default_factory=list)
    prompt_length: int = 0

    # Retained so existing callers and the stored audit shape keep working.
    ml_scores: Dict[str, float] = field(default_factory=dict)

    @property
    def pii_entities(self) -> List[ent.Entity]:
        """Entities identifying a person, as opposed to dates or sums."""
        return [e for e in self.entities if e.type in ent.PII_TYPES]

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
        return False        # no longer detected; see module docstring


def detect_injection(text: str) -> List[str]:
    """Return the matched injection phrases, verbatim, for the audit trail."""
    hits: List[str] = []
    for pattern in _INJECTION:
        m = pattern.search(text)
        if m:
            hits.append(m.group(0).strip())
    return hits


class PromptInspector:
    def inspect(self, text: str) -> InspectionResult:
        result = InspectionResult(prompt_length=len(text))

        result.entities = ent.extract_identifiers(text)
        if result.pii_entities:
            result.flags.append("PII_DETECTED")
        if any(e.type == "API_KEY" for e in result.entities):
            result.flags.append("SENSITIVE_DATA")

        result.injection_spans = detect_injection(text)
        if result.injection_spans:
            result.flags.append("PROMPT_INJECTION")

        if len(text) > 4000:
            result.flags.append("EXCESSIVE_LENGTH")

        return result

    def redact_pii(self, text: str) -> str:
        """Mask each PII span in place, leaving the rest of the prompt intact."""
        return ent.redact(text, [
            e for e in ent.extract_identifiers(text) if e.type in ent.PII_TYPES
        ])


inspector = PromptInspector()
