"""seekdb 存储层：建表、增量导入、混合检索和追溯关系查询。每条 SQL 都写进查询记录。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import pymysql
from pymysql.cursors import DictCursor

from . import vectors
from .ingest import Chunk
from .records import Recorder

SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS sdd_chunks (
  project      VARCHAR(64)  NOT NULL,
  chunk_id     VARCHAR(400) NOT NULL,
  kind         VARCHAR(16)  NOT NULL,
  path         VARCHAR(400) NOT NULL,
  symbol       VARCHAR(256) NOT NULL,
  title        VARCHAR(512) NOT NULL,
  content      LONGTEXT     NOT NULL,
  keywords     TEXT         NOT NULL,
  status       VARCHAR(32)  NOT NULL,
  grp          VARCHAR(256) NOT NULL,
  start_line   INT          NOT NULL,
  end_line     INT          NOT NULL,
  content_sha  CHAR(64)     NOT NULL,
  revision     INT          NOT NULL,
  import_run   BIGINT       NOT NULL,
  updated_at   DATETIME(6)  NOT NULL,
  embedding    VECTOR({vectors.DIM}) NOT NULL,
  PRIMARY KEY (project, chunk_id),
  KEY idx_chunks_kind (project, kind),
  VECTOR INDEX idx_chunks_embedding (embedding) WITH (distance=cosine, type=hnsw, sync_mode=immediate),
  FULLTEXT INDEX ft_chunks_title (title) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="max_word"),
  FULLTEXT INDEX ft_chunks_keywords (keywords) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="max_word"),
  FULLTEXT INDEX ft_chunks_content (content) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="max_word")
) ORGANIZATION HEAP""",
    """CREATE TABLE IF NOT EXISTS sdd_links (
  project    VARCHAR(64)  NOT NULL,
  src_chunk  VARCHAR(400) NOT NULL,
  rel        VARCHAR(16)  NOT NULL,
  target     VARCHAR(256) NOT NULL,
  PRIMARY KEY (project, src_chunk, rel, target),
  KEY idx_links_target (project, rel, target)
)""",
    """CREATE TABLE IF NOT EXISTS sdd_chunk_revisions (
  project      VARCHAR(64)  NOT NULL,
  chunk_id     VARCHAR(400) NOT NULL,
  revision     INT          NOT NULL,
  change_kind  VARCHAR(16)  NOT NULL,
  content_sha  CHAR(64)     NOT NULL,
  title        VARCHAR(512) NOT NULL,
  content      LONGTEXT     NOT NULL,
  import_run   BIGINT       NOT NULL,
  created_at   DATETIME(6)  NOT NULL,
  PRIMARY KEY (project, chunk_id, revision)
)""",
    """CREATE TABLE IF NOT EXISTS sdd_import_runs (
  run_id       BIGINT       NOT NULL PRIMARY KEY,
  project      VARCHAR(64)  NOT NULL,
  project_dir  VARCHAR(512) NOT NULL,
  tree_sha     CHAR(64)     NOT NULL,
  code_version VARCHAR(128) NOT NULL,
  started_at   DATETIME(6)  NOT NULL,
  finished_at  DATETIME(6)  NULL,
  added        INT NOT NULL DEFAULT 0,
  updated      INT NOT NULL DEFAULT 0,
  moved        INT NOT NULL DEFAULT 0,
  unchanged    INT NOT NULL DEFAULT 0,
  removed      INT NOT NULL DEFAULT 0,
  total        INT NOT NULL DEFAULT 0,
  changes      LONGTEXT NULL
)""",
]

SOURCE_FIELDS = [
    "chunk_id", "kind", "path", "symbol", "title", "status", "grp", "start_line", "end_line",
    "revision", "content_sha", "_keyword_score", "_semantic_score", "_keyword_rank", "_semantic_rank",
]  # fmt: skip

_VECTOR_LITERAL = re.compile(r"\[(?:-?\d+\.\d+,){8,}-?\d+\.\d+\]")


@dataclass
class ImportReport:
    run_id: int
    project: str
    tree_sha: str
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    moved: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    total: int = 0
    links: int = 0
    seconds: float = 0.0


def clean_query(text: str, limit: int = 1500) -> str:
    """DBMS_HYBRID_SEARCH 会把检索词原样拼进 MATCH ... AGAINST('...')，先去掉引号和反斜杠。"""
    text = re.sub(r"['\"\\`]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _short(value: object) -> object:
    if isinstance(value, str):
        value = _VECTOR_LITERAL.sub(f"[…{vectors.DIM} 维向量…]", value)
        return value if len(value) <= 300 else value[:300] + f"…（共 {len(value)} 字符）"
    if isinstance(value, (list, tuple)):
        if len(value) > 20 and all(isinstance(x, float) for x in value):
            return f"[…{len(value)} 维向量…]"
        return [_short(v) for v in value]
    return value


class Store:
    def __init__(self, settings, recorder: Recorder) -> None:
        self.recorder = recorder
        self.database = settings.seekdb_database
        deadline = time.monotonic() + 60
        while True:
            try:
                self.conn = pymysql.connect(
                    host=settings.seekdb_host,
                    port=settings.seekdb_port,
                    user=settings.seekdb_user,
                    password=settings.seekdb_password,
                    charset="utf8mb4",
                    autocommit=True,
                    connect_timeout=10,
                    read_timeout=300,
                    write_timeout=300,
                    cursorclass=DictCursor,
                )
                break
            except pymysql.err.OperationalError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(2)
        if not re.fullmatch(r"[A-Za-z0-9_]+", self.database):
            raise ValueError(f"非法的数据库名：{self.database}")
        self.q(f"CREATE DATABASE IF NOT EXISTS `{self.database}`", purpose="schema")
        self.conn.select_db(self.database)

    # -------------------------------------------------------------- 基础

    def q(self, sql: str, args: object = None, *, purpose: str, preview: int = 0) -> list[dict]:
        started = time.perf_counter()
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            rows = list(cur.fetchall()) if cur.description else []
            affected = cur.rowcount
        record = {
            "db": "seekdb",
            "purpose": purpose,
            "sql": _short(re.sub(r"\s+", " ", sql).strip()),
            "args": _short(list(args) if isinstance(args, tuple) else args),
            "rows": len(rows) if rows else affected,
            "ms": round((time.perf_counter() - started) * 1000, 1),
        }
        if preview and rows:
            record["preview"] = _short([{k: v for k, v in row.items() if k != "content"} for row in rows[:preview]])
        self.recorder.write(record)
        return rows

    def executemany(self, sql: str, rows: list[tuple], *, purpose: str) -> None:
        if not rows:
            return
        started = time.perf_counter()
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)
        self.recorder.write(
            {
                "db": "seekdb",
                "purpose": purpose,
                "sql": _short(re.sub(r"\s+", " ", sql).strip()),
                "batch": len(rows),
                "ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )

    def ensure_schema(self) -> None:
        for ddl in SCHEMA:
            self.q(ddl, purpose="schema")

    def version(self) -> str:
        return self.q("SELECT version() AS v", purpose="info")[0]["v"]

    # -------------------------------------------------------------- 导入

    def import_chunks(self, project: str, project_dir: str, tree_sha: str, code_version: str, chunks: list[Chunk]) -> ImportReport:
        started = time.perf_counter()
        self.ensure_schema()
        # 批次号自己分配：seekdb 重启后 AUTO_INCREMENT 会跳号（缓存段），批次号应当连续
        run_id = int(self.q("SELECT COALESCE(MAX(run_id), 0) + 1 AS id FROM sdd_import_runs", purpose="import: open run")[0]["id"])
        self.q(
            "INSERT INTO sdd_import_runs (run_id, project, project_dir, tree_sha, code_version, started_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(6))",
            (run_id, project, project_dir, tree_sha, code_version),
            purpose="import: open run",
        )
        report = ImportReport(run_id=run_id, project=project, tree_sha=tree_sha, total=len(chunks))

        existing = {
            row["chunk_id"]: row
            for row in self.q(
                "SELECT chunk_id, content_sha, revision, start_line, end_line, path FROM sdd_chunks WHERE project = %s",
                (project,),
                purpose="import: load current index",
            )
        }
        self.conn.begin()
        try:
            for chunk in chunks:
                old = existing.pop(chunk.chunk_id, None)
                if old is None:
                    self._write_chunk(project, chunk, 1, run_id, insert=True)
                    report.added.append(chunk.chunk_id)
                elif old["content_sha"] != chunk.content_sha:
                    self._write_chunk(project, chunk, old["revision"] + 1, run_id, insert=False)
                    report.updated.append(chunk.chunk_id)
                elif (old["start_line"], old["end_line"], old["path"]) != (chunk.start_line, chunk.end_line, chunk.path):
                    self.q(
                        "UPDATE sdd_chunks SET start_line = %s, end_line = %s, path = %s, import_run = %s, updated_at = NOW(6) "
                        "WHERE project = %s AND chunk_id = %s",
                        (chunk.start_line, chunk.end_line, chunk.path, run_id, project, chunk.chunk_id),
                        purpose="import: move chunk",
                    )
                    report.moved.append(chunk.chunk_id)
                else:
                    report.unchanged += 1
            for chunk_id, old in existing.items():
                self.q("DELETE FROM sdd_chunks WHERE project = %s AND chunk_id = %s", (project, chunk_id), purpose="import: remove chunk")
                self.q(
                    "INSERT INTO sdd_chunk_revisions (project, chunk_id, revision, change_kind, content_sha, title, content, import_run, created_at) "
                    "VALUES (%s, %s, %s, 'removed', %s, '', '', %s, NOW(6))",
                    (project, chunk_id, old["revision"] + 1, old["content_sha"], run_id),
                    purpose="import: remove chunk",
                )
                report.removed.append(chunk_id)
            self.q("DELETE FROM sdd_links WHERE project = %s", (project,), purpose="import: rebuild links")
            links = sorted({(project, c.chunk_id, rel, target) for c in chunks for rel, target in c.links})
            self.executemany(
                "INSERT INTO sdd_links (project, src_chunk, rel, target) VALUES (%s, %s, %s, %s)",
                links,
                purpose="import: rebuild links",
            )
            report.links = len(links)
            changes = {"added": report.added, "updated": report.updated, "moved": report.moved, "removed": report.removed}
            self.q(
                "UPDATE sdd_import_runs SET finished_at = NOW(6), added = %s, updated = %s, moved = %s, unchanged = %s, "
                "removed = %s, total = %s, changes = %s WHERE run_id = %s",
                (len(report.added), len(report.updated), len(report.moved), report.unchanged, len(report.removed),
                 report.total, json.dumps(changes, ensure_ascii=False), run_id),
                purpose="import: close run",
            )  # fmt: skip
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        report.seconds = round(time.perf_counter() - started, 2)
        return report

    def _write_chunk(self, project: str, chunk: Chunk, revision: int, run_id: int, *, insert: bool) -> None:
        embedding = vectors.literal(vectors.embed(f"{chunk.title}\n{chunk.keywords}\n{chunk.content}"))
        values = (
            chunk.kind, chunk.path, chunk.symbol, chunk.title, chunk.content, chunk.keywords, chunk.status,
            chunk.group, chunk.start_line, chunk.end_line, chunk.content_sha, revision, run_id, embedding,
        )  # fmt: skip
        if insert:
            self.q(
                "INSERT INTO sdd_chunks (kind, path, symbol, title, content, keywords, status, grp, start_line, end_line, "
                "content_sha, revision, import_run, embedding, updated_at, project, chunk_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(6), %s, %s)",
                values + (project, chunk.chunk_id),
                purpose="import: add chunk",
            )
        else:
            self.q(
                "UPDATE sdd_chunks SET kind = %s, path = %s, symbol = %s, title = %s, content = %s, keywords = %s, status = %s, "
                "grp = %s, start_line = %s, end_line = %s, content_sha = %s, revision = %s, import_run = %s, embedding = %s, "
                "updated_at = NOW(6) WHERE project = %s AND chunk_id = %s",
                values + (project, chunk.chunk_id),
                purpose="import: update chunk",
            )
        self.q(
            "INSERT INTO sdd_chunk_revisions (project, chunk_id, revision, change_kind, content_sha, title, content, import_run, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(6))",
            (project, chunk.chunk_id, revision, "added" if insert else "updated", chunk.content_sha, chunk.title,
             chunk.content, run_id),
            purpose="import: keep revision",
        )  # fmt: skip

    # -------------------------------------------------------------- 查询

    def _tables_exist(self) -> bool:
        rows = self.q(
            "SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'sdd_import_runs'",
            (self.database,),
            purpose="check schema",
        )
        return bool(rows and rows[0]["n"])

    def latest_import(self, project: str) -> dict | None:
        if not self._tables_exist():
            return None
        rows = self.q(
            "SELECT run_id, project, project_dir, tree_sha, code_version, started_at, finished_at, added, updated, moved, "
            "unchanged, removed, total, changes FROM sdd_import_runs WHERE project = %s AND finished_at IS NOT NULL "
            "ORDER BY run_id DESC LIMIT 1",
            (project,),
            purpose="context: latest import run",
        )
        return rows[0] if rows else None

    def hybrid_search(self, project: str, kinds: list[str], text: str, *, size: int, purpose: str) -> list[dict]:
        """一条 DBMS_HYBRID_SEARCH.SEARCH：IK 全文（title^3, keywords^2, content）+ HNSW 向量，RRF 融合。"""
        query_text = clean_query(text)
        if not query_text:
            return []
        filters = [{"term": {"project": project}}, {"terms": {"kind": kinds}}]
        body = {
            "query": {
                "bool": {
                    "must": [{"query_string": {"fields": ["title^3", "keywords^2", "content"], "query": query_text}}],
                    "filter": filters,
                }
            },
            "knn": {"field": "embedding", "k": size, "query_vector": vectors.embed(query_text), "filter": filters},
            "rank": {"rrf": {}},
            "_source": SOURCE_FIELDS,
            "size": size,
        }
        rows = self.q(
            "SELECT DBMS_HYBRID_SEARCH.SEARCH('sdd_chunks', %s) AS hits",
            (json.dumps(body, ensure_ascii=False),),
            purpose=purpose,
        )
        raw = rows[0]["hits"] if rows else None
        hits = json.loads(raw) if isinstance(raw, (str, bytes)) else (raw or [])
        self.recorder.write(
            {
                "db": "seekdb",
                "purpose": purpose + " (hits)",
                "query_text": query_text,
                "hits": [
                    {
                        "chunk_id": h.get("chunk_id"),
                        "score": round(h.get("_score") or 0, 5),
                        "keyword_rank": h.get("_keyword_rank"),
                        "semantic_rank": h.get("_semantic_rank"),
                    }
                    for h in hits
                ],
            }
        )
        return hits

    def chunks(self, project: str, chunk_ids: list[str], *, purpose: str) -> dict[str, dict]:
        if not chunk_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(chunk_ids))
        rows = self.q(
            "SELECT chunk_id, kind, path, symbol, title, content, keywords, status, grp, start_line, end_line, content_sha, "
            f"revision, import_run FROM sdd_chunks WHERE project = %s AND chunk_id IN ({placeholders})",
            (project, *chunk_ids),
            purpose=purpose,
        )
        return {row["chunk_id"]: row for row in rows}

    def specs_in_groups(self, project: str, groups: list[str], *, purpose: str) -> list[dict]:
        if not groups:
            return []
        placeholders = ", ".join(["%s"] * len(groups))
        return self.q(
            "SELECT chunk_id, symbol, title, status, grp, path, start_line, end_line, revision, content_sha FROM sdd_chunks "
            f"WHERE project = %s AND kind = 'spec' AND grp IN ({placeholders}) ORDER BY path, start_line",
            (project, *groups),
            purpose=purpose,
        )

    def links(self, project: str, rel: str, *, targets: list[str] | None = None, sources: list[str] | None = None,
              purpose: str) -> list[dict]:  # fmt: skip
        sql = "SELECT l.src_chunk, l.rel, l.target, c.kind, c.path, c.symbol FROM sdd_links l " \
              "JOIN sdd_chunks c ON c.project = l.project AND c.chunk_id = l.src_chunk WHERE l.project = %s AND l.rel = %s"  # fmt: skip
        args: list = [project, rel]
        for column, values in (("l.target", targets), ("l.src_chunk", sources)):
            if values is not None:
                if not values:
                    return []
                sql += f" AND {column} IN ({', '.join(['%s'] * len(values))})"
                args += list(values)
        return self.q(sql + " ORDER BY l.src_chunk, l.target", tuple(args), purpose=purpose)

    def spec_revisions(self, project: str, spec_ids: list[str], *, purpose: str) -> list[dict]:
        if not spec_ids:
            return []
        ids = [f"spec:{s}" for s in spec_ids]
        return self.q(
            "SELECT chunk_id, revision, change_kind, content_sha, import_run, created_at FROM sdd_chunk_revisions "
            f"WHERE project = %s AND chunk_id IN ({', '.join(['%s'] * len(ids))}) ORDER BY chunk_id, revision",
            (project, *ids),
            purpose=purpose,
        )

    def revision(self, project: str, chunk_id: str, revision: int, *, purpose: str) -> dict | None:
        rows = self.q(
            "SELECT chunk_id, revision, content_sha, title, content, import_run FROM sdd_chunk_revisions "
            "WHERE project = %s AND chunk_id = %s AND revision = %s",
            (project, chunk_id, revision),
            purpose=purpose,
        )
        return rows[0] if rows else None

    def counts(self, project: str) -> list[dict]:
        if not self._tables_exist():
            return []
        return self.q(
            "SELECT kind, COUNT(*) AS n, MAX(revision) AS max_revision FROM sdd_chunks WHERE project = %s GROUP BY kind ORDER BY kind",
            (project,),
            purpose="inspect: chunk counts",
        )
