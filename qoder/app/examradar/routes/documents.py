"""Document import endpoint."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException

from ..ingest import ingest_bytes, ValidationError
from ..seekdb import get_documents

router = APIRouter()


@router.post("/api/documents")
def upload_document(
    file: UploadFile = File(...),
    course_id: str = Form(...),
    doc_kind: str = Form(...),
    x_examradar_source: Optional[str] = Header(None),
):
    # Sync def: chunking + embedding run in the threadpool, so the event
    # loop (and every other request) is not blocked during import.
    source = "auto" if x_examradar_source == "auto" else "real"
    content = file.file.read()

    try:
        return ingest_bytes(content, file.filename or "unknown", course_id,
                            doc_kind, source)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/documents")
def list_documents(course_id: str):
    return get_documents(course_id)
