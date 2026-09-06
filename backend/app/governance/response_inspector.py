"""
Response Inspection — checks what the LLM sends back.

Two things matter on the way out:

  1. Confidential document content in the response. Same entity index used on
     the prompt: if a value from a protected document appears in the answer,
     the document leaked regardless of how the prompt was worded.

  2. Credentials and PII in the response. Regex over the same identifier
     patterns — an API key or an SSN in generated text is a leak whether the
     model invented it or repeated it.

This is regex plus dict lookups, so unlike the classifier it previously used
it is cheap enough to run on every response with no model loaded.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from app.governance import entities as ent

_SECRET_TYPES = frozenset({"API_KEY", "IBAN", "CREDIT_CARD"})


@dataclass
class ResponseInspectionResult:
    secrets_detected: bool = False
    pii_detected: bool = False
    doc_leak_detected: bool = False
    flags: List[str] = field(default_factory=list)
    entities: List[ent.Entity] = field(default_factory=list)
    doc_matches: List = field(default_factory=list)
    ml_scores: Dict[str, float] = field(default_factory=dict)   # retained for audit shape


def inspect_response(text: str) -> ResponseInspectionResult:
    result = ResponseInspectionResult()
    if not text or not text.strip():
        return result

    result.entities = ent.extract_identifiers(text)

    if any(e.type in _SECRET_TYPES for e in result.entities):
        result.secrets_detected = True
        result.flags.append("RESPONSE_SECRET_LEAK")

    if any(e.type in ent.PII_TYPES for e in result.entities):
        result.pii_detected = True
        result.flags.append("RESPONSE_PII_LEAK")

    # Imported here rather than at module scope: knowledge_shield imports the
    # governance package, and this keeps that dependency one-directional.
    from app.embeddings import knowledge_shield

    result.doc_matches = knowledge_shield.match_entities(text)
    if any(m.conclusive for m in result.doc_matches):
        result.doc_leak_detected = True
        result.flags.append("RESPONSE_DOC_LEAK")

    return result


def redact_response(text: str, result: ResponseInspectionResult) -> str:
    """Mask leaked spans in the response, keeping the rest of the answer usable."""
    spans = [e for e in result.entities if e.type in ent.PII_TYPES or e.type in _SECRET_TYPES]
    spans += [
        ent.Entity(m.type, m.value, m.start, m.end, "") for m in result.doc_matches
    ]
    return ent.redact(text, spans)
