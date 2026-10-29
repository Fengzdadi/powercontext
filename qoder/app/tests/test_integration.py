"""Integration tests requiring a running seekdb instance.

Run with: EXAMRADAR_IT=1 uv run pytest -m integration
"""
import os
import json
import hashlib
import pytest

from examradar.config import get_settings
from examradar.seekdb import (
    ensure_tables, check_connection, get_connection,
    insert_document, insert_chunk, find_document_by_sha256,
    hybrid_search, insert_usage_event, get_documents,
)
from examradar.embedding import get_embedding_model
from examradar.chunker import chunk_file
from examradar.cleaner import clean_extracted_text, normalize_text


pytestmark = pytest.mark.integration

COURSE = "db101_it"


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if not os.environ.get("EXAMRADAR_IT"):
        pytest.skip("EXAMRADAR_IT not set")
    assert check_connection(), "Cannot connect to seekdb"
    ensure_tables()
    yield
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for table in ("chunks", "documents", "usage_events"):
                cur.execute(f"DELETE FROM {table} WHERE course_id = %s", (COURSE,))
    finally:
        conn.close()


def test_connection():
    assert check_connection()


def test_insert_and_find_document():
    sha = hashlib.sha256(b"test_content_it").hexdigest()
    doc_id = insert_document(COURSE, "test_it.md", "notes", "md", sha, 1)
    assert doc_id > 0
    found = find_document_by_sha256(sha)
    assert found is not None
    assert found["name"] == "test_it.md"


def test_chunk_and_import_markdown():
    import pathlib
    md_path = pathlib.Path(__file__).resolve().parents[2] / "samples" / "course-db" / "notes" / "03-索引与B+树.md"
    if not md_path.exists():
        pytest.skip("Sample file not found")
    result = chunk_file(str(md_path), "notes")
    assert len(result.chunks) >= 3
    for c in result.chunks:
        assert c.content.strip()
        assert c.heading is not None


def test_chunk_exam_pdf():
    import pathlib
    exam_path = pathlib.Path(__file__).resolve().parents[2] / "samples" / "course-db" / "exams" / "2025-2026-1-期末试卷A.pdf"
    if not exam_path.exists():
        pytest.skip("Exam PDF not found")
    result = chunk_file(str(exam_path), "exam")
    assert len(result.chunks) == 11, f"Expected 11 questions, got {len(result.chunks)}"
    total_points = sum(c.points for c in result.chunks if c.points)
    assert total_points == 100.0, f"Expected 100 points, got {total_points}"


def test_embedding_model():
    model = get_embedding_model()
    vec = model.embed_one("数据库系统")
    s = get_settings()
    assert len(vec) == s.embedding_dim


def test_batch_embedding():
    model = get_embedding_model()
    texts = ["B+树索引", "事务隔离级别", "SQL查询优化"]
    vecs = model.embed(texts)
    assert len(vecs) == 3
    assert all(len(v) == 512 for v in vecs)


def test_full_import_and_search():
    """End-to-end: import a markdown file, then search it."""
    import pathlib
    md_path = pathlib.Path(__file__).resolve().parents[2] / "samples" / "course-db" / "notes" / "03-索引与B+树.md"
    if not md_path.exists():
        pytest.skip("Sample file not found")

    content = md_path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()

    existing = find_document_by_sha256(sha)
    if existing and existing["course_id"] == COURSE:
        doc_id = existing["id"]
    else:
        result = chunk_file(str(md_path), "notes")
        doc_id = insert_document(COURSE, md_path.name, "notes", "md", sha, len(result.chunks))
        model = get_embedding_model()
        texts = [c.content for c in result.chunks]
        embeddings = model.embed(texts)
        for i, (chunk, emb) in enumerate(zip(result.chunks, embeddings)):
            insert_chunk(
                document_id=doc_id, course_id=COURSE, doc_kind="notes",
                content=chunk.content, heading=chunk.heading, page=chunk.page,
                question_no=chunk.question_no, points=chunk.points,
                chunk_index=chunk.chunk_index, embedding=emb,
            )

    model = get_embedding_model()
    query_vec = model.embed_one("B+树插入时结点分裂")
    hits, search_json, actual_sql = hybrid_search(
        query_text="B+树插入时结点分裂",
        query_vector=query_vec,
        course_id=COURSE,
        doc_kinds=["notes"],
        top_k=5,
    )
    assert len(hits) > 0, "No search results"
    assert actual_sql, "GET_SQL returned empty"

    first = hits[0]
    heading = first.get("heading", "") or ""
    assert "3.3" in heading, f"Expected 3.3 in heading, got: {heading}"

    kw_score = first.get("_keyword_score")
    assert kw_score is not None and kw_score > 0, f"keyword_score should be > 0, got {kw_score}"


def test_search_json_and_sql():
    """Verify search JSON is well-formed and GET_SQL returns valid SQL."""
    model = get_embedding_model()
    query_vec = model.embed_one("测试查询")
    hits, search_json, actual_sql = hybrid_search(
        query_text="测试查询",
        query_vector=query_vec,
        course_id=COURSE,
        doc_kinds=["notes"],
        top_k=3,
    )
    parsed = json.loads(search_json) if isinstance(search_json, str) else search_json
    assert "query" in parsed
    assert "knn" in parsed
    assert len(actual_sql) > 0


def test_usage_event_recorded():
    eid = insert_usage_event(COURSE, "auto", "search", {"query": "test", "results": 0})
    assert eid > 0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usage_events WHERE id = %s", (eid,))
            row = cur.fetchone()
            assert row is not None
            assert row["source"] == "auto"
            assert row["event"] == "search"
    finally:
        conn.close()


def test_pdf_text_cleaning():
    """Verify that PDF extraction produces normal CJK characters."""
    import pathlib
    slides_path = pathlib.Path(__file__).resolve().parents[2] / "samples" / "course-db" / "slides" / "第7讲-故障恢复.pdf"
    if not slides_path.exists():
        pytest.skip("Slides PDF not found")

    import fitz
    doc = fitz.open(str(slides_path))
    page7_text = doc[6].get_text("text")
    doc.close()

    cleaned = clean_extracted_text(page7_text)
    assert "脏页表" in cleaned or "脏页表" in normalize_text(page7_text), \
        f"Expected '脏页表' in cleaned text. Got: {cleaned[:200]}"

    from examradar.cleaner import validate_cjk_chars
    suspicious = validate_cjk_chars(cleaned)
    assert len(suspicious) == 0, f"Suspicious chars after cleaning: {suspicious[:3]}"
