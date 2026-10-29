"""Integration tests requiring a running seekdb instance.

Run with: export EXAMRADAR_IT=1 && uv run pytest -m integration

conftest.py switches SEEKDB_DATABASE to examradar_test (or
SEEKDB_TEST_DATABASE) when EXAMRADAR_IT is set, so tests never touch the
dev database.
"""
import os
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
from examradar.cleaner import validate_cjk_chars


pytestmark = pytest.mark.integration

COURSE = "db101"
COURSE_B = "db101_it_b"

SAMPLES = pathlib.Path(__file__).resolve().parents[2] / "samples" / "course-db"

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

# Design truth from samples/course-db/README.md — every judgment asserted.
DESIGN_LEVELS = {
    "t01": "missing", "t02": "thin", "t03": "covered", "t04": "missing",
    "t05": "missing", "t06": "covered", "t07": "covered", "t08": "thin",
    "t09": "covered", "t10": "covered",
}
DESIGN_ASSIGNMENTS = {
    1: "t01", 2: "t02", 3: "t03", 4: "t04", 5: "t04", 6: "t05",
    7: "t06", 8: "t07", 9: "t08", 10: "t09", 11: "t10",
}


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
    s = get_settings()
    test_db = s.seekdb_database
    expected = os.environ.get("SEEKDB_TEST_DATABASE", "examradar_test")
    assert test_db == expected, (
        f"Integration tests must use the test database {expected!r}, "
        f"got {test_db!r}")
    ensure_tables()
    assert check_connection(), "Cannot connect to seekdb"
    _clean_test_db()
    for f, kind in _sample_files():
        result = ingest_bytes(f.read_bytes(), f.name, COURSE, kind, source="auto")
        assert not result["skipped"], f"{f.name} should be imported fresh"
    yield
    delete_course(COURSE_B, include_usage=True)


def _clean_test_db():
    """Remove all data from the test database. Only touches the test DB."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT course_id FROM documents")
            course_ids = [r["course_id"] for r in cur.fetchall()]
    finally:
        conn.close()
    for cid in course_ids:
        delete_course(cid, include_usage=True)


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
    delete_course(COURSE_B, include_usage=True)


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


def test_chunk_exam_pdf_joins_hard_wraps():
    result = chunk_file(str(SAMPLES / "exams" / "2025-2026-1-期末试卷A.pdf"), "exam")
    q1 = next(c for c in result.chunks if c.question_no == 1)
    assert "写出" in q1.content, f"'写\\n出' should be joined: {q1.content[:80]!r}"
    q10 = next(c for c in result.chunks if c.question_no == 10)
    assert "原则" in q10.content, f"'原\\n则' should be joined: {q10.content[:80]!r}"


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


def test_chunk_paper_pdf_keeps_section_headings():
    """Numbered section headings must not be glued into body paragraphs."""
    result = chunk_file(str(SAMPLES / "papers" / "two-phase-commit-primer.pdf"), "paper")
    joined = "\n".join(c.content for c in result.chunks)
    for heading in ("1. The Atomic Commitment Problem", "2. Roles",
                    "6. Why 2PC Is a Blocking Protocol"):
        assert "\n" + heading + "\n" in "\n" + joined + "\n", \
            f"{heading!r} should stay on its own line"
    assert "Commitment Problem A distributed transaction" not in joined


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
    import json
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


@pytest.fixture(scope="module")
def coverage_result():
    from examradar.coverage import analyze
    syllabus_text = (SAMPLES / "syllabus.txt").read_text(encoding="utf-8")
    return analyze(COURSE, syllabus_text, source="auto")


def test_coverage_levels_match_design_truth(coverage_result):
    """All 10 topic judgments must match the design truth in the README."""
    levels = {i["topic_id"]: i["coverage_level"] for i in coverage_result["items"]}
    assert levels == DESIGN_LEVELS, f"coverage levels mismatch: {levels}"


def test_coverage_scores_consistent_with_levels(coverage_result):
    for item in coverage_result["items"]:
        score, level = item["coverage_score"], item["coverage_level"]
        if level == "missing":
            assert score == 0.0
        elif level == "thin":
            assert 0.0 < score < 0.5, (item["topic_id"], score)
        else:
            assert score >= 0.5, (item["topic_id"], score)


def test_exam_assignment_matches_design_truth(coverage_result):
    """All 11 questions must be assigned to the design-truth topics."""
    assigned = {}
    for item in coverage_result["items"]:
        for q in item["exam_questions"]:
            assigned[q["question_no"]] = item["topic_id"]
    assert assigned == DESIGN_ASSIGNMENTS, f"assignment mismatch: {assigned}"
    # term-based assignments must report their matched terms
    for item in coverage_result["items"]:
        for q in item["exam_questions"]:
            assert q["matched_terms"], \
                f"Q{q['question_no']} assigned to {item['topic_id']} without term evidence"


def test_blind_spot_ranking(coverage_result):
    """t04 must be the top blind spot: 25 points, coverage 0."""
    items = coverage_result["items"]
    assert items[0]["topic_id"] == "t04"
    assert items[0]["exam_weight"] == 25.0
    assert items[0]["coverage_score"] == 0.0
    assert items[0]["blind_spot_score"] == 25.0


def test_coverage_reasons_are_explained(coverage_result):
    """Every reason must name the found/missing terms and the quantities."""
    by_id = {i["topic_id"]: i for i in coverage_result["items"]}
    # missing topic: names the terms that were not found
    assert "关系代数" in by_id["t01"]["reason"]
    assert "0/2" in by_id["t01"]["reason"]
    # covered topic: reports support chars above the threshold
    assert "支撑段落" in by_id["t03"]["reason"]
    assert "高出 covered 阈值" in by_id["t03"]["reason"]
    # thin topics say which dimension fell short
    assert "thin" in by_id["t02"]["reason"]
    assert "thin" in by_id["t08"]["reason"]


def test_coverage_latest(coverage_result):
    """get_latest returns the most recent analysis with full detail."""
    from examradar.coverage import get_latest
    latest = get_latest(COURSE)
    assert latest is not None
    assert latest["course_id"] == COURSE
    assert len(latest["items"]) == 10
    item = next(i for i in latest["items"] if i["topic_id"] == "t04")
    assert item["coverage_level"] == "missing"
    assert item["coverage_score"] == 0.0
    t10 = next(i for i in latest["items"] if i["topic_id"] == "t10")
    assert t10["exam_questions"][0]["content"], "question text must persist"
    assert t10["exam_questions"][0]["matched_terms"]
