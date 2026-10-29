"""seekdb client: connection, DDL, atomic import, hybrid search."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pymysql

from .config import get_settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_connection(database: Optional[str] = None):
    s = get_settings()
    return pymysql.connect(
        host=s.seekdb_host,
        port=s.seekdb_port,
        user=s.seekdb_user,
        password=s.seekdb_password,
        database=database or s.seekdb_database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def ensure_database():
    """Create the database if it doesn't exist."""
    s = get_settings()
    db = s.seekdb_database
    conn = pymysql.connect(
        host=s.seekdb_host,
        port=s.seekdb_port,
        user=s.seekdb_user,
        password=s.seekdb_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db}` "
                f"DEFAULT CHARACTER SET utf8mb4"
            )
    finally:
        conn.close()


def ensure_tables():
    """Idempotent: create tables if they don't exist."""
    ensure_database()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
                    course_id   VARCHAR(64) NOT NULL,
                    name        VARCHAR(256) NOT NULL,
                    doc_kind    VARCHAR(16) NOT NULL,
                    file_type   VARCHAR(8),
                    sha256      CHAR(64),
                    chunk_count INT DEFAULT 0,
                    created_at  DATETIME,
                    INDEX idx_course (course_id),
                    UNIQUE INDEX idx_course_sha (course_id, sha256)
                ) ORGANIZATION HEAP
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
                    document_id BIGINT NOT NULL,
                    course_id   VARCHAR(64) NOT NULL,
                    doc_kind    VARCHAR(16) NOT NULL,
                    content     TEXT NOT NULL,
                    heading     TEXT,
                    page        INT,
                    question_no INT,
                    points      DECIMAL(5,1),
                    chunk_index INT,
                    embedding   VECTOR(512),
                    VECTOR INDEX idx_emb (embedding) WITH (distance=cosine, type=hnsw, sync_mode=immediate),
                    FULLTEXT INDEX ft_content (content) WITH PARSER ik,
                    FULLTEXT INDEX ft_heading (heading) WITH PARSER ik,
                    INDEX idx_course_kind (course_id, doc_kind)
                ) ORGANIZATION HEAP
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usage_events (
                    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
                    session_id  VARCHAR(64),
                    course_id   VARCHAR(64),
                    source      VARCHAR(16) NOT NULL,
                    event       VARCHAR(32) NOT NULL,
                    payload     TEXT,
                    created_at  DATETIME,
                    INDEX idx_session (session_id),
                    INDEX idx_course_source (course_id, source)
                ) ORGANIZATION HEAP
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coverage_runs (
                    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
                    course_id   VARCHAR(64) NOT NULL,
                    source      VARCHAR(16) NOT NULL DEFAULT 'real',
                    topics_json TEXT NOT NULL,
                    config_json TEXT,
                    created_at  DATETIME,
                    INDEX idx_course (course_id)
                ) ORGANIZATION HEAP
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coverage_items (
                    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
                    run_id          BIGINT NOT NULL,
                    course_id       VARCHAR(64) NOT NULL,
                    topic_id        VARCHAR(16) NOT NULL,
                    topic_name      VARCHAR(256) NOT NULL,
                    keywords_json   TEXT,
                    terms_json      TEXT,
                    coverage_level  VARCHAR(16),
                    coverage_score  DECIMAL(6,4),
                    support_chunks  INT,
                    support_chars   INT,
                    best_sem_score  DECIMAL(6,4),
                    best_kw_score   DECIMAL(10,4),
                    best_content    TEXT,
                    best_heading    TEXT,
                    best_page       INT,
                    best_doc_name   VARCHAR(256),
                    exam_weight     DECIMAL(6,1) DEFAULT 0,
                    exam_qs_json    TEXT,
                    blind_spot_score DECIMAL(10,4),
                    reason          TEXT,
                    INDEX idx_run (run_id),
                    INDEX idx_course_topic (course_id, topic_id)
                ) ORGANIZATION HEAP
            """)
            # existing installations: add columns introduced in session 05
            _ensure_columns(conn, "coverage_items", {
                "terms_json": "terms_json TEXT",
                "support_chunks": "support_chunks INT",
                "support_chars": "support_chars INT",
            })
    finally:
        conn.close()


def _ensure_columns(conn, table: str, columns: dict[str, str]):
    """Idempotently add missing columns (MySQL/seekdb has no ADD COLUMN IF
    NOT EXISTS)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (table,),
        )
        existing = {r["COLUMN_NAME"] for r in cur.fetchall()}
        for col, ddl in columns.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def import_document(
    course_id: str, name: str, doc_kind: str, file_type: str,
    sha256: str, chunks: list[dict],
) -> int:
    """Atomically insert a document row and all its chunks.

    `chunks` items: {content, heading, page, question_no, points,
    chunk_index, embedding}. All embedding is assumed done before calling.
    On failure the transaction is rolled back — no partial document remains.
    Returns the new document id.
    """
    now = _utc_now()
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (course_id, name, doc_kind, file_type, sha256, chunk_count, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (course_id, name, doc_kind, file_type, sha256, len(chunks), now),
            )
            doc_id = cur.lastrowid
            rows = []
            for c in chunks:
                emb_str = "[" + ",".join(f"{v:.8f}" for v in c["embedding"]) + "]"
                rows.append((
                    doc_id, course_id, doc_kind, c["content"], c.get("heading"),
                    c.get("page"), c.get("question_no"), c.get("points"),
                    c.get("chunk_index"), emb_str,
                ))
            cur.executemany(
                "INSERT INTO chunks (document_id, course_id, doc_kind, content, heading, "
                "page, question_no, points, chunk_index, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                rows,
            )
        conn.commit()
        return doc_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def find_document_by_sha256(sha256: str, course_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM documents WHERE sha256 = %s AND course_id = %s",
                (sha256, course_id),
            )
            return cur.fetchone()
    finally:
        conn.close()


def delete_course(course_id: str, include_usage: bool = False) -> dict:
    """Delete a course's materials (documents, chunks) and coverage analyses.

    usage_events are the usage log and survive a re-import by default; pass
    include_usage=True to delete them as well.
    """
    tables = ["chunks", "documents", "coverage_items", "coverage_runs"]
    if include_usage:
        tables.append("usage_events")
    counts = {}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(f"DELETE FROM {table} WHERE course_id = %s", (course_id,))
                counts[table] = cur.rowcount
    finally:
        conn.close()
    return counts


def get_coverage_chunks(course_id: str, doc_kinds: list[str]) -> list[dict]:
    """All material chunks (with document name) for coverage analysis."""
    kinds = ",".join("'" + k.replace("'", "") + "'" for k in doc_kinds)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.heading, c.page, c.content, d.name AS doc_name "
                "FROM chunks c JOIN documents d ON c.document_id = d.id "
                f"WHERE c.course_id = %s AND c.doc_kind IN ({kinds}) "
                "ORDER BY c.id",
                (course_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_exam_chunks(course_id: str) -> list[dict]:
    """Exam question chunks with embeddings, ordered by question number."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, question_no, points, content, embedding "
                "FROM chunks WHERE course_id = %s AND doc_kind = 'exam' "
                "AND question_no IS NOT NULL ORDER BY question_no",
                (course_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def insert_usage_event(course_id: str, source: str, event: str, payload: dict,
                       session_id: Optional[str] = None) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_events (session_id, course_id, source, event, payload, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (session_id, course_id, source, event,
                 json.dumps(payload, ensure_ascii=False), _utc_now()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def _escape_search_text(text: str) -> str:
    """Remove characters that would break the JSON/SQL in DBMS_HYBRID_SEARCH."""
    text = text.replace("\\", "")
    text = text.replace('"', "")
    text = text.replace("'", "")
    return text.strip()


# Full-text fields searched for every query. The heading field carries no
# explicit ^N boost: BM25 length normalization already gives a heading hit a
# ~4x higher score than a body hit (short field), and empirical tuning on
# the acceptance queries showed heading^2 or higher over-weights headings
# and flips legitimate winners (see DEVLOG session 03).
MULTI_MATCH_FIELDS = ["content", "heading"]


def build_search_json(
    query_text: str,
    query_vector: list[float],
    course_id: str,
    doc_kinds: list[str],
    top_k: int = 10,
) -> dict:
    """Build the JSON for DBMS_HYBRID_SEARCH.SEARCH."""
    safe_text = _escape_search_text(query_text)
    return {
        "query": {
            "bool": {
                "must": [{
                    "multi_match": {
                        "query": safe_text,
                        "fields": MULTI_MATCH_FIELDS,
                    }
                }],
                "filter": [
                    {"term": {"course_id": course_id}},
                    {"terms": {"doc_kind": doc_kinds}},
                ],
            }
        },
        "knn": {
            "field": "embedding",
            "k": max(top_k * 2, 20),
            "query_vector": query_vector,
            "filter": [
                {"term": {"course_id": course_id}},
                {"terms": {"doc_kind": doc_kinds}},
            ],
        },
        "rank": {"rrf": {}},
        "_source": [
            "id", "document_id", "content", "heading", "page",
            "question_no", "points",
            "_keyword_score", "_semantic_score", "_keyword_rank", "_semantic_rank",
        ],
        "size": top_k,
    }


def hybrid_search(
    query_text: str,
    query_vector: list[float],
    course_id: str,
    doc_kinds: list[str],
    top_k: int = 10,
) -> tuple[list[dict], str, str]:
    """Execute hybrid search. Returns (hits, search_json, actual_sql)."""
    search_json = build_search_json(query_text, query_vector, course_id, doc_kinds, top_k)
    json_str = json.dumps(search_json, ensure_ascii=False)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DBMS_HYBRID_SEARCH.GET_SQL('chunks', %s) AS sql_text",
                (json_str,),
            )
            row = cur.fetchone()
            actual_sql = row["sql_text"] if row else ""

            cur.execute(
                "SELECT DBMS_HYBRID_SEARCH.SEARCH('chunks', %s) AS hits",
                (json_str,),
            )
            row = cur.fetchone()
            if row is None or row["hits"] is None:
                return [], json_str, actual_sql

            hits_raw = row["hits"]
            if isinstance(hits_raw, str):
                hits = json.loads(hits_raw)
            else:
                hits = hits_raw
            return _break_rrf_ties(hits), json_str, actual_sql
    finally:
        conn.close()


def _break_rrf_ties(hits: list[dict]) -> list[dict]:
    """RRF is symmetric: ranks (1,2) and (2,1) produce identical _score, and
    seekdb's secondary sort is by primary key, which is arbitrary. When RRF
    scores tie exactly, break the tie by the raw keyword score, then the raw
    semantic score — BM25 separates near-identical candidates better than
    cosine similarity does for short queries."""
    def key(h: dict):
        kw = h.get("_keyword_score")
        sem = h.get("_semantic_score")
        return (
            -(h.get("_score") or 0.0),
            -(kw if kw is not None else float("-inf")),
            -(sem if sem is not None else float("-inf")),
        )
    return sorted(hits, key=key)


def get_document_names(course_id: str) -> dict[int, str]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM documents WHERE course_id = %s", (course_id,))
            return {r["id"]: r["name"] for r in cur.fetchall()}
    finally:
        conn.close()


def get_documents(course_id: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, doc_kind, file_type, chunk_count, created_at "
                "FROM documents WHERE course_id = %s ORDER BY created_at, id",
                (course_id,),
            )
            rows = cur.fetchall()
            for r in rows:
                if isinstance(r.get("created_at"), datetime):
                    # stored as naive UTC; return tz-aware ISO string
                    r["created_at"] = (
                        r["created_at"].replace(tzinfo=timezone.utc).isoformat()
                    )
            return rows
    finally:
        conn.close()


def check_connection() -> bool:
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
        conn.close()
        return True
    except Exception:
        return False


def save_coverage_run(
    course_id: str, source: str, topics_json: str, config_json: str,
    items: list[dict],
) -> int:
    """Save a coverage analysis run and its items. Returns the run id."""
    now = _utc_now()
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO coverage_runs (course_id, source, topics_json, config_json, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (course_id, source, topics_json, config_json, now),
            )
            run_id = cur.lastrowid
            for item in items:
                cur.execute(
                    "INSERT INTO coverage_items (run_id, course_id, topic_id, topic_name, "
                    "keywords_json, terms_json, coverage_level, coverage_score, "
                    "support_chunks, support_chars, best_sem_score, "
                    "best_kw_score, best_content, best_heading, best_page, best_doc_name, "
                    "exam_weight, exam_qs_json, blind_spot_score, reason) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        run_id, course_id, item["topic_id"], item["topic_name"],
                        item.get("keywords_json"), item.get("terms_json"),
                        item.get("coverage_level"), item.get("coverage_score"),
                        item.get("support_chunks"), item.get("support_chars"),
                        item.get("best_sem_score"),
                        item.get("best_kw_score"), item.get("best_content"),
                        item.get("best_heading"), item.get("best_page"),
                        item.get("best_doc_name"), item.get("exam_weight", 0),
                        item.get("exam_qs_json"), item.get("blind_spot_score"),
                        item.get("reason"),
                    ),
                )
        conn.commit()
        return run_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_latest_coverage(course_id: str) -> Optional[dict]:
    """Get the latest coverage run for a course, including items."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM coverage_runs WHERE course_id = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (course_id,),
            )
            run = cur.fetchone()
            if not run:
                return None
            if isinstance(run.get("created_at"), datetime):
                run["created_at"] = run["created_at"].replace(tzinfo=timezone.utc).isoformat()
            cur.execute(
                "SELECT * FROM coverage_items WHERE run_id = %s ORDER BY topic_id",
                (run["id"],),
            )
            items = cur.fetchall()
            for item in items:
                for key in ("coverage_score", "best_sem_score", "best_kw_score",
                            "blind_spot_score"):
                    v = item.get(key)
                    if v is not None:
                        item[key] = float(v)
                v = item.get("exam_weight")
                if v is not None:
                    item["exam_weight"] = float(v)
            run["items"] = items
            return run
    finally:
        conn.close()


def get_usage_events(
    course_id: str, source: str = "real",
    limit: int = 1000,
) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM usage_events WHERE course_id = %s AND source = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (course_id, source, limit),
            )
            rows = cur.fetchall()
            for r in rows:
                if isinstance(r.get("created_at"), datetime):
                    r["created_at"] = r["created_at"].replace(tzinfo=timezone.utc).isoformat()
            return rows
    finally:
        conn.close()


def get_usage_stats(course_id: str, source: str = "real",
                    tz_name: str = "UTC") -> dict:
    """Compute usage statistics for a course.

    tz_name is an IANA time zone name (e.g. America/New_York); daily
    buckets are computed with zoneinfo so DST transitions are correct.
    """
    events = get_usage_events(course_id, source, limit=10000)
    tz = ZoneInfo(tz_name)
    stats = compute_usage_stats(events, tz, get_settings())
    stats["course_id"] = course_id
    stats["source"] = source
    return stats


def compute_usage_stats(events: list[dict], tz: ZoneInfo, settings) -> dict:
    """Pure statistics over a list of usage events (unit-testable).

    `events` items carry an ISO-8601 `created_at` (UTC). Study minutes are
    an estimate: events are clustered into study segments by an inactivity
    gap, each segment lasting its time span plus a fixed minimum per event.
    Real session durations arrive in M3.
    """
    search_count = sum(1 for e in events if e["event"] == "search")
    import_count = sum(1 for e in events if e["event"] == "import")
    analyze_count = sum(1 for e in events if e["event"] == "analyze")
    quiz_count = sum(1 for e in events if e["event"] == "quiz")

    sessions = set()
    for e in events:
        if e.get("session_id"):
            sessions.add(e["session_id"])

    timed = []
    for e in events:
        if e.get("created_at"):
            timed.append((datetime.fromisoformat(e["created_at"]), e))
    timed.sort(key=lambda p: p[0])

    daily: dict[str, dict] = {}
    for dt, e in timed:
        day_key = dt.astimezone(tz).strftime("%Y-%m-%d")
        if day_key not in daily:
            daily[day_key] = {"date": day_key, "search": 0, "import": 0,
                              "analyze": 0, "quiz": 0, "total": 0}
        daily[day_key][e["event"]] = daily[day_key].get(e["event"], 0) + 1
        daily[day_key]["total"] += 1

    # estimated study time: cluster by inactivity gap
    gap = timedelta(minutes=settings.usage_session_gap_minutes)
    per_event = settings.usage_minutes_per_event
    study_minutes = 0.0
    seg_start = seg_end = None
    seg_events = 0

    def close_segment():
        nonlocal seg_start, seg_end, seg_events, study_minutes
        if seg_start is not None:
            span_min = (seg_end - seg_start).total_seconds() / 60.0
            study_minutes += max(span_min, seg_events * per_event)
        seg_start = seg_end = None
        seg_events = 0

    for dt, _e in timed:
        if seg_end is not None and dt - seg_end > gap:
            close_segment()
        if seg_start is None:
            seg_start = dt
        seg_end = dt
        seg_events += 1
    close_segment()

    daily_list = sorted(daily.values(), key=lambda d: d["date"])

    return {
        "session_count": len(sessions),
        "search_count": search_count,
        "import_count": import_count,
        "analyze_count": analyze_count,
        "quiz_count": quiz_count,
        "total_events": len(events),
        "study_minutes": round(study_minutes, 1),
        "daily": daily_list,
    }
