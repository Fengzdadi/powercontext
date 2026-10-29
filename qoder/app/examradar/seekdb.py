"""seekdb client: connection, DDL, atomic import, hybrid search."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

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
                f"CREATE DATABASE IF NOT EXISTS `{s.seekdb_database}` "
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
    finally:
        conn.close()


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


def delete_course(course_id: str) -> dict:
    """Delete all documents, chunks and usage_events of a course."""
    counts = {}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for table in ("chunks", "documents", "usage_events"):
                cur.execute(f"DELETE FROM {table} WHERE course_id = %s", (course_id,))
                counts[table] = cur.rowcount
    finally:
        conn.close()
    return counts


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
