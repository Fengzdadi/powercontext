"""seekdb storage for the court: schema, seed data, filing, verdicts and hybrid search."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
import yaml

from .embedding import Embedder

log = logging.getLogger("court.store")

SEED_DIR = Path(os.environ.get("COURT_SEED_DIR", Path(__file__).resolve().parent.parent / "seed"))
DEFENDANT_TYPES = ("pet", "appliance", "digital", "person", "food", "body", "nature", "time", "other")
TYPE_LABELS = {
    "pet": "宠物动物", "appliance": "家电物件", "digital": "数码网络", "person": "人",
    "food": "食物", "body": "身体", "nature": "天气自然", "time": "时间与抽象", "other": "其他",
}
OUTCOME_LABELS = {"plaintiff": "原告胜诉", "defendant": "被告胜诉", "split": "各打五十大板", "withdrawn": "原告撤诉"}
FIRST_PLAYER_CASE_ID = 101


def _schema(dim: int) -> list[str]:
    # DBMS_HYBRID_SEARCH needs heap-organized tables and one FULLTEXT index per searched column.
    return [
        """CREATE TABLE IF NOT EXISTS case_seq (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) AUTO_INCREMENT = %d""" % FIRST_PLAYER_CASE_ID,
        f"""CREATE TABLE IF NOT EXISTS cases (
            id BIGINT NOT NULL,
            case_no VARCHAR(64) NOT NULL,
            source VARCHAR(16) NOT NULL,
            status VARCHAR(16) NOT NULL,
            plaintiff VARCHAR(64) NOT NULL,
            defendant VARCHAR(64) NOT NULL,
            defendant_type VARCHAR(16) NOT NULL,
            title VARCHAR(255) NOT NULL,
            grievance TEXT NOT NULL,
            demand VARCHAR(512) NOT NULL DEFAULT '',
            verdict TEXT,
            judge_quote VARCHAR(512),
            outcome VARCHAR(16),
            tags VARCHAR(255) NOT NULL DEFAULT '',
            conversation_id VARCHAR(64) NOT NULL DEFAULT '',
            filed_at DATETIME NOT NULL,
            judged_at DATETIME,
            embedding VECTOR({dim}),
            UNIQUE KEY uk_cases_id (id),
            UNIQUE KEY uk_cases_no (case_no),
            KEY idx_cases_status (status),
            KEY idx_cases_plaintiff (plaintiff),
            VECTOR INDEX vidx_cases (embedding) WITH (distance=cosine, type=hnsw, lib=vsag),
            FULLTEXT INDEX ftx_cases_title (title) WITH PARSER ik,
            FULLTEXT INDEX ftx_cases_grievance (grievance) WITH PARSER ik,
            FULLTEXT INDEX ftx_cases_verdict (verdict) WITH PARSER ik,
            FULLTEXT INDEX ftx_cases_tags (tags) WITH PARSER ik
        ) ORGANIZATION HEAP""",
        f"""CREATE TABLE IF NOT EXISTS statutes (
            id BIGINT NOT NULL,
            article_no INT NOT NULL,
            chapter VARCHAR(64) NOT NULL,
            title VARCHAR(128) NOT NULL,
            content TEXT NOT NULL,
            tags VARCHAR(255) NOT NULL DEFAULT '',
            embedding VECTOR({dim}),
            UNIQUE KEY uk_statutes_id (id),
            UNIQUE KEY uk_statutes_article (article_no),
            VECTOR INDEX vidx_statutes (embedding) WITH (distance=cosine, type=hnsw, lib=vsag),
            FULLTEXT INDEX ftx_statutes_title (title) WITH PARSER ik,
            FULLTEXT INDEX ftx_statutes_content (content) WITH PARSER ik,
            FULLTEXT INDEX ftx_statutes_tags (tags) WITH PARSER ik
        ) ORGANIZATION HEAP""",
    ]


def _vec(values: list[float] | None) -> str | None:
    if values is None:
        return None
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def _clean_query(text: str) -> str:
    # query_string has its own operator syntax; keep only words so player text can never break it.
    words = re.sub(r"[^\w一-鿿]+", " ", text or "").split()
    return " ".join(words)[:200]


def chinese_number(n: int) -> str:
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    return digits[n // 10] + "十" + (digits[n % 10] if n % 10 else "")


class CourtStore:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.host = os.environ.get("SEEKDB_HOST", "seekdb")
        self.port = int(os.environ.get("SEEKDB_PORT", "2881"))
        self.user = os.environ.get("SEEKDB_USER", "root")
        self.password = os.environ.get("SEEKDB_PASSWORD", "")
        self.database = os.environ.get("SEEKDB_DATABASE", "court")
        self.hybrid_native = True

    # ------------------------------------------------------------------ connections
    def _connect(self, database: str | None = None) -> pymysql.connections.Connection:
        return pymysql.connect(
            host=self.host, port=self.port, user=self.user, password=self.password,
            database=database, charset="utf8mb4", autocommit=True,
            connect_timeout=5, read_timeout=30, write_timeout=30,
            cursorclass=pymysql.cursors.DictCursor,
        )

    @contextmanager
    def cursor(self) -> Iterator[pymysql.cursors.DictCursor]:
        conn = self._connect(self.database)
        try:
            with conn.cursor() as cur:
                yield cur
        finally:
            conn.close()

    def wait_until_ready(self, timeout: float = 300) -> None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                conn = self._connect()
                with conn.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}`")
                conn.close()
                return
            except pymysql.MySQLError as exc:
                if time.monotonic() > deadline:
                    raise
                log.info("waiting for seekdb at %s:%s (%s)", self.host, self.port, exc)
                time.sleep(3)

    # ------------------------------------------------------------------ bootstrap
    def init_schema(self) -> None:
        with self.cursor() as cur:
            for ddl in _schema(self.embedder.dim):
                cur.execute(ddl)

    def load_seed(self) -> dict[str, int]:
        statutes = yaml.safe_load((SEED_DIR / "statutes.yaml").read_text(encoding="utf-8"))
        precedents = yaml.safe_load((SEED_DIR / "precedents.yaml").read_text(encoding="utf-8"))
        added = {"statutes": 0, "precedents": 0}
        with self.cursor() as cur:
            cur.execute("SELECT article_no FROM statutes")
            have = {row["article_no"] for row in cur.fetchall()}
            todo = [s for s in statutes if s["article_no"] not in have]
            vectors = self.embedder.embed_documents([f"{s['title']}：{s['content']}" for s in todo]) if todo else []
            for s, v in zip(todo, vectors or [None] * len(todo)):
                cur.execute(
                    "INSERT INTO statutes (id, article_no, chapter, title, content, tags, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (s["article_no"], s["article_no"], s["chapter"], s["title"], s["content"], s.get("tags", ""), _vec(v)),
                )
                added["statutes"] += 1

            cur.execute("SELECT case_no FROM cases WHERE source = 'seed'")
            have_cases = {row["case_no"] for row in cur.fetchall()}
            todo_cases = [(i, p) for i, p in enumerate(precedents, start=1) if p["case_no"] not in have_cases]
            texts = [self._case_text(p["title"], p["grievance"], p["verdict"]) for _, p in todo_cases]
            vectors = self.embedder.embed_documents(texts) if texts else []
            for (i, p), v in zip(todo_cases, vectors or [None] * len(todo_cases)):
                year = int(re.search(r"（(\d{4})）", p["case_no"]).group(1))
                cur.execute(
                    "INSERT INTO cases (id, case_no, source, status, plaintiff, defendant, defendant_type, title, "
                    "grievance, demand, verdict, judge_quote, outcome, tags, filed_at, judged_at, embedding) "
                    "VALUES (%s, %s, 'seed', 'judged', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (i, p["case_no"], p["plaintiff"], p["defendant"], p["defendant_type"], p["title"],
                     p["grievance"], p.get("demand", ""), p["verdict"], p.get("judge_quote", ""), p["outcome"],
                     p.get("tags", ""), datetime(year, 6, 1), datetime(year, 6, 1), _vec(v)),
                )
                added["precedents"] += 1
        return added

    @staticmethod
    def _case_text(title: str, grievance: str, verdict: str | None) -> str:
        return f"{title}。案情：{grievance} 判决：{verdict or ''}"

    # ------------------------------------------------------------------ filing & verdicts
    def file_case(self, player: str, defendant: str, defendant_type: str, grievance: str, demand: str,
                  conversation_id: str) -> dict[str, Any]:
        now = datetime.now()
        with self.cursor() as cur:
            cur.execute("INSERT INTO case_seq (created_at) VALUES (%s)", (now,))
            case_id = cur.lastrowid
            case_no = f"（{now.year}）喵民初字第{case_id:04d}号"
            title = f"{player}诉{defendant}案"
            vector = self.embedder.embed_documents([self._case_text(title, grievance, None)])
            cur.execute(
                "INSERT INTO cases (id, case_no, source, status, plaintiff, defendant, defendant_type, title, "
                "grievance, demand, conversation_id, filed_at, embedding) "
                "VALUES (%s, %s, 'player', 'filed', %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (case_id, case_no, player, defendant, defendant_type, title, grievance, demand,
                 conversation_id, now, _vec(vector[0] if vector else None)),
            )
        return {"case_id": case_id, "case_no": case_no, "title": title, "filed_at": now.isoformat(timespec="seconds")}

    def get_case(self, case_no: str) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute(
                "SELECT id, case_no, source, status, plaintiff, defendant, defendant_type, title, grievance, demand, "
                "verdict, judge_quote, outcome, tags, filed_at, judged_at FROM cases WHERE case_no = %s",
                (case_no,),
            )
            return cur.fetchone()

    def record_verdict(self, case_no: str, title: str, verdict: str, outcome: str, judge_quote: str,
                       tags: str) -> dict[str, Any] | None:
        case = self.get_case(case_no)
        if case is None:
            return None
        title = title or case["title"]
        vector = self.embedder.embed_documents([self._case_text(title, case["grievance"], verdict)])
        with self.cursor() as cur:
            cur.execute(
                "UPDATE cases SET status = 'judged', title = %s, verdict = %s, outcome = %s, judge_quote = %s, "
                "tags = %s, judged_at = %s, embedding = %s WHERE case_no = %s",
                (title, verdict, outcome, judge_quote, tags, datetime.now(), _vec(vector[0] if vector else None),
                 case_no),
            )
            cur.execute("SELECT COUNT(*) AS n FROM cases WHERE status = 'judged'")
            total = cur.fetchone()["n"]
        return {"case_no": case_no, "title": title, "status": "judged", "precedent_count": total}

    def withdraw(self, case_no: str) -> bool:
        with self.cursor() as cur:
            cur.execute("UPDATE cases SET status = 'withdrawn', outcome = 'withdrawn', judged_at = %s "
                        "WHERE case_no = %s AND status = 'filed'", (datetime.now(), case_no))
            return cur.rowcount > 0

    # ------------------------------------------------------------------ search
    def search_cases(self, query: str, k: int, defendant_type: str | None = None,
                     exclude_case_no: str | None = None) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [{"term": {"status": "judged"}}]
        if defendant_type:
            filters.append({"term": {"defendant_type": defendant_type}})
        fields = ["case_no", "source", "plaintiff", "defendant", "defendant_type", "title", "grievance", "verdict",
                  "judge_quote", "outcome", "tags"]
        hits = self._hybrid("cases", ["title", "grievance", "verdict", "tags"], query, k + 1, filters, fields)
        return [h for h in hits if h.get("case_no") != exclude_case_no][:k]

    def search_statutes(self, query: str, k: int) -> list[dict[str, Any]]:
        fields = ["article_no", "chapter", "title", "content"]
        return self._hybrid("statutes", ["title", "content", "tags"], query, k, [], fields)

    def _hybrid(self, table: str, text_fields: list[str], query: str, k: int, filters: list[dict[str, Any]],
                source: list[str]) -> list[dict[str, Any]]:
        text = _clean_query(query)
        vector = self.embedder.embed_query(query) if query else None
        if self.hybrid_native:
            try:
                return self._hybrid_native(table, text_fields, text, vector, k, filters, source)
            except pymysql.MySQLError as exc:
                # Older seekdb builds lack DBMS_HYBRID_SEARCH; the SQL fallback gives the same fusion.
                log.warning("DBMS_HYBRID_SEARCH unavailable, using SQL fallback: %s", exc)
                self.hybrid_native = False
        return self._hybrid_sql(table, text_fields, text, vector, k, filters, source)

    def _hybrid_native(self, table: str, text_fields: list[str], text: str, vector: list[float] | None, k: int,
                       filters: list[dict[str, Any]], source: list[str]) -> list[dict[str, Any]]:
        window = max(k * 4, 20)
        param: dict[str, Any] = {"size": k, "_source": source}
        if text:
            match = {"query_string": {"fields": text_fields, "query": text}}
            param["query"] = {"bool": {"must": [match], "filter": filters}} if filters else match
        if vector is not None:
            param["knn"] = {"field": "embedding", "k": window, "query_vector": vector}
            if filters:
                param["knn"]["filter"] = filters
        if "query" in param and "knn" in param:
            param["rank"] = {"rrf": {"rank_window_size": window, "rank_constant": 60}}
        if "query" not in param and "knn" not in param:
            return []
        with self.cursor() as cur:
            cur.execute("SELECT DBMS_HYBRID_SEARCH.SEARCH(%s, %s) AS hits",
                        (table, json.dumps(param, ensure_ascii=False)))
            raw = cur.fetchone()["hits"]
        hits = json.loads(raw) if raw else []
        for h in hits:
            h["score"] = round(float(h.pop("_score", 0.0)), 4)
            h["matched_by"] = "seekdb DBMS_HYBRID_SEARCH (ik 全文 + HNSW 向量, RRF 融合)"
        return hits

    def _hybrid_sql(self, table: str, text_fields: list[str], text: str, vector: list[float] | None, k: int,
                    filters: list[dict[str, Any]], source: list[str]) -> list[dict[str, Any]]:
        where = ["1 = 1"]
        args: list[Any] = []
        for f in filters:
            (col, val), = f["term"].items()
            where.append(f"`{col}` = %s")
            args.append(val)
        cols = ", ".join(f"`{c}`" for c in source)
        key = source[0]
        ranked: dict[Any, dict[str, Any]] = {}
        with self.cursor() as cur:
            lists = []
            if text:
                match = " + ".join(f"MATCH(`{f}`) AGAINST(%s IN NATURAL LANGUAGE MODE)" for f in text_fields)
                cur.execute(f"SELECT {cols}, ({match}) AS s FROM `{table}` WHERE {' AND '.join(where)} "
                            f"HAVING s > 0 ORDER BY s DESC LIMIT 20", [text] * len(text_fields) + args)
                lists.append(cur.fetchall())
            if vector is not None:
                cur.execute(f"SELECT {cols} FROM `{table}` WHERE {' AND '.join(where)} "
                            f"ORDER BY cosine_distance(embedding, %s) APPROXIMATE LIMIT 20", args + [_vec(vector)])
                lists.append(cur.fetchall())
        for rows in lists:
            for rank, row in enumerate(rows, start=1):
                row.pop("s", None)
                entry = ranked.setdefault(row[key], {**row, "score": 0.0})
                entry["score"] += 1.0 / (60 + rank)
        hits = sorted(ranked.values(), key=lambda r: r["score"], reverse=True)[:k]
        for h in hits:
            h["score"] = round(h["score"], 4)
            h["matched_by"] = "seekdb SQL (MATCH AGAINST + cosine_distance, RRF 融合)"
        return hits

    # ------------------------------------------------------------------ statistics
    def stats(self) -> dict[str, Any]:
        with self.cursor() as cur:
            cur.execute("SELECT source, COUNT(*) AS n FROM cases WHERE status = 'judged' GROUP BY source")
            by_source = {r["source"]: r["n"] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*) AS n FROM cases WHERE status = 'filed'")
            pending = cur.fetchone()["n"]
            cur.execute("SELECT defendant, COUNT(*) AS n FROM cases WHERE status IN ('judged', 'filed') "
                        "GROUP BY defendant ORDER BY n DESC, defendant LIMIT 5")
            top_defendants = cur.fetchall()
            cur.execute("SELECT outcome, COUNT(*) AS n FROM cases WHERE status = 'judged' GROUP BY outcome")
            outcomes = {r["outcome"]: r["n"] for r in cur.fetchall()}
            cur.execute("SELECT plaintiff, COUNT(*) AS n FROM cases WHERE source = 'player' "
                        "AND status IN ('judged', 'filed') GROUP BY plaintiff ORDER BY n DESC, plaintiff LIMIT 3")
            top_plaintiffs = cur.fetchall()
            cur.execute("SELECT case_no, title, outcome, judge_quote FROM cases WHERE source = 'player' "
                        "AND status = 'judged' ORDER BY judged_at DESC LIMIT 3")
            recent = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS n FROM statutes")
            statutes = cur.fetchone()["n"]
        return {
            "precedents_total": sum(by_source.values()), "precedents_seed": by_source.get("seed", 0),
            "precedents_player": by_source.get("player", 0), "pending_cases": pending, "statutes": statutes,
            "outcomes": outcomes, "top_defendants": top_defendants, "top_plaintiffs": top_plaintiffs,
            "recent_player_cases": recent,
        }

    def ping(self) -> dict[str, Any]:
        with self.cursor() as cur:
            cur.execute("SELECT VERSION() AS v")
            version = cur.fetchone()["v"]
            cur.execute("SELECT COUNT(*) AS n FROM cases WHERE status = 'judged'")
            judged = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM statutes")
            statutes = cur.fetchone()["n"]
        return {"version": version, "precedents": judged, "statutes": statutes}
