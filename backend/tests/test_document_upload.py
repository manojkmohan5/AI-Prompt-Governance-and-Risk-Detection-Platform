"""
Tests for uploaded-document text extraction.

The happy paths run against the real files in sample_documents/, so this also
guards the fixtures themselves: if a sample document is regenerated badly, or a
parser stops recovering the values it used to, these fail rather than the
Knowledge Shield quietly indexing less than it did before.
"""
import pathlib

import pytest

from app.governance import entities as ent
from app.services import document_text as dt

SAMPLES = pathlib.Path(__file__).resolve().parents[2] / "sample_documents"

MIME = {
    ".pdf": "application/pdf",
    ".docx": dt.DOCX_MIME,
    ".csv": "text/csv",
    ".md": "text/markdown",
}


def _sample_files():
    if not SAMPLES.is_dir():
        return []
    # README.md documents the fixtures, it is not one of them — and it quotes
    # example identifiers, so it would pass the entity assertions for the wrong
    # reason and hide a genuinely empty fixture.
    return sorted(
        p for p in SAMPLES.iterdir()
        if p.suffix in MIME and p.name.lower() != "readme.md"
    )


@pytest.mark.parametrize("path", _sample_files(), ids=lambda p: p.name)
def test_sample_documents_extract_to_text(path):
    text = dt.extract(path.name, MIME[path.suffix], path.read_bytes())
    assert len(text) > dt.MIN_EXTRACTED_CHARS


@pytest.mark.parametrize("path", _sample_files(), ids=lambda p: p.name)
def test_sample_documents_still_yield_indexable_entities(path):
    """
    Extraction that returns text but loses the identifiers is the failure mode
    that matters here — the document would index as protected while containing
    nothing the shield can actually match a prompt against.
    """
    text = dt.extract(path.name, MIME[path.suffix], path.read_bytes())
    found = ent.extract_identifiers(text)
    assert found, f"no identifiers survived extraction of {path.name}"


def test_every_sample_format_is_covered():
    """A format with no fixture is a format nothing tests."""
    suffixes = {p.suffix for p in _sample_files()}
    assert {".pdf", ".docx", ".csv", ".md"} <= suffixes


# ── Rejections ────────────────────────────────────────────────────────────────
def test_empty_file_is_rejected():
    with pytest.raises(dt.ExtractionError) as e:
        dt.extract("empty.pdf", "application/pdf", b"")
    assert e.value.status == 422


def test_oversized_file_is_rejected_before_parsing():
    data = b"x" * (dt.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(dt.ExtractionError) as e:
        dt.extract("big.txt", "text/plain", data)
    assert e.value.status == 413


def test_legacy_doc_gets_its_own_message():
    # python-docx cannot read .doc at all, so the generic "corrupt file" error
    # would send the admin looking for a problem that isn't there.
    with pytest.raises(dt.ExtractionError) as e:
        dt.extract("contract.doc", "application/msword", b"\xd0\xcf\x11\xe0" + b"x" * 100)
    assert e.value.status == 415
    assert ".docx" in e.value.detail


def test_unsupported_type_is_rejected():
    with pytest.raises(dt.ExtractionError) as e:
        dt.extract("logo.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 100)
    assert e.value.status == 415


def test_text_with_almost_no_content_is_rejected():
    # Stands in for a scanned PDF: parses fine, yields nothing worth protecting.
    with pytest.raises(dt.ExtractionError) as e:
        dt.extract("scan.txt", "text/plain", b"  page 1  ")
    assert e.value.status == 422


def test_corrupt_pdf_is_rejected_without_leaking_parser_internals():
    with pytest.raises(dt.ExtractionError) as e:
        dt.extract("broken.pdf", "application/pdf", b"%PDF-1.4 not really a pdf")
    assert e.value.status == 422
    assert "Traceback" not in e.value.detail


# ── Extraction detail ─────────────────────────────────────────────────────────
def test_csv_content_is_read_as_text():
    data = b"client,ssn\nDana Reyes,492-83-7291\n"
    text = dt.extract("clients.csv", "text/csv", data)
    assert "492-83-7291" in text
    assert [e.type for e in ent.extract_identifiers(text)] == ["SSN"]


def test_runs_of_whitespace_are_collapsed():
    # PDF extraction emits ragged spacing; spans are offsets into the stored
    # text, so it is normalised once here rather than at every read.
    text = dt.extract("notes.txt", "text/plain", b"Contract     number    NW-2024-8871 is active")
    assert "  " not in text
    assert [e.value for e in ent.extract_identifiers(text)] == ["NW-2024-8871"]
