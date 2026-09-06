"""
Entity extraction for confidential-data leak detection.

Two extractors, split by what each is actually good at:

  Regex → format-defined identifiers (SSN, card, email, phone, contract dates,
          money, reference numbers). Exact character spans, deterministic,
          no model, no training data. Runs on both documents and prompts.

  NER   → PERSON / ORG / LOC, which have no fixed format and cannot be
          regexed. Runs at DOCUMENT UPLOAD ONLY — never on the prompt hot path.

Prompts are not NER'd. A person's name only matters here if it is a name that
appears in a protected document, so prompt-side name detection is an index
lookup against entities already extracted from those documents. That keeps
precision high (no guessing whether "Dana Reyes" is a person) and keeps the
per-prompt cost to regex plus set lookups.
"""
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

# ── Entity types ───────────────────────────────────────────────────────────────
# Identifier types are extracted by regex from any text.
IDENTIFIER_TYPES = frozenset({
    "SSN", "CREDIT_CARD", "EMAIL", "PHONE", "IBAN", "PASSPORT",
    "API_KEY", "DATE", "MONEY", "REF_NUMBER",
})
# Phrase types come from NER at document-ingest time and are matched in prompts
# by n-gram intersection rather than by regex.
PHRASE_TYPES = frozenset({"PERSON", "ORG", "LOC"})

# Types that identify a specific individual (drives the PII flag / compliance tags).
PII_TYPES = frozenset({"SSN", "CREDIT_CARD", "EMAIL", "PHONE", "PASSPORT", "IBAN", "PERSON"})


@dataclass(frozen=True)
class Entity:
    type: str
    value: str      # verbatim text as it appeared
    start: int      # character offset, inclusive
    end: int        # character offset, exclusive
    norm: str       # normalised form used for cross-document matching


# ── Regex extractors ───────────────────────────────────────────────────────────
# Order matters: on an overlap the earlier (more specific) pattern wins, so a
# 9-digit SSN is never re-tagged as a phone number or a reference number.
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("API_KEY", re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}"
        r"|AKIA[0-9A-Z]{16}"
        r"|gh[pousr]_[A-Za-z0-9]{20,}"
        r"|xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    # Separator may be dash, dot or space — reformatting is the cheapest
    # evasion there is, and all three spellings normalise to the same value.
    ("SSN", re.compile(r"\b\d{3}[-. ]\d{2}[-. ]\d{4}\b")),
    # Unseparated form only when a label makes the intent explicit; a bare
    # 9-digit run is far too common to treat as an SSN on its own.
    ("SSN", re.compile(
        r"(?:\bssn\b|social\s+security(?:\s+(?:no\.?|number))?|\btax\s*id\b)"
        r"\s*[:#-]?\s*(\d{9})\b", re.I)),
    # Luhn-verified below; the pattern alone would match any long digit run.
    ("CREDIT_CARD", re.compile(r"\b\d(?:[ -]?\d){12,18}\b")),
    ("PASSPORT", re.compile(r"\b[A-Z]{1,2}\d{7,8}\b")),
    ("DATE", re.compile(
        r"\b(?:\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}/\d{1,2}/\d{2,4}"
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})\b")),
    ("MONEY", re.compile(r"(?:USD|EUR|GBP|\$|€|£)\s?\d[\d,]*(?:\.\d{1,2})?\b", re.I)),
    ("PHONE", re.compile(
        r"(?:\+?\d{1,3}[-. ]?)?(?:\(\d{3}\)|\b\d{3})[-. ]\d{3}[-. ]\d{4}\b")),
    # Contextual: only a reference number when a label precedes it, so bare
    # integers in ordinary prose are never indexed as confidential identifiers.
    ("REF_NUMBER", re.compile(
        r"\b(?:account|acct|contract|agreement|policy|invoice|employee|patient"
        r"|case|claim|member|customer|order|po|reference|ref)\s*"
        r"(?:no\.?|number|num|#|id)?\s*[:#-]?\s*"
        r"(?=[A-Za-z0-9-]*\d)([A-Za-z0-9][A-Za-z0-9-]{3,19})\b", re.I)),
]

# Month name → number, for normalising written dates onto the ISO form so that
# "March 15, 1985", "03/15/1985" and "1985-03-15" all match each other.
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _luhn_ok(digits: str) -> bool:
    """Luhn checksum. Rejects the digit runs that merely look card-shaped."""
    if not 13 <= len(digits) <= 19:
        return False
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _normalise_date(raw: str) -> str:
    """Best-effort ISO yyyy-mm-dd, so equivalent date spellings compare equal."""
    s = raw.strip().rstrip(".,")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yr < 100:
            yr += 2000 if yr < 50 else 1900
        return f"{yr:04d}-{mo:02d}-{day:02d}"
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        mo = _MONTHS.get(m.group(1).lower())
        if mo:
            return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", s)
    if m:
        mo = _MONTHS.get(m.group(2).lower())
        if mo:
            return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(1)):02d}"
    return s.lower()


def normalise(entity_type: str, raw: str) -> str:
    """
    Canonical form used for matching a prompt against the document index.

    Formatting is stripped so that reformatting an identifier does not evade
    detection: "492-83-7291", "492 83 7291" and "492837291" all normalise the
    same, and so do "$185,000" and "USD 185000".
    """
    s = raw.strip()
    if entity_type == "DATE":
        return _normalise_date(s)
    if entity_type == "EMAIL":
        return s.lower()
    if entity_type == "MONEY":
        digits = re.sub(r"[^\d.]", "", s)
        return digits[:-3] if digits.endswith(".00") else digits
    if entity_type in PHRASE_TYPES:
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
    # Identifiers: drop separators entirely.
    return re.sub(r"[^a-z0-9]", "", s.lower())


def extract_identifiers(text: str) -> List[Entity]:
    """
    Regex-extract every format-defined identifier in *text*, with spans.

    On overlapping matches the earlier pattern in _PATTERNS wins, so each
    character belongs to at most one entity and a span is never double-labelled.
    """
    found: List[Entity] = []
    for etype, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            # Labelled patterns capture only the identifier, not the label.
            group = 1 if m.lastindex else 0
            raw = m.group(group)
            start, end = m.span(group)
            if etype == "CREDIT_CARD" and not _luhn_ok(re.sub(r"\D", "", raw)):
                continue
            found.append(Entity(etype, raw, start, end, normalise(etype, raw)))

    return _drop_overlaps(found, {t: i for i, (t, _) in enumerate(_PATTERNS)})


def _drop_overlaps(entities: List[Entity], priority: Dict[str, int]) -> List[Entity]:
    """Keep the highest-priority entity on each overlapping span; longest breaks ties."""
    ordered = sorted(
        entities,
        key=lambda e: (priority.get(e.type, 99), -(e.end - e.start), e.start),
    )
    kept: List[Entity] = []
    for e in ordered:
        if any(e.start < k.end and k.start < e.end for k in kept):
            continue
        kept.append(e)
    return sorted(kept, key=lambda e: e.start)


# ── NER (document ingest only) ─────────────────────────────────────────────────
# Generic entities that a NER model happily tags but which carry no
# confidentiality: indexing them is what would make the shield fire on
# unrelated prompts, so they are dropped before they ever reach the index.
_GENERIC_PHRASES = frozenset({
    "united states", "usa", "us", "uk", "united kingdom", "europe", "eu", "asia",
    "america", "american", "english", "google", "microsoft", "amazon", "apple",
    "inc", "llc", "ltd", "corp", "corporation", "company", "gmbh", "plc",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
})
_MIN_PHRASE_LEN = 4          # characters; drops "Bob", "AI", stray initials
_NER_MIN_SCORE = 0.85        # model confidence floor
# Distilled NER checkpoint: same architecture size as the classifier that
# used to run on every prompt, but pretrained on CoNLL-2003 and used here
# only at document upload. Overridable via NER_MODEL.

_ner_pipeline = None
_ner_available: Optional[bool] = None


def ner_available() -> bool:
    """True once the NER pipeline has loaded. Mirrors encoder.is_available()."""
    global _ner_pipeline, _ner_available
    if _ner_available is None:
        try:
            from transformers import pipeline
            from app.core.config import settings
            _ner_pipeline = pipeline(
                "ner", model=settings.NER_MODEL, aggregation_strategy="simple",
            )
            _ner_available = True
        except Exception as e:                                   # pragma: no cover
            print(f"[Entities] NER unavailable, documents indexed by regex only: {e}")
            _ner_available = False
    return _ner_available


def extract_names(text: str) -> List[Entity]:
    """
    NER-extract PERSON / ORG / LOC spans. Document-ingest path only — this
    loads a ~260MB model and is far too slow for per-prompt use.

    Returns [] when the model is unavailable, so the shield degrades to
    regex-only identifier coverage rather than failing the upload.
    """
    if not ner_available() or not text.strip():
        return []

    _TYPE_MAP = {"PER": "PERSON", "ORG": "ORG", "LOC": "LOC"}
    out: List[Entity] = []
    try:
        # BERT caps at 512 tokens; window the document so long contracts are
        # fully covered rather than silently truncated to their first page.
        for offset, chunk in _windows(text, size=1500, overlap=200):
            for span in _ner_pipeline(chunk):
                etype = _TYPE_MAP.get(span.get("entity_group", ""))
                if etype is None or float(span.get("score", 0)) < _NER_MIN_SCORE:
                    continue
                raw = span["word"].strip()
                norm = normalise(etype, raw)
                if len(norm) < _MIN_PHRASE_LEN or norm in _GENERIC_PHRASES:
                    continue
                out.append(Entity(
                    etype, raw,
                    offset + int(span["start"]), offset + int(span["end"]), norm,
                ))
    except Exception as e:                                       # pragma: no cover
        print(f"[Entities] NER extraction failed: {e}")
        return []

    # Same span may be found twice where windows overlap.
    seen, deduped = set(), []
    for e in out:
        if (e.start, e.end) in seen:
            continue
        seen.add((e.start, e.end))
        deduped.append(e)
    return deduped


def _windows(text: str, size: int, overlap: int) -> Iterable[Tuple[int, str]]:
    if len(text) <= size:
        yield 0, text
        return
    start = 0
    while start < len(text):
        yield start, text[start:start + size]
        start += size - overlap


def extract_all(text: str, use_ner: bool = False) -> List[Entity]:
    """Identifiers always; names only when *use_ner* (document ingest)."""
    entities = extract_identifiers(text)
    if use_ner:
        taken = [(e.start, e.end) for e in entities]
        for name in extract_names(text):
            if not any(name.start < end and start < name.end for start, end in taken):
                entities.append(name)
    return sorted(entities, key=lambda e: e.start)


# ── Redaction ──────────────────────────────────────────────────────────────────
def redact(text: str, entities: List[Entity]) -> str:
    """
    Replace exactly the entity spans with typed placeholders, leaving the rest
    of the sentence intact so the LLM still receives a usable question.
    """
    if not entities:
        return text
    out, cursor = [], 0
    for e in sorted(entities, key=lambda x: x.start):
        if e.start < cursor:      # overlapping span already covered
            continue
        out.append(text[cursor:e.start])
        out.append(f"[{e.type}_REDACTED]")
        cursor = e.end
    out.append(text[cursor:])
    return "".join(out)


def ngrams(text: str, max_n: int = 4) -> Dict[str, Tuple[int, int]]:
    """
    Normalised 1..max_n word n-grams of *text* → character span of each.

    This is how a prompt is checked against document PERSON/ORG entities
    without running NER on the prompt: build the prompt's n-grams once, then
    intersect with the index. O(len(prompt)) set lookups instead of a scan
    per indexed phrase.
    """
    tokens = [(m.group(0).lower(), m.start(), m.end())
              for m in re.finditer(r"[A-Za-z0-9]+", text)]
    out: Dict[str, Tuple[int, int]] = {}
    for n in range(1, max_n + 1):
        for i in range(len(tokens) - n + 1):
            window = tokens[i:i + n]
            phrase = " ".join(w for w, _, _ in window)
            out.setdefault(phrase, (window[0][1], window[-1][2]))
    return out
