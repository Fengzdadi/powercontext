"""Document import endpoint."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Header

from ..seekdb import (
    insert_document, insert_chunk, find_document_by_sha256,
    insert_usage_event, get_documents,
)
from ..chunker import chunk_file
from ..embedding import get_embedding_model

router = APIRouter()

_BATCH_SIZE = 16


@router.post("/api/documents")
async def upload_document(
    file: UploadFile = File(...),
    course_id: str = Form(...),
    doc_kind: str = Form(...),
    x_examradar_source: Optional[str] = Header(None),
):
    source = "auto" if x_examradar_source == "auto" else "real"
    content = await file.read()
    sha = hashlib.sha256(content).hexdigest()

    existing = find_document_by_sha256(sha)
    if existing:
        return {
            "document_id": existing["id"],
            "chunk_count": existing["chunk_count"],
            "skipped": True,
            "message": "文件已存在（内容相同）",
        }

    suffix = Path(file.filename or "file").suffix.lower()
    tmp = Path(f"/tmp/examradar_{sha}{suffix}")
    tmp.write_bytes(content)

    try:
        result = chunk_file(str(tmp), doc_kind)
    finally:
        tmp.unlink(missing_ok=True)

    file_type = result.file_type or suffix.lstrip(".")
    doc_id = insert_document(course_id, file.filename or "unknown", doc_kind,
                             file_type, sha, len(result.chunks))

    model = get_embedding_model()
    texts = [c.content for c in result.chunks]

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start:batch_start + _BATCH_SIZE]
        embeddings = model.embed(batch)
        for i, emb in enumerate(embeddings):
            ci = batch_start + i
            chunk = result.chunks[ci]
            insert_chunk(
                document_id=doc_id,
                course_id=course_id,
                doc_kind=doc_kind,
                content=chunk.content,
                heading=chunk.heading,
                page=chunk.page,
                question_no=chunk.question_no,
                points=chunk.points,
                chunk_index=chunk.chunk_index,
                embedding=emb,
            )

    insert_usage_event(course_id, source, "import", {
        "document_id": doc_id,
        "doc_kind": doc_kind,
        "chunk_count": len(result.chunks),
        "filename": file.filename,
    })

    return {
        "document_id": doc_id,
        "chunk_count": len(result.chunks),
        "skipped": False,
    }


@router.get("/api/documents")
def list_documents(course_id: str):
    return get_documents(course_id)
