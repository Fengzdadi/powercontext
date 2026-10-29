"""Shared document ingestion pipeline: validate, chunk, embed, atomic import."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .chunker import chunk_file, ChunkResult
from .embedding import get_embedding_model
from .seekdb import (
    find_document_by_sha256, import_document, insert_usage_event,
)

ALLOWED_DOC_KINDS = {"notes", "slides", "paper", "exam"}
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB

_BATCH_SIZE = 16


class ValidationError(ValueError):
    pass


def validate_input(filename: str, doc_kind: str, content: bytes) -> None:
    if doc_kind not in ALLOWED_DOC_KINDS:
        raise ValidationError(f"doc_kind 只允许 {'/'.join(sorted(ALLOWED_DOC_KINDS))}，收到: {doc_kind}")
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"文件只支持 {'/'.join(sorted(ALLOWED_EXTENSIONS))}，收到: {filename}")
    if len(content) > MAX_FILE_SIZE:
        raise ValidationError(f"文件超过 30 MB 上限（{len(content)} 字节）")


def ingest_bytes(
    content: bytes,
    filename: str,
    course_id: str,
    doc_kind: str,
    source: str = "real",
) -> dict:
    """Ingest raw file content. Returns {document_id, chunk_count, skipped}.

    Everything (chunking, embedding) happens before any DB write; the DB
    write itself is a single transaction, so a failure never leaves a
    half-imported document behind.
    """
    validate_input(filename, doc_kind, content)
    sha = hashlib.sha256(content).hexdigest()

    existing = find_document_by_sha256(sha, course_id)
    if existing:
        return {
            "document_id": existing["id"],
            "chunk_count": existing["chunk_count"],
            "skipped": True,
            "message": "文件已存在（同课程内内容相同）",
        }

    suffix = Path(filename).suffix.lower()
    tmp = Path(f"/tmp/examradar_{sha}{suffix}")
    tmp.write_bytes(content)
    try:
        result: ChunkResult = chunk_file(str(tmp), doc_kind)
    finally:
        tmp.unlink(missing_ok=True)

    if not result.chunks:
        raise ValidationError("文件解析后没有可用内容")

    model = get_embedding_model()
    texts = [c.content for c in result.chunks]
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        embeddings.extend(model.embed(texts[i:i + _BATCH_SIZE]))

    rows = [
        {
            "content": c.content,
            "heading": c.heading,
            "page": c.page,
            "question_no": c.question_no,
            "points": c.points,
            "chunk_index": c.chunk_index,
            "embedding": emb,
        }
        for c, emb in zip(result.chunks, embeddings)
    ]

    file_type = result.file_type or suffix.lstrip(".")
    doc_id = import_document(course_id, filename, doc_kind, file_type, sha, rows)

    insert_usage_event(course_id, source, "import", {
        "document_id": doc_id, "doc_kind": doc_kind,
        "chunk_count": len(rows), "filename": filename,
    })
    return {
        "document_id": doc_id,
        "chunk_count": len(rows),
        "skipped": False,
    }
