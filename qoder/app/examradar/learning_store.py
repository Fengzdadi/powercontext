"""学习会话与出题记录的存储（新表，M3 专用）。

learning_sessions / quiz_questions 建表和读写都放在本模块，
不改动 seekdb.py 里已有的表定义。

隐私：本表只存学习者名字的短哈希（learner_hash）和 PowerContext scope_id
（scp_… 随机 id），不存明文名字——名字只出现在本机 PowerContext 的 Scope 里。

时长口径：30 分钟（config.session_idle_minutes）没有任何事件视为已结束，
时长按最后一个事件的时间计（ended_at / duration = last_event_at - started_at）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import get_settings
from .seekdb import get_connection


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_learning_tables() -> None:
    """幂等建表。由 main.py 的 lifespan 调用。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS learning_sessions (
                    session_id    VARCHAR(64) PRIMARY KEY,
                    scope_id      VARCHAR(128),
                    learner_hash  CHAR(8) NOT NULL,
                    course_id     VARCHAR(64) NOT NULL,
                    started_at    DATETIME NOT NULL,
                    last_event_at DATETIME NOT NULL,
                    ended_at      DATETIME,
                    INDEX idx_learner_course (learner_hash, course_id)
                ) ORGANIZATION HEAP
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS quiz_questions (
                    id           VARCHAR(32) PRIMARY KEY,
                    session_id   VARCHAR(64) NOT NULL,
                    course_id    VARCHAR(64) NOT NULL,
                    topic_id     VARCHAR(16) NOT NULL,
                    topic_name   VARCHAR(256) NOT NULL,
                    question_type VARCHAR(16) NOT NULL,
                    payload      TEXT NOT NULL,
                    created_at   DATETIME NOT NULL,
                    answered_at  DATETIME,
                    answer       TEXT,
                    correct      TINYINT,
                    box_before   INT,
                    box_after    INT,
                    INDEX idx_session (session_id)
                ) ORGANIZATION HEAP
            """)
    finally:
        conn.close()


# ------------------------------------------------------------------- sessions

def create_session(session_id: str, scope_id: Optional[str], learner_hash: str,
                   course_id: str) -> None:
    now = _utc_now()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO learning_sessions (session_id, scope_id, learner_hash, "
                "course_id, started_at, last_event_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (session_id, scope_id, learner_hash, course_id, now, now),
            )
    finally:
        conn.close()


def get_session(session_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM learning_sessions WHERE session_id = %s",
                        (session_id,))
            row = cur.fetchone()
            _decode_session(row)
            return row
    finally:
        conn.close()


def touch_session(session_id: str) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE learning_sessions SET last_event_at = %s "
                        "WHERE session_id = %s", (_utc_now(), session_id))
    finally:
        conn.close()


def mark_idle_sessions_ended() -> int:
    """把超过 idle 分钟没有事件的会话标记为已结束（ended_at = last_event_at）。"""
    s = get_settings()
    cutoff = _utc_now() - timedelta(minutes=s.session_idle_minutes)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE learning_sessions SET ended_at = last_event_at "
                "WHERE ended_at IS NULL AND last_event_at < %s", (cutoff,))
            return cur.rowcount
    finally:
        conn.close()


def end_session(session_id: str) -> Optional[dict]:
    """结束会话：ended_at 取最后一个事件的时间。返回更新后的会话行。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE learning_sessions SET ended_at = last_event_at "
                "WHERE session_id = %s AND ended_at IS NULL", (session_id,))
            cur.execute("SELECT * FROM learning_sessions WHERE session_id = %s",
                        (session_id,))
            row = cur.fetchone()
            _decode_session(row)
            return row
    finally:
        conn.close()


def session_duration_seconds(session: dict) -> float:
    """时长按最后一个事件计；不足 1 分钟按实际秒数。"""
    started = session.get("started_at")
    last = session.get("ended_at") or session.get("last_event_at")
    if isinstance(started, datetime) and isinstance(last, datetime):
        return max(0.0, (last - started).total_seconds())
    return 0.0


def _decode_session(row: Optional[dict]) -> None:
    if not row:
        return
    for key in ("started_at", "last_event_at", "ended_at"):
        if isinstance(row.get(key), datetime):
            row[key] = row[key].replace(tzinfo=timezone.utc).isoformat()


# ------------------------------------------------------------------- questions

def create_question(question_id: str, session_id: str, course_id: str,
                    topic_id: str, topic_name: str, question_type: str,
                    payload: dict) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO quiz_questions (id, session_id, course_id, topic_id, "
                "topic_name, question_type, payload, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (question_id, session_id, course_id, topic_id, topic_name,
                 question_type, json.dumps(payload, ensure_ascii=False), _utc_now()),
            )
    finally:
        conn.close()


def get_question(question_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM quiz_questions WHERE id = %s", (question_id,))
            row = cur.fetchone()
            if row and isinstance(row.get("payload"), str):
                row["payload"] = json.loads(row["payload"])
            for key in ("created_at", "answered_at"):
                if isinstance(row.get(key), datetime):
                    row[key] = row[key].replace(tzinfo=timezone.utc).isoformat()
            return row
    finally:
        conn.close()


def save_answer(question_id: str, answer: str, correct: bool,
                box_before: Optional[int], box_after: Optional[int]) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE quiz_questions SET answered_at = %s, answer = %s, correct = %s, "
                "box_before = %s, box_after = %s WHERE id = %s",
                (_utc_now(), answer, 1 if correct else 0, box_before, box_after,
                 question_id),
            )
    finally:
        conn.close()


def last_question_of_session(session_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM quiz_questions WHERE session_id = %s "
                "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
            row = cur.fetchone()
            if row and isinstance(row.get("payload"), str):
                row["payload"] = json.loads(row["payload"])
            return row
    finally:
        conn.close()


def session_question_stats(session_id: str) -> dict:
    """{asked, answered, correct, wrong_by_topic: {topic_id: (name, count)}}"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT topic_id, topic_name, correct FROM quiz_questions "
                "WHERE session_id = %s AND answered_at IS NOT NULL", (session_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    asked = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    wrong_by_topic: dict[str, tuple[str, int]] = {}
    for r in rows:
        if not r["correct"]:
            tid = r["topic_id"]
            name, count = wrong_by_topic.get(tid, (r["topic_name"], 0))
            wrong_by_topic[tid] = (name, count + 1)
    return {"asked": asked, "correct": correct, "wrong_by_topic": wrong_by_topic}
