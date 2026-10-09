"""
Protected documents, admin only. The documents and their index live in the
detection service; these routes check the caller is an admin and forward.

Employees are exactly the people the shield protects documents from, so every
route here takes require_admin - the detection service itself never sees an
end user's token.
"""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import require_admin
from app.schemas.prompt import ConfidentialDocCreate, ConfidentialDocOut
from app.services import detection_client

router = APIRouter(prefix="/knowledge-shield", tags=["knowledge-shield"])

# The limit the detection service enforces. Checked here too, so an oversized
# file is refused before it is buffered and forwarded.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _forward(call):
    try:
        return await call
    except detection_client.DetectionRefused as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.get("/documents", response_model=list[ConfidentialDocOut])
async def list_documents(_=Depends(require_admin)):
    return await _forward(detection_client.list_documents())


@router.post("/documents", response_model=ConfidentialDocOut, status_code=201)
async def add_document(body: ConfidentialDocCreate, _=Depends(require_admin)):
    return await _forward(detection_client.add_document(body.model_dump()))


@router.post("/documents/upload", response_model=ConfidentialDocOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    name: str | None = Form(None, max_length=300),
    category: str = Form("general", max_length=100),
    _=Depends(require_admin),
):
    """Add a protected document from a file; the detection service extracts its text."""
    # One byte past the limit is enough to know it is too large; reading the
    # whole file first let any upload size land in memory before being refused.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File is larger than the {MAX_UPLOAD_BYTES // 1024 // 1024}MB limit.")
    return await _forward(detection_client.upload_document(
        file.filename or "upload", file.content_type or "", data, name, category))


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: uuid.UUID, _=Depends(require_admin)):
    await _forward(detection_client.delete_document(doc_id))


@router.get("/status")
async def shield_status(_=Depends(require_admin)):
    return await _forward(detection_client.status())
