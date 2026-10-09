"""
Detection service: everything that reads text for confidential content.

It answers two questions for the backend, which decides what to do with the
answers (policy rules, the LLM call, the audit trail):

  POST /v1/check/prompt    what is in this prompt, and how risky is it
  POST /v1/check/response  did this answer leak anything, and the masked text

and it owns the protected documents those checks compare against, with the
routes the backend's admin-only Knowledge Shield pages call.

Internal only. The backend is its one caller; it is not published to the host
and never sees an end user's token. See DETECTION_TOKEN in config.py.
"""
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from detection import cache, document_text, encoder, knowledge_shield, response_inspector, risk_scorer
from detection import entities as ent
from detection.config import settings
from detection.database import Base, engine, get_db
from detection.inspector import inspector
from detection.models import ConfidentialDocument


def require_service_token(authorization: Optional[str] = Header(None)) -> None:
    if not settings.DETECTION_TOKEN:
        return
    if not secrets.compare_digest(authorization or "", f"Bearer {settings.DETECTION_TOKEN}"):
        raise HTTPException(status_code=401, detail="Invalid service token")


router = APIRouter(prefix="/v1", dependencies=[Depends(require_service_token)])


# ── Checks ─────────────────────────────────────────────────────────────────────
class TextIn(BaseModel):
    text: str = Field(..., max_length=200_000)


class EntityOut(BaseModel):
    type: str
    value: str


class DocMatchOut(BaseModel):
    type: str
    value: str
    documents: List[str]


class PromptCheck(BaseModel):
    risk_score: int
    risk_level: str
    flags: List[str]
    entities: List[EntityOut]
    injection_spans: List[str]
    doc_matches: List[DocMatchOut]   # every match, confirmed leak or not, for the audit trail
    documents: List[str]             # the documents those matches came from
    similarity: Optional[float]
    redacted_text: str               # what a REDACT policy sends to the LLM


class ResponseCheck(BaseModel):
    flags: List[str]
    redacted_text: str               # the answer as it may be delivered


@router.post("/check/prompt", response_model=PromptCheck)
async def check_prompt(body: TextIn):
    inspection = inspector.inspect(body.text)
    # Runs unconditionally. It used to be gated behind a risk score, which meant
    # a calmly-worded prompt quoting a document verbatim - the exact thing this
    # check exists to catch - was never compared against the documents at all.
    shield = await knowledge_shield.check_prompt(body.text)
    score, level, flags = risk_scorer.score(
        inspection,
        doc_matches=shield.matches if shield.confirmed_leak else [],
        topic_similar=shield.topic_similar,
    )
    # Masks PII, credentials, and any value traced to a protected document.
    # Redacting PII alone forwarded API keys and passwords to the LLM verbatim,
    # and a document's contract dates or party names with them.
    spans = [e for e in inspection.entities if e.type in ent.PII_TYPES or e.type in ent.SECRET_TYPES]
    spans += [ent.Entity(m.type, m.value, m.start, m.end, "") for m in shield.matches]
    return PromptCheck(
        risk_score=score,
        risk_level=level,
        flags=flags,
        entities=[EntityOut(type=e.type, value=e.value) for e in inspection.entities],
        injection_spans=inspection.injection_spans,
        doc_matches=[DocMatchOut(type=m.type, value=m.value, documents=list(m.doc_names or (m.doc_name,)))
                     for m in shield.matches],
        documents=shield.documents,
        similarity=shield.similarity,
        redacted_text=ent.redact(body.text, spans),
    )


@router.post("/check/response", response_model=ResponseCheck)
async def check_response(body: TextIn):
    # The prompt is not the only way a document leaks: the model can name
    # protected values in an answer to a prompt that contained none.
    result = response_inspector.inspect_response(body.text)
    redacted = response_inspector.redact_response(body.text, result) if result.flags else body.text
    return ResponseCheck(flags=result.flags, redacted_text=redacted)


# ── Protected documents ────────────────────────────────────────────────────────
class DocumentIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    category: str = Field("general", max_length=100)


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    created_at: datetime

    model_config = {"from_attributes": True}


async def _save(db: AsyncSession, docs: List[ConfidentialDocument]) -> List[DocumentOut]:
    db.add_all(docs)
    # Commit before rebuilding. The rebuild reads the document set through its
    # own session, which cannot see this transaction until it commits - so
    # rebuilding first indexed the set as it was BEFORE this change.
    await db.commit()
    await knowledge_shield.rebuild()
    return [DocumentOut.model_validate(d) for d in docs]


@router.get("/documents", response_model=List[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConfidentialDocument).order_by(ConfidentialDocument.created_at.desc()))
    return [DocumentOut.model_validate(d) for d in result.scalars().all()]


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def add_document(body: DocumentIn, db: AsyncSession = Depends(get_db)):
    return (await _save(db, [ConfidentialDocument(**body.model_dump())]))[0]


@router.post("/documents/batch", response_model=List[DocumentOut], status_code=201)
async def add_documents(body: List[DocumentIn], db: AsyncSession = Depends(get_db)):
    # One rebuild for the lot. Adding them one at a time re-runs NER over
    # every document already indexed, once per document added.
    return await _save(db, [ConfidentialDocument(**d.model_dump()) for d in body])


@router.post("/documents/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None, max_length=300),
    category: str = Form("general", max_length=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a protected document from a file. The extracted text is stored and
    indexed exactly as a pasted document is: a second way in, not a second
    code path.
    """
    # One byte past the limit is enough to know it is too large; reading the
    # whole file first let any upload size land in memory before being refused.
    data = await file.read(document_text.MAX_UPLOAD_BYTES + 1)
    filename = file.filename or "upload"
    try:
        content = document_text.extract(filename, file.content_type or "", data)
    except document_text.ExtractionError as e:
        # The message names the actual problem (scanned PDF, legacy .doc, too
        # large) so the admin knows what to do with the file they picked.
        raise HTTPException(status_code=e.status, detail=e.detail)
    doc = ConfidentialDocument(
        name=(name or "").strip() or filename.rsplit(".", 1)[0][:300],
        content=content,
        category=category,
    )
    return (await _save(db, [doc]))[0]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    doc = (await db.execute(select(ConfidentialDocument).where(ConfidentialDocument.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()   # before the rebuild; see _save
    await knowledge_shield.rebuild()


@router.get("/status")
async def status():
    return {
        "encoder_available": encoder.is_available(),
        "index_ready": knowledge_shield._faiss_index is not None,
        "initialized": knowledge_shield._initialized,
        # How much of each document is actually protected. ner_enabled False
        # means names were not indexed and only identifiers are covered.
        **knowledge_shield.index_stats(),
    }


# ── App ────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if not settings.DETECTION_TOKEN:
        print("[Security] DETECTION_TOKEN is not set: requests are not authenticated. "
              "Keep this service unreachable from anything but the backend.")
    # NER runs over the stored documents here, not per prompt.
    await knowledge_shield.initialize()
    yield
    await cache.close_async_client()
    await engine.dispose()


app = FastAPI(title="Detection service", lifespan=lifespan, debug=settings.DEBUG,
              docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
