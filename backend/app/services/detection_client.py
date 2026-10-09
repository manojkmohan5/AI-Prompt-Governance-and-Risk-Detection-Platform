"""
Client for the detection service, which checks every prompt and every answer.

Fails closed. When the service cannot be reached, times out, or answers with
an error, DetectionUnavailable is raised and the caller must stop: a prompt
nobody checked is never sent to the LLM, and an answer nobody checked is never
delivered. main.py turns it into a 503.

Document routes pass the service's own refusals through (DetectionRefused):
"this PDF is password-protected" is for the admin who picked the file.
"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Adding or removing a document re-indexes every document, NER included.
_DOCUMENT_TIMEOUT = 300

# Tests route requests to the detection app in-process instead of the network.
_transport: Optional[httpx.AsyncBaseTransport] = None


class DetectionUnavailable(Exception):
    """The detection service gave no usable answer."""


class DetectionRefused(Exception):
    """The detection service refused a document request, with a reason for the admin."""

    def __init__(self, status: int, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def _call(method: str, path: str, *, timeout: float, passthrough: bool = False, **kwargs):
    headers = {"Authorization": f"Bearer {settings.DETECTION_TOKEN}"} if settings.DETECTION_TOKEN else {}
    # ponytail: a new connection per call; share one client if this latency ever shows.
    try:
        async with httpx.AsyncClient(base_url=settings.DETECTION_URL, timeout=timeout,
                                     transport=_transport) as client:
            resp = await client.request(method, path, headers=headers, **kwargs)
    except httpx.HTTPError as e:
        logger.warning("Detection service unreachable (%s %s): %r", method, path, e)
        raise DetectionUnavailable(str(e)) from e

    if resp.is_success:
        return resp
    # A 401 or 403 is this platform's misconfiguration (DETECTION_TOKEN differs
    # between the two services), not something the admin can fix.
    if passthrough and 400 <= resp.status_code < 500 and resp.status_code not in (401, 403):
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = resp.text
        raise DetectionRefused(resp.status_code, detail)
    logger.warning("Detection service error (%s %s): HTTP %s", method, path, resp.status_code)
    raise DetectionUnavailable(f"HTTP {resp.status_code}")


# ── Checks ─────────────────────────────────────────────────────────────────────
async def check_prompt(text: str) -> dict:
    """Inspection, Knowledge Shield and risk score for a prompt."""
    return (await _call("POST", "/v1/check/prompt", json={"text": text},
                        timeout=settings.DETECTION_TIMEOUT_SECONDS)).json()


async def check_response(text: str) -> dict:
    """Flags for an LLM answer, and the answer as it may be delivered."""
    return (await _call("POST", "/v1/check/response", json={"text": text},
                        timeout=settings.DETECTION_TIMEOUT_SECONDS)).json()


# ── Protected documents ────────────────────────────────────────────────────────
async def list_documents() -> list:
    return (await _call("GET", "/v1/documents", timeout=settings.DETECTION_TIMEOUT_SECONDS)).json()


async def add_document(doc: dict) -> dict:
    return (await _call("POST", "/v1/documents", json=doc, timeout=_DOCUMENT_TIMEOUT,
                        passthrough=True)).json()


async def add_documents(docs: list) -> list:
    return (await _call("POST", "/v1/documents/batch", json=docs, timeout=_DOCUMENT_TIMEOUT,
                        passthrough=True)).json()


async def upload_document(filename: str, content_type: str, data: bytes,
                          name: Optional[str], category: str) -> dict:
    form = {"category": category, **({"name": name} if name is not None else {})}
    return (await _call("POST", "/v1/documents/upload", timeout=_DOCUMENT_TIMEOUT, passthrough=True,
                        files={"file": (filename, data, content_type)}, data=form)).json()


async def delete_document(doc_id) -> None:
    await _call("DELETE", f"/v1/documents/{doc_id}", timeout=_DOCUMENT_TIMEOUT, passthrough=True)


async def status() -> dict:
    return (await _call("GET", "/v1/status", timeout=settings.DETECTION_TIMEOUT_SECONDS)).json()
