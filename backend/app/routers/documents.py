"""
Document upload and processing router.

Handles multipart file uploads (PDF, DOCX, images, text),
delegates extraction to the document processor service,
and persists results for downstream analysis.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.schemas import (
    DocumentDetail,
    DocumentResult,
    DocumentTextResponse,
    UploadResponse,
)
from app.services.document_processor import (
    extract_pdf,
    extract_docx,
    extract_image,
    extract_text,
)

router = APIRouter()

# In-memory store for MVP — replace with PostgreSQL in production
_document_store: dict[str, dict[str, Any]] = {}


ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".tif": "image",
    ".txt": "text",
}


def _get_file_type(filename: str) -> str:
    """Determine file type from extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(ALLOWED_EXTENSIONS.keys())}"
            ),
        )
    return ALLOWED_EXTENSIONS[ext]


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a document for processing",
)
async def upload_document(
    file: UploadFile = File(..., description="Corporate document to analyse"),
) -> UploadResponse:
    """Accept a document upload, extract text, and return metadata.

    Supported formats:
    - **PDF** — text extracted with page and line metadata via PyMuPDF
    - **DOCX** — paragraphs extracted via python-docx
    - **Image** (PNG, JPG, TIFF) — OCR placeholder (Google Document AI)
    - **Text** — direct passthrough with line numbering
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_type = _get_file_type(file.filename)

    # Validate file size
    content = await file.read()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
        )

    # Save to uploads directory
    doc_id = uuid.uuid4().hex
    upload_dir = os.path.join(settings.UPLOAD_DIR, doc_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # Process the document
    try:
        if file_type == "pdf":
            result: DocumentResult = await extract_pdf(file_path)
        elif file_type == "docx":
            result = await extract_docx(file_path)
        elif file_type == "image":
            result = await extract_image(file_path)
        elif file_type == "text":
            text_content = content.decode("utf-8", errors="replace")
            result = await extract_text(text_content)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {exc}",
        ) from exc

    # Persist in memory store
    _document_store[doc_id] = {
        "document_id": doc_id,
        "filename": file.filename,
        "file_type": file_type,
        "file_path": file_path,
        "page_count": len(result.pages),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "text": result.text,
        "pages": [p.model_dump() for p in result.pages],
        "metadata": result.metadata,
    }

    return UploadResponse(
        document_id=doc_id,
        filename=file.filename,
        file_type=file_type,
        page_count=len(result.pages),
        message="Document uploaded and processed successfully",
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    summary="Get document metadata",
)
async def get_document(document_id: str) -> DocumentDetail:
    """Retrieve metadata for a previously uploaded document."""
    doc = _document_store.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentDetail(
        document_id=doc["document_id"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        page_count=doc["page_count"],
        uploaded_at=datetime.fromisoformat(doc["uploaded_at"]),
        text_preview=doc["text"][:500] if doc["text"] else "",
    )


@router.get(
    "/{document_id}/text",
    response_model=DocumentTextResponse,
    summary="Get extracted text for a document",
)
async def get_document_text(document_id: str) -> DocumentTextResponse:
    """Return the full extracted text and page-level detail."""
    doc = _document_store.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.models.schemas import PageContent

    pages = [PageContent(**p) for p in doc["pages"]]
    return DocumentTextResponse(
        document_id=doc["document_id"],
        text=doc["text"],
        pages=pages,
    )
