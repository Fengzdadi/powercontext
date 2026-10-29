"""seekdb client: connection, DDL, hybrid search."""
from __future__ import annotations

import json
import random
import time
from typing import Any, Optional

import pymysql

from .config import get_settings


def _gen_id() -> int:
    """Generate a BIGINT primary key: timestamp_ms * 1000 + random."""
    return int(time.time() * 1000) * 1000 + random.randint(0, 999)


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
                    id          BIGINT PRIMARY KEY,
                    course_id   VARCHAR(64) NOT NULL,
                    name        VARCHAR(256) NOT NULL,
                    doc_kind    VARCHAR(16) NOT NULL,
                    file_type   VARCHAR(8),
                    sha256      CHAR(64),
                    chunk_count INT DEFAULT 0,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_course (course_id),
                    UNIQUE INDEX idx_sha256 (sha256)
                ) ORGANIZATION HEAP
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id          BIGINT PRIMARY KEY,
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
                    INDEX idx_course_kind (course_id, doc_kind)
                ) ORGANIZATION HEAP
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usage_events (
                    id          BIGINT PRIMARY KEY,
                    session_id  VARCHAR(64),
                    course_id   VARCHAR(64),
                    source      VARCHAR(16) NOT NULL,
                    event       VARCHAR(32) NOT NULL,
                    payload     TEXT,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_session (session_id),
                    INDEX idx_course_source (course_id, source)
                ) ORGANIZATION HEAP
            """)
    finally:
        conn.close()


def insert_document(course_id: str, name: str, doc_kind: str, file_type: str,
                    sha256: str, chunk_count: int) -> int:
    doc_id = _gen_id()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (id, course_id, name, doc_kind, file_type, sha256, chunk_count) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (doc_id, course_id, name, doc_kind, file_type, sha256, chunk_count),
            )
    finally:
        conn.close()
    return doc_id


def find_document_by_sha256(sha256: str) -> Optional[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM documents WHERE sha256 = %s", (sha256,))
            return cur.fetchone()
    finally:
        conn.close()


def insert_chunk(document_id: int, course_id: str, doc_kind: str, content: str,
                 heading: Optional[str], page: Optional[int],
                 question_no: Optional[int], points: Optional[float],
                 chunk_index: int, embedding: list[float]) -> int:
    chunk_id = _gen_id() + chunk_index
    emb_str = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chunks (id, document_id, course_id, doc_kind, content, heading, "
                "page, question_no, points, chunk_index, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (chunk_id, document_id, course_id, doc_kind, content, heading,
                 page, question_no, points, chunk_index, emb_str),
            )
    finally:
        conn.close()
    return chunk_id


def insert_usage_event(course_id: str, source: str, event: str, payload: dict,
                       session_id: Optional[str] = None) -> int:
    eid = _gen_id()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_events (id, session_id, course_id, source, event, payload) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (eid, session_id, course_id, source, event, json.dumps(payload, ensure_ascii=False)),
            )
    finally:
        conn.close()
    return eid


def _escape_search_text(text: str) -> str:
    """Remove characters that would break the JSON/SQL in DBMS_HYBRID_SEARCH."""
    text = text.replace("\\", "")
    text = text.replace('"', "")
    text = text.replace("'", "")
    return text.strip()


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
                "must": [{"match": {"content": safe_text}}],
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
            return hits, json_str, actual_sql
    finally:
        conn.close()


def get_documents(course_id: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, doc_kind, file_type, chunk_count, created_at "
                "FROM documents WHERE course_id = %s ORDER BY created_at",
                (course_id,),
            )
            rows = cur.fetchall()
            for r in rows:
                if r.get("created_at"):
                    r["created_at"] = str(r["created_at"])
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
