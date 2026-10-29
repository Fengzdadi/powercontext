"""Integration tests requiring a running seekdb instance.

Run with: export EXAMRADAR_IT=1 && uv run pytest -m integration
"""
import os
import json
import hashlib
import pathlib

import pytest

from examradar.config import get_settings
from examradar.seekdb import (
    ensure_tables, check_connection, get_connection,
    import_document, find_document_by_sha256, delete_course,
    hybrid_search, insert_usage_event, get_documents,
)
from examradar.ingest import ingest_bytes
from examradar.embedding import get_embedding_model
from examradar.chunker import chunk_file
from examradar.cleaner import clean_extracted_text, validate_cjk_chars


pytestmark = pytest.mark.integration

# The acceptance queries are calibrated against a corpus containing exactly
# the sample course materials: BM25 IDF is computed over the whole table,
# so extra documents in other courses shift keyword scores. The suite
# therefore wipes all courses first and imports only the samples.
COURSE = "db101"
COURSE_B = "db101_it_b"

SAMPLES = pathlib.Path(__file__).resolve().parents[2] / "samples" / "course-db"

# The 6 acceptance queries: (query, doc_kinds, expectation on first hit)
ACCEPTANCE_QUERIES = [
    ("脏页表", ["slides"], lambda h: h.get("page") == 7),
    ("先写日志原则", ["slides"], lambda h: h.get("page") == 4),
    ("B+树插入时结点分裂", ["notes"],
     lambda h: "3.3" in (h.get("heading") or "")),
    ("coordinator crash blocking", ["paper"], lambda h: h.get("page") == 2),
    ("两阶段锁能不能避免死锁", ["notes"],
     lambda h: "5.3" in (h.get("heading") or "")),
    ("函数依赖 候选码", ["notes", "slides", "paper", "exam"],
     lambda h: h.get("question_no") == 4),
]


def _sample_files():
    files = []
    for sub, kind in (("notes", "notes"), ("slides", "slides"),
                      ("exams", "exam"), ("papers", "paper")):
        d = SAMPLES / sub
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in (".md", ".txt", ".pdf"):
                    files.append((f, kind))
    return files


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if not os.environ.get("EXAMRADAR_IT"):
        pytest.skip("EXAMRADAR_IT not set")
    assert check_connection(), "Cannot connect to seekdb"
    ensure_tables()
    _delete_all_courses()
    for f, kind in _sample_files():
        result = ingest_bytes(f.read_bytes(), f.name, COURSE, kind)
        assert not result["skipped"], f"{f.name} should be imported fresh"
    # leave COURSE data in place: this is the acceptance environment
    # (scripts/load_sample.sh afterwards reports all files as skipped)
    yield
    delete_course(COURSE_B)


def _delete_all_courses():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT course_id FROM documents")
            course_ids = [r["course_id"] for r in cur.fetchall()]
    finally:
        conn.close()
    for cid in course_ids:
        delete_course(cid)


def test_connection():
    assert check_connection()


def test_import_is_idempotent():
    f = SAMPLES / "notes" / "03-索引与B+树.md"
    result = ingest_bytes(f.read_bytes(), f.name, COURSE, "notes")
    assert result["skipped"] is True
    assert result["chunk_count"] > 0


def test_same_file_importable_into_other_course():
    f = SAMPLES / "notes" / "03-索引与B+树.md"
    result = ingest_bytes(f.read_bytes(), f.name, COURSE_B, "notes")
    assert result["skipped"] is False
    assert result["chunk_count"] > 0
    # restore the corpus: extra documents shift BM25 IDF for later tests
    delete_course(COURSE_B)


def test_find_document_by_sha256_scoped_to_course():
    f = SAMPLES / "notes" / "03-索引与B+树.md"
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    assert find_document_by_sha256(sha, COURSE) is not None
    assert find_document_by_sha256(sha, COURSE + "_nope") is None


def test_created_at_is_utc_isoformat():
    docs = get_documents(COURSE)
    assert docs
    for d in docs:
        assert d["created_at"].endswith("+00:00"), d["created_at"]


def test_import_document_rollback_on_failure():
    """A failing chunk insert must roll back the whole document."""
    sha = hashlib.sha256(b"rollback_test_payload").hexdigest()
    chunks = [
        {"content": "ok", "chunk_index": 0, "embedding": [0.1] * 512},
        # >64KB violates TEXT limit -> insert error mid-batch
        {"content": "x" * 200_000, "chunk_index": 1, "embedding": [0.1] * 512},
    ]
    with pytest.raises(Exception):
        import_document(COURSE, "rollback.md", "notes", "md", sha, chunks)
    assert find_document_by_sha256(sha, COURSE) is None


def test_chunk_exam_pdf():
    result = chunk_file(str(SAMPLES / "exams" / "2025-2026-1-期末试卷A.pdf"), "exam")
    assert len(result.chunks) == 11, f"Expected 11 questions, got {len(result.chunks)}"
    total_points = sum(c.points for c in result.chunks if c.points)
    assert total_points == 100.0, f"Expected 100 points, got {total_points}"
    for c in result.chunks:
        assert "（" in c.content, "full-width punctuation should be preserved"


def test_chunk_slides_pdf():
    result = chunk_file(str(SAMPLES / "slides" / "第7讲-故障恢复.pdf"), "slides")
    assert len(result.chunks) == 9
    for c in result.chunks:
        lines = c.content.split("\n")
        assert c.heading == lines[0], "heading must be the page's first line"
        # no standalone footer page-number line
        assert not lines[-1].strip().isdigit(), f"footer page number left: {lines[-1]!r}"
        assert validate_cjk_chars(c.content) == []
    headings = {c.page: c.heading for c in result.chunks}
    assert headings[4] == "先写日志原则（WAL）"
    assert headings[7] == "ARIES 恢复算法的三个阶段"


def test_embedding_model():
    model = get_embedding_model()
    vec = model.embed_one("数据库系统")
    assert len(vec) == get_settings().embedding_dim


def test_query_embedding_instruction_is_configurable():
    """With the default empty instruction, query and plain embeddings are
    identical; the BGE instruction is opt-in via EMBEDDING_QUERY_INSTRUCTION
    (measured to hurt short Chinese term queries — see DEVLOG session 03)."""
    model = get_embedding_model()
    assert model.embed_one("数据库系统", is_query=True) == model.embed_one("数据库系统")


def test_hybrid_search_sql_matches_heading():
    model = get_embedding_model()
    query_vec = model.embed_one("测试查询", is_query=True)
    hits, search_json, actual_sql = hybrid_search(
        query_text="测试查询", query_vector=query_vec,
        course_id=COURSE, doc_kinds=["notes"], top_k=3,
    )
    parsed = json.loads(search_json) if isinstance(search_json, str) else search_json
    assert "query" in parsed and "knn" in parsed
    assert "match(`heading`)" in actual_sql, \
        f"GET_SQL should score the heading fulltext index: {actual_sql[:400]}"


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


@pytest.mark.parametrize("query,doc_kinds,expect", ACCEPTANCE_QUERIES)
def test_acceptance_query_first_hit(query, doc_kinds, expect):
    """Each acceptance query's first hit must be the expected source,
    with a non-null keyword score."""
    model = get_embedding_model()
    query_vec = model.embed_one(query, is_query=True)
    hits, _, _ = hybrid_search(
        query_text=query, query_vector=query_vec,
        course_id=COURSE, doc_kinds=doc_kinds, top_k=3,
    )
    assert hits, f"no results for: {query}"
    first = hits[0]
    assert expect(first), (
        f"first hit for {query!r} unexpected: "
        f"page={first.get('page')} heading={first.get('heading')!r} "
        f"question_no={first.get('question_no')}"
    )
    assert first.get("_keyword_score") is not None, \
        f"_keyword_score is None for first hit of {query!r}"
