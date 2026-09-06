import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.embeddings import knowledge_shield
from app.models.confidential_doc import ConfidentialDocument
from app.schemas.prompt import ConfidentialDocCreate, ConfidentialDocOut
from app.services import document_text

router = APIRouter(prefix="/knowledge-shield", tags=["knowledge-shield"])


@router.get("/documents", response_model=list[ConfidentialDocOut])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(ConfidentialDocument).order_by(ConfidentialDocument.created_at.desc())
    )
    return [ConfidentialDocOut.model_validate(d) for d in result.scalars().all()]


@router.post("/documents", response_model=ConfidentialDocOut, status_code=201)
async def add_document(
    body: ConfidentialDocCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    doc = ConfidentialDocument(**body.model_dump())
    db.add(doc)
    await db.flush()
    # Rebuild FAISS index with new document
    await knowledge_shield.rebuild()
    return ConfidentialDocOut.model_validate(doc)


@router.post("/documents/upload", response_model=ConfidentialDocOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    category: str = Form("general"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Add a protected document from a file instead of pasted text.

    Admin only, like every route on this router — an employee cannot add to or
    read the protected set. The extracted text is stored and indexed exactly as
    a pasted document is: this is a second way in, not a second code path.
    """
    data = await file.read()
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
    db.add(doc)
    await db.flush()
    await knowledge_shield.rebuild()
    return ConfidentialDocOut.model_validate(doc)


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(ConfidentialDocument).where(ConfidentialDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.flush()
    await knowledge_shield.rebuild()


@router.get("/status")
async def shield_status(_=Depends(require_admin)):
    from app.embeddings import encoder
    return {
        "encoder_available": encoder.is_available(),
        "index_ready": knowledge_shield._faiss_index is not None,
        "initialized": knowledge_shield._initialized,
        # How much of each document is actually protected. ner_enabled False
        # means names were not indexed and only identifiers are covered.
        **knowledge_shield.index_stats(),
    }
