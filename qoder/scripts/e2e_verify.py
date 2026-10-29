#!/usr/bin/env python3
"""ExamRadar 端到端验证脚本（会话 08a 建立，会话 10 加入复习教练一步）。

按验证样例逐步执行：健康检查 → 导入样例资料 → 6 条验收检索 → 覆盖雷达 →
复习教练（学习会话 + 出题判分 + PowerContext 记忆）。
每一步写进 Markdown 报告（默认 docs/validation/e2e-report.md），全部通过
退出码为 0，否则为 1。只用标准库；所有请求带 X-ExamRadar-Source: auto。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# ===========================================================================
# 期望值（集中在此，注明出处；不要散到各步骤函数里）
# ===========================================================================

COURSE_ID = "db101"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples" / "course-db"
SYLLABUS_FILE = SAMPLES_DIR / "syllabus.txt"

# 导入的 6 份资料（出处：samples/course-db/README.md 资料表；目录→类型）。
# README 未写各份资料的块数：块数以首次导入实际结果为准，仅核对重复导入后不变。
IMPORT_FILES: list[tuple[str, str]] = [
    ("notes/02-SQL速记.md", "notes"),
    ("notes/03-索引与B+树.md", "notes"),
    ("notes/05-事务与并发控制.md", "notes"),
    ("slides/第7讲-故障恢复.pdf", "slides"),
    ("exams/2025-2026-1-期末试卷A.pdf", "exam"),
    ("papers/two-phase-commit-primer.pdf", "paper"),
]

# 试卷规模（出处：samples/course-db/README.md 资料表 ——
# "2 页、11 道题、满分 100，每题标了分值"）。
EXAM_QUESTION_COUNT = 11
EXAM_TOTAL_POINTS = 100.0

# 6 条验收检索（出处：dev-records/prompts/02-m1-ingest-search.md 验收表。
# 前 5 条用默认范围（notes/slides/paper），最后一条 include_exam=True）。
ACCEPTANCE_QUERIES: list[dict] = [
    {
        "query": "B+树插入时结点分裂",
        "include_exam": False,
        "expect_doc": "03-索引与B+树.md",
        "expect_heading_contains": "3.3",
        "note": "笔记 03 的 3.3 节",
    },
    {
        "query": "脏页表",
        "include_exam": False,
        "expect_doc": "第7讲-故障恢复.pdf",
        "expect_page": 7,
        "note": "课件第 7 页（ARIES 三个阶段）",
    },
    {
        "query": "先写日志原则",
        "include_exam": False,
        "expect_doc": "第7讲-故障恢复.pdf",
        "expect_page": 4,
        "note": "课件第 4 页",
    },
    {
        "query": "coordinator crash blocking",
        "include_exam": False,
        "expect_doc": "two-phase-commit-primer.pdf",
        "expect_page": 2,
        "note": "英文阅读材料第 2 页",
    },
    {
        "query": "两阶段锁能不能避免死锁",
        "include_exam": False,
        "expect_doc": "05-事务与并发控制.md",
        "expect_heading_contains_any": ["5.3", "5.4"],
        "note": "笔记 05 的 5.3 或 5.4 节",
    },
    {
        "query": "函数依赖 候选码",
        "include_exam": True,
        "expect_doc": "2025-2026-1-期末试卷A.pdf",
        "expect_question_no": 4,
        "note": "往年试卷第 4 题",
    },
]

# 覆盖雷达设计真值（出处：samples/course-db/README.md「设计真值」表）。
DESIGN_LEVELS: dict[str, str] = {
    "t01": "missing",
    "t02": "thin",
    "t03": "covered",
    "t04": "missing",
    "t05": "missing",
    "t06": "covered",
    "t07": "covered",
    "t08": "thin",
    "t09": "covered",
    "t10": "covered",
}

# 每道题归属的知识点与分值（出处：同上表"往年试卷（题号:分值）"列）。
DESIGN_ASSIGNMENTS: dict[int, tuple[str, float]] = {
    1: ("t01", 5.0),
    2: ("t02", 10.0),
    3: ("t03", 10.0),
    4: ("t04", 15.0),
    5: ("t04", 10.0),
    6: ("t05", 5.0),
    7: ("t06", 5.0),
    8: ("t07", 10.0),
    9: ("t08", 10.0),
    10: ("t09", 10.0),
    11: ("t10", 10.0),
}

# 盲区第一名（出处：README.md —— "最大的盲区是 t04：……往年试卷却占 25 分"）。
BLIND_SPOT_TOP_TOPIC = "t04"
BLIND_SPOT_TOP_WEIGHT = 25.0


# ===========================================================================
# HTTP（仅标准库）
# ===========================================================================

class ApiError(Exception):
    pass


class HttpClient:
    def __init__(self, base_url: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, *,
                json_body: Optional[dict] = None,
                multipart: Optional[list[tuple[str, str, Optional[str],
                                               Optional[bytes]]]] = None,
                timeout: Optional[int] = None) -> dict | list | str:
        url = f"{self.base_url}{path}"
        headers = {"X-ExamRadar-Source": "auto"}
        data: Optional[bytes] = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif multipart is not None:
            boundary = uuid.uuid4().hex
            parts = []
            for field_name, filename, content_type, content in multipart:
                disp = f'form-data; name="{field_name}"'
                if filename is not None:
                    disp += f'; filename="{filename}"'
                parts.append(f"--{boundary}\r\n"
                             f"Content-Disposition: {disp}\r\n"
                             f"Content-Type: "
                             f"{content_type or 'application/octet-stream'}"
                             f"\r\n\r\n".encode("utf-8"))
                parts.append(content or b"")
                parts.append(b"\r\n")
            parts.append(f"--{boundary}--\r\n".encode("utf-8"))
            headers["Content-Type"] = \
                f"multipart/form-data; boundary={boundary}"
            data = b"".join(parts)

        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) \
                    as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()[:500].decode("utf-8", "replace")
            raise ApiError(f"HTTP {e.code} {method} {path}: {body}") from None
        except urllib.error.URLError as e:
            raise ApiError(
                f"无法连接 {self.base_url}（{method} {path}）：{e.reason}。\n"
                f"请确认服务已启动、地址正确。本地开发见 docs/DEPLOY.md；"
                f"Docker 部署先执行 docker compose up -d --build。"
            ) from None
        except OSError as e:
            raise ApiError(
                f"无法连接 {self.base_url}（{method} {path}）：{e}。"
                f"请确认服务已启动、地址正确。"
            ) from None

        if not raw:
            return ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.decode("utf-8", "replace")

    def get(self, path: str) -> dict | list:
        r = self.request("GET", path)
        if not isinstance(r, (dict, list)):
            raise ApiError(f"GET {path} 返回了非 JSON 内容")
        return r

    def post_json(self, path: str, body: dict) -> dict | list:
        r = self.request("POST", path, json_body=body)
        if not isinstance(r, (dict, list)):
            raise ApiError(f"POST {path} 返回了非 JSON 内容")
        return r

    def post_file(self, path: str, filename: str, content: bytes,
                  fields: dict[str, str]) -> dict:
        mime = "application/pdf" if filename.lower().endswith(".pdf") \
            else "text/markdown"
        multipart = [(k, None, None, v.encode("utf-8"))
                     for k, v in fields.items()]
        multipart.append(("file", filename, mime, content))
        r = self.request("POST", path, multipart=multipart)
        if not isinstance(r, dict):
            raise ApiError(f"POST {path} 返回了非 JSON 内容")
        return r

    def get_ok(self, path: str, timeout: Optional[int] = None) -> bool:
        """True when the endpoint answers 2xx."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET",
                                     headers={"X-ExamRadar-Source": "auto"})
        try:
            with urllib.request.urlopen(
                    req, timeout=timeout or self.timeout):
                return True
        except urllib.error.HTTPError as e:
            raise ApiError(f"HTTP {e.code} GET {path}") from None
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ApiError(
                f"无法连接 {self.base_url}（GET {path}）：{reason}。\n"
                f"请确认服务已启动、地址正确（PowerContext 就绪检查在 "
                f"{self.base_url}/health/ready）。"
            ) from None


# ===========================================================================
# 步骤结果的载体：每步一份 markdown 正文 + 若干检查项
# ===========================================================================

@dataclass
class Check:
    label: str
    passed: bool
    detail: str = ""


@dataclass
class StepResult:
    name: str
    body: str = ""
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


@dataclass
class Ctx:
    app: HttpClient
    pc: HttpClient
    # 首次导入记录的各文件块数（重复导入 / 二次运行核对用）
    chunk_counts: dict[str, int] = field(default_factory=dict)


def fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") or "0"
    return str(v)


def result_source(r: dict) -> str:
    parts = [r.get("document_name") or "?"]
    if r.get("question_no") is not None:
        parts.append(f"第{r['question_no']}题"
                     f"({fmt(r.get('points'))}分)")
    elif r.get("page") is not None:
        parts.append(f"第{r['page']}页")
    if r.get("heading"):
        parts.append(str(r["heading"]))
    return " · ".join(parts)


# ===========================================================================
# 步骤 1：健康检查
# ===========================================================================

def step_health(ctx: Ctx) -> StepResult:
    res = StepResult("健康检查")

    health = ctx.app.get("/api/health")
    for key in ("seekdb", "embedding", "powercontext"):
        entry = health.get(key) or {}
        ok = bool(entry.get("ok"))
        info = entry.get("model") or entry.get("detail") or ""
        res.checks.append(Check(
            f"应用 /api/health：{key} 可用",
            ok,
            info if info else ("ok" if ok else str(entry)),
        ))

    pc_ready = ctx.pc.get_ok("/health/ready", timeout=15)
    res.checks.append(Check(
        f"PowerContext /health/ready（{ctx.pc.base_url}）",
        pc_ready,
        "HTTP 200",
    ))
    return res


# ===========================================================================
# 步骤 2：导入样例资料
# ===========================================================================

def _import_all(ctx: Ctx) -> dict[str, dict]:
    out = {}
    for rel_path, kind in IMPORT_FILES:
        path = SAMPLES_DIR / rel_path
        if not path.exists():
            raise ApiError(f"样例文件不存在：{path}")
        resp = ctx.app.post_file(
            "/api/documents", path.name, path.read_bytes(),
            {"course_id": COURSE_ID, "doc_kind": kind},
        )
        out[rel_path] = resp
    return out


def _exam_questions(ctx: Ctx) -> list[dict]:
    """通过检索接口取全部试卷题目块（exam 语料仅 11 块，top_k=20 全部召回）。"""
    resp = ctx.app.post_json("/api/search", {
        "query": "数据库", "course_id": COURSE_ID,
        "doc_kinds": ["exam"], "top_k": 20,
    })
    return resp.get("results") or []


def step_import(ctx: Ctx) -> StepResult:
    res = StepResult("导入样例资料")

    first = _import_all(ctx)
    lines = ["| 文件 | 类型 | 块数 | 状态 |", "| --- | --- | --- | --- |"]
    for rel_path, kind in IMPORT_FILES:
        r = first[rel_path]
        n = r.get("chunk_count", 0)
        state = "skip（已导入）" if r.get("skipped") else "new"
        ctx.chunk_counts[rel_path] = n
        lines.append(f"| {Path(rel_path).name} | {kind} | {n} | {state} |")
    total = sum(ctx.chunk_counts.values())
    lines.append(f"| **合计（6 份）** | | **{total}** | |")
    res.body = ("\n".join(lines) + "\n\n各份资料块数以首次导入结果为准"
                "（README 未给出块数）；随后核对重复导入后不变。\n")

    docs = ctx.app.get(f"/api/documents?course_id={COURSE_ID}")
    by_name = {d.get("name"): d for d in docs}
    doc_checks_ok = len(docs) == len(IMPORT_FILES)
    for rel_path, _ in IMPORT_FILES:
        name = Path(rel_path).name
        d = by_name.get(name)
        if d is None:
            doc_checks_ok = False
            break
        if d.get("chunk_count") != ctx.chunk_counts[rel_path]:
            doc_checks_ok = False
            break
    res.checks.append(Check(
        "GET /api/documents 列出 6 份资料，块数与导入结果一致",
        doc_checks_ok,
        f"共 {len(docs)} 份，合计 {total} 块",
    ))

    # 试卷：11 题、合计 100 分
    questions = _exam_questions(ctx)
    by_no: dict[int, dict] = {}
    for q in questions:
        no = q.get("question_no")
        if no is not None:
            by_no[no] = q
    res.checks.append(Check(
        f"试卷切成 {EXAM_QUESTION_COUNT} 个题目块",
        len(by_no) == EXAM_QUESTION_COUNT,
        f"检索到 {len(by_no)} 个题号块",
    ))
    points_sum = sum(float(q.get("points") or 0) for q in by_no.values())
    res.checks.append(Check(
        f"试卷分值合计 {fmt(EXAM_TOTAL_POINTS)}",
        abs(points_sum - EXAM_TOTAL_POINTS) < 1e-6 and len(by_no) > 0,
        f"实际合计 {fmt(points_sum)} 分",
    ))

    # 重复导入幂等
    second = _import_all(ctx)
    idem_ok = True
    idem_detail = []
    for rel_path, _ in IMPORT_FILES:
        r = second[rel_path]
        ok = bool(r.get("skipped")) and \
            r.get("chunk_count") == ctx.chunk_counts[rel_path]
        idem_ok = idem_ok and ok
        idem_detail.append(f"{Path(rel_path).name}: "
                           f"{'skip' if r.get('skipped') else 'new'}"
                           f"/{r.get('chunk_count')} 块")
    res.checks.append(Check(
        "重复导入不产生新块（全部 skip，块数不变）",
        idem_ok,
        "；".join(idem_detail),
    ))
    return res


# ===========================================================================
# 步骤 3：6 条验收检索
# ===========================================================================

def _match_expectation(top: dict, spec: dict) -> tuple[bool, str]:
    doc = top.get("document_name") or ""
    if doc != spec["expect_doc"]:
        return False, f"文档不符：期望 {spec['expect_doc']}，实际 {doc}"
    if "expect_page" in spec:
        if top.get("page") != spec["expect_page"]:
            return False, (f"页码不符：期望第 {spec['expect_page']} 页，"
                           f"实际第 {top.get('page')} 页")
    if "expect_question_no" in spec:
        if top.get("question_no") != spec["expect_question_no"]:
            return False, (f"题号不符：期望第 {spec['expect_question_no']} 题，"
                           f"实际第 {top.get('question_no')} 题")
    if "expect_heading_contains" in spec:
        heading = top.get("heading") or ""
        if spec["expect_heading_contains"] not in heading:
            return False, (f"标题不符：期望含 "
                           f"「{spec['expect_heading_contains']}」，"
                           f"实际「{heading}」")
    if "expect_heading_contains_any" in spec:
        heading = top.get("heading") or ""
        if not any(s in heading
                   for s in spec["expect_heading_contains_any"]):
            return False, (f"标题不符：期望含 "
                           f"{' 或 '.join(spec['expect_heading_contains_any'])}，"
                           f"实际「{heading}」")
    return True, ""


def step_search(ctx: Ctx) -> StepResult:
    res = StepResult("验收检索")
    parts = []

    for spec in ACCEPTANCE_QUERIES:
        scope = "含 exam" if spec["include_exam"] else "默认范围"
        body = {
            "query": spec["query"],
            "course_id": COURSE_ID,
            "top_k": 10,
        }
        if spec["include_exam"]:
            body["include_exam"] = True
        resp = ctx.app.post_json("/api/search", body)
        results = resp.get("results") or []
        search_json = resp.get("search_json")
        actual_sql = resp.get("actual_sql")

        sub = [f"**检索**：`{spec['query']}`（{scope}）"
               f"— 期望第一条：{spec['note']}", ""]

        sql_ok = isinstance(search_json, dict) and bool(search_json) and \
            isinstance(actual_sql, str) and len(actual_sql.strip()) > 0
        sub.append(f"- 检索 JSON 与 GET_SQL 实际 SQL："
                   f"{'有' if sql_ok else '缺失'}"
                   f"（SQL {len(actual_sql) if isinstance(actual_sql, str) else 0} 字符）")

        top = results[0] if results else None
        if top is None:
            sub.append("- ❌ 无检索结果")
            res.checks.append(Check(
                f"「{spec['query']}」第一条命中期望出处", False, "无结果"))
            res.checks.append(Check(
                f"「{spec['query']}」返回检索 JSON 和实际 SQL", sql_ok, ""))
            parts.append("\n".join(sub) + "\n")
            continue

        kw = top.get("keyword_score")
        sem = top.get("semantic_score")
        kw_ok = kw is not None and float(kw) > 0
        sub.append(f"- 第一条关键词分：{fmt(kw)}（全文索引命中），"
                   f"语义分：{fmt(sem)}")

        matched, why = _match_expectation(top, spec)
        mark = "✅" if matched else "❌"
        sub.append(f"- {mark} 第一条出处：{result_source(top)}"
                   + (f"（{why}）" if not matched else ""))
        sub.append("")
        sub.append("| 名次 | 出处 | 关键词分 | 语义分 | RRF |")
        sub.append("| --- | --- | --- | --- | --- |")
        for r in results[:3]:
            sub.append(f"| {r.get('rank')} | {result_source(r)} "
                       f"| {fmt(r.get('keyword_score'))} "
                       f"| {fmt(r.get('semantic_score'))} "
                       f"| {fmt(r.get('score'))} |")
        parts.append("\n".join(sub) + "\n")

        res.checks.append(Check(
            f"「{spec['query']}」第一条命中期望出处（{spec['note']}）",
            matched, why))
        res.checks.append(Check(
            f"「{spec['query']}」第一条关键词分不为空", kw_ok,
            f"keyword_score={fmt(kw)}"))
        res.checks.append(Check(
            f"「{spec['query']}」返回检索 JSON 和实际 SQL", sql_ok, ""))

    res.body = "\n".join(parts)
    return res


# ===========================================================================
# 步骤 4：覆盖雷达
# ===========================================================================

def _coverage_items(payload: dict) -> list[dict]:
    return payload.get("items") or []


def _check_levels(items: list[dict], source: str) -> Check:
    mismatches = []
    for it in items:
        tid = it.get("topic_id")
        want = DESIGN_LEVELS.get(tid)
        got = it.get("coverage_level")
        if want != got:
            mismatches.append(f"{tid}: 期望 {want}，实际 {got}")
    return Check(
        f"{source}：10 个知识点判定 = 设计真值",
        len(items) == len(DESIGN_LEVELS) and not mismatches,
        "；".join(mismatches) if mismatches
        else f"{len(items)} 个知识点全部一致",
    )


def _check_terms(items: list[dict], source: str) -> Check:
    """每个考点词的证据：found=True 时 chunks 里有 doc/page/heading。"""
    bad = []
    for it in items:
        for te in it.get("terms") or []:
            if te.get("found"):
                chunks = te.get("chunks") or []
                if not chunks or any(
                        not c.get("doc") for c in chunks):
                    bad.append(f"{it['topic_id']}/{te.get('term')}")
            # found=False 的词不应有 chunks
            elif te.get("chunks"):
                bad.append(f"{it['topic_id']}/{te.get('term')}（未找到却有出处）")
    return Check(
        f"{source}：每个考点词的证据（出处含文档/页/标题）",
        not bad,
        "; ".join(bad[:5]) if bad else "全部考点词证据完整",
    )


def _check_assignments(items: list[dict], source: str) -> Check:
    got: dict[int, tuple[str, float]] = {}
    for it in items:
        for q in it.get("exam_questions") or []:
            got[int(q["question_no"])] = (
                it["topic_id"], float(q.get("points") or 0))
    mismatches = []
    for q_no, (want_topic, want_points) in DESIGN_ASSIGNMENTS.items():
        g = got.get(q_no)
        if g is None:
            mismatches.append(f"Q{q_no}: 缺失")
        elif g[0] != want_topic or abs(g[1] - want_points) > 1e-6:
            mismatches.append(f"Q{q_no}: 期望 {want_topic}"
                              f"({fmt(want_points)}分)，实际 {g[0]}"
                              f"({fmt(g[1])}分)")
    extra = set(got) - set(DESIGN_ASSIGNMENTS)
    for q_no in sorted(extra):
        mismatches.append(f"Q{q_no}: 多余归属 {got[q_no][0]}")
    return Check(
        f"{source}：11 道题归属与分值 = 设计真值",
        not mismatches,
        "；".join(mismatches) if mismatches
        else "11 道题归属（Q1→t01 … Q11→t10）与分值全部一致",
    )


def _check_blind_spot(items: list[dict], source: str,
                      by_position: bool = True) -> tuple[Check, Check]:
    if by_position:
        top = items[0] if items else {}
    else:
        # latest 在 05b 修复前按 topic_id 排序：核对"盲区分数最高的知识点"
        # 而非列表第一位，修复前后该检查都应通过。
        top = max(items, key=lambda it: float(it.get("blind_spot_score")
                                              or 0)) if items else {}
    top_ok = top.get("topic_id") == BLIND_SPOT_TOP_TOPIC and \
        abs(float(top.get("exam_weight") or 0) - BLIND_SPOT_TOP_WEIGHT) \
        < 1e-6
    weights = ", ".join(f"{it['topic_id']}={fmt(it.get('exam_weight'))}"
                        for it in items)
    top_check = Check(
        f"{source}：盲区第一名是 {BLIND_SPOT_TOP_TOPIC}"
        f"（{fmt(BLIND_SPOT_TOP_WEIGHT)} 分）",
        top_ok,
        f"实际第一名 {top.get('topic_id')}"
        f"（{fmt(top.get('exam_weight'))} 分，"
        f"blind {fmt(top.get('blind_spot_score'))}）；"
        f"各知识点权重：{weights}"
        if not top_ok else
        f"exam_weight={fmt(top.get('exam_weight'))}，"
        f"blind_spot_score={fmt(top.get('blind_spot_score'))}",
    )

    scores = [float(it.get("blind_spot_score") or 0) for it in items]
    ordered = scores == sorted(scores, reverse=True)
    order_check = Check(
        f"{source}：整体顺序按盲区分数从高到低",
        ordered,
        "顺序：" + " > ".join(
            f"{it['topic_id']}({fmt(it.get('blind_spot_score'))})"
            for it in items),
    )
    return top_check, order_check


def _check_reason_structure(items: list[dict], source: str) -> Check:
    """只核对理由的结构：提到了哪些考点词、有没有支撑字数。

    会话 05b 正在改措辞，故不比对原文。
    """
    bad = []
    for it in items:
        reason = it.get("reason") or ""
        if not reason:
            bad.append(f"{it['topic_id']}: 理由为空")
            continue
        for te in it.get("terms") or []:
            term = te.get("term") or ""
            if term and term not in reason:
                bad.append(f"{it['topic_id']}: 理由未提到考点词「{term}」")
        support_chars = it.get("support_chars") or 0
        if support_chars and str(support_chars) not in reason:
            bad.append(f"{it['topic_id']}: 理由未提到支撑字数（{support_chars}）")
    return Check(
        f"{source}：判定理由结构（提到各考点词和支撑字数）",
        not bad,
        "；".join(bad[:5]) if bad else "全部理由结构完整",
    )


def step_coverage(ctx: Ctx) -> StepResult:
    res = StepResult("覆盖雷达")

    syllabus_text = SYLLABUS_FILE.read_text(encoding="utf-8")
    analyze = ctx.app.post_json("/api/coverage/analyze", {
        "course_id": COURSE_ID, "syllabus_text": syllabus_text,
    })
    latest = ctx.app.get(f"/api/coverage/latest?course_id={COURSE_ID}")

    config = analyze.get("config") or {}
    res.checks.append(Check(
        "analyze 返回顶层 config（判定阈值）",
        bool(config) and "term_ratio_covered" in config
        and "support_chars_covered" in config,
        f"config={config}",
    ))

    items_a = _coverage_items(analyze)
    for c in (_check_levels(items_a, "analyze"),
              _check_terms(items_a, "analyze"),
              _check_assignments(items_a, "analyze"),
              _check_reason_structure(items_a, "analyze")):
        res.checks.append(c)
    top_c, order_c = _check_blind_spot(items_a, "analyze")
    res.checks.append(top_c)
    res.checks.append(order_c)

    items_l = _coverage_items(latest)
    res.checks.append(Check(
        "latest 与 analyze 的 run_id 一致（读到刚才的分析）",
        latest.get("run_id") == analyze.get("run_id"),
        f"analyze run_id={analyze.get('run_id')}，"
        f"latest run_id={latest.get('run_id')}",
    ))
    for c in (_check_levels(items_l, "latest"),
              _check_assignments(items_l, "latest")):
        res.checks.append(c)
    top_l, order_l = _check_blind_spot(items_l, "latest", by_position=False)
    res.checks.append(top_l)
    res.checks.append(order_l)

    # 报告正文：判定与归属总表
    by_topic = {it["topic_id"]: it for it in items_a}
    lines = ["analyze 判定总表（对照 samples/course-db/README.md 设计真值）：",
             "", "| 知识点 | 判定 | score | 考点词 | 支撑 | 权重 | 盲区 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for tid in sorted(by_topic):
        it = by_topic[tid]
        found = sum(1 for t in it.get("terms") or [] if t.get("found"))
        total = len(it.get("terms") or [])
        lines.append(
            f"| {tid} {it.get('topic_name')} | {it.get('coverage_level')} "
            f"（期望 {DESIGN_LEVELS[tid]}） | {fmt(it.get('coverage_score'))} "
            f"| {found}/{total} | "
            f"{it.get('support_chunks')} 段/{it.get('support_chars')} 字 "
            f"| {fmt(it.get('exam_weight'))} "
            f"| {fmt(it.get('blind_spot_score'))} |")
    lines += ["", "题目归属（analyze）：", ""]
    for q_no in sorted(DESIGN_ASSIGNMENTS):
        want_topic, want_points = DESIGN_ASSIGNMENTS[q_no]
        q = next((q for it in items_a
                  for q in it.get("exam_questions") or []
                  if q.get("question_no") == q_no), None)
        if q is None:
            lines.append(f"- Q{q_no}：缺失（期望 {want_topic}）")
        else:
            lines.append(f"- Q{q_no}（{fmt(want_points)} 分）→ "
                         f"{want_topic}，依据考点词："
                         f"{'、'.join(q.get('matched_terms') or []) or '（纯语义）'}")
    res.body = "\n".join(lines) + "\n"
    return res


# ===========================================================================
# 步骤 5：复习教练（会话 10 加入；examradar-ci 栈不配大模型，走无模型路径：
# missing 知识点往年原题自测 + thin 知识点考点词填空）
# ===========================================================================

SELF_RATINGS = ["会", "模糊", "不会"]


def _pc_revision_texts(pc: HttpClient, scope_id: str,
                       artifact_id: str) -> list[tuple[int, str]]:
    """掌握度卡片的 revision 历史：[(revision, text), ...] 升序。"""
    data = pc.get(
        f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/revisions")
    out = []
    for it in data.get("items") or []:
        rev = it.get("revision")
        if rev is None:
            continue
        rev_data = pc.get(
            f"/v1/scopes/{scope_id}/artifacts/atomic-memory/"
            f"{artifact_id}/revisions/{rev}")
        content = rev_data.get("content") or {}
        out.append((int(rev), content.get("text") or rev_data.get("text") or ""))
    out.sort()
    return out


def step_coach(ctx: Ctx) -> StepResult:
    res = StepResult("复习教练")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    learner = f"e2e教练{ts}"

    status = ctx.app.get("/api/coach/status")
    pc_ok = bool((status.get("powercontext") or {}).get("ok"))
    res.checks.append(Check(
        "/api/coach/status：PowerContext 可用", pc_ok,
        f"llm configured={bool((status.get('llm') or {}).get('configured'))}"
        f"（CI 栈不配大模型，走无模型路径）",
    ))

    # ---- 会话 1：新学习者，bootstrap 必须为空 ----
    s1 = ctx.app.post_json("/api/sessions/start",
                           {"learner": learner, "course_id": COURSE_ID})
    scope_id = s1.get("scope_id") or ""
    res.checks.append(Check(
        "新学习者开始会话：scope 已建、bootstrap 为空",
        bool(scope_id)
        and (s1.get("bootstrap") is None or not (s1.get("bootstrap") or {}).get("items"))
        and s1.get("opening_line") is None,
        f"scope_id={scope_id[:12]}…，bootstrap items="
        f"{(s1.get('bootstrap') or {}).get('items') or []}",
    ))
    sid1 = s1.get("session_id") or ""

    # ---- 第 1 题：自动选题应为盲区第一 t04（missing → 往年原题自测）----
    q1 = ctx.app.post_json("/api/quiz/next", {"session_id": sid1})
    res.checks.append(Check(
        "第 1 题自动选题 = 盲区第一 t04，missing 走往年原题自测",
        q1.get("topic_id") == BLIND_SPOT_TOP_TOPIC
        and q1.get("question_type") == "self"
        and "笔记里没有" in (q1.get("hint") or "")
        and "期末试卷" in ((q1.get("source") or {}).get("label") or "")
        and q1.get("self_ratings") == SELF_RATINGS,
        f"topic={q1.get('topic_id')}，题型={q1.get('question_type')}，"
        f"出处={((q1.get('source') or {}).get('label') or '')[:60]}",
    ))
    q1_text = (q1.get("question") or "").strip()

    # ---- 自测答错（不会）：box 1→1，写错题记忆 ----
    a1 = ctx.app.post_json("/api/quiz/answer",
                           {"question_id": q1["question_id"],
                            "self_rating": "不会"})
    m1 = a1.get("mastery") or {}
    res.checks.append(Check(
        "自测答错（不会）：correct=False，盒 1→1，错题记忆已写",
        a1.get("correct") is False and a1.get("box_before") == 1
        and a1.get("box_after") == 1
        and bool((a1.get("mistake_memory") or {}).get("artifact_id")),
        f"卡片 artifact={m1.get('artifact_id')} rev={m1.get('revision')}，"
        f"错题 artifact={(a1.get('mistake_memory') or {}).get('artifact_id')}",
    ))

    # ---- 第 2 题：同知识点再答对（会）：prepare 应召回刚才的错题 ----
    q2 = ctx.app.post_json("/api/quiz/next",
                           {"session_id": sid1, "topic_id": BLIND_SPOT_TOP_TOPIC})
    a2 = ctx.app.post_json("/api/quiz/answer",
                           {"question_id": q2["question_id"], "self_rating": "会"})
    m2 = a2.get("mastery") or {}
    mistake_hist = q2.get("mistake_history") or []
    res.checks.append(Check(
        "context/prepare 召回上次答错的错题（「你之前在这里错过」材料）",
        bool(mistake_hist) and any("【错题】" in (h.get("text") or "")
                                   for h in mistake_hist),
        f"召回 {len(mistake_hist)} 条，第一条："
        f"{((mistake_hist[0].get('text') or '')[:50]) if mistake_hist else '—'}",
    ))
    res.checks.append(Check(
        "同知识点答对（会）：盒 1→2，卡片 revision 递增",
        a2.get("correct") is True and a2.get("box_before") == 1
        and a2.get("box_after") == 2
        and bool(m2.get("artifact_id"))
        and int(m2.get("revision") or 0) > int(m1.get("revision") or 0),
        f"卡片 artifact={m2.get('artifact_id')}，rev "
        f"{m1.get('revision')}→{m2.get('revision')}",
    ))

    # ---- 第 3 题：thin 知识点（t08）考点词填空，故意答错 ----
    q3 = ctx.app.post_json("/api/quiz/next",
                           {"session_id": sid1, "question_type": "fill"})
    src3 = (q3.get("source") or {}).get("label") or ""
    res.checks.append(Check(
        "第 3 题自动选题 = t08（thin），填空题出考点词所在段落",
        q3.get("topic_id") == "t08" and q3.get("question_type") == "fill"
        and "＿＿＿" in (q3.get("question") or "")
        and "05-事务" in src3,
        f"topic={q3.get('topic_id')}，出处={src3[:60]}",
    ))
    a3 = ctx.app.post_json("/api/quiz/answer",
                           {"question_id": q3["question_id"],
                            "answer": "完全不会"})
    res.checks.append(Check(
        "填空题挖空的是考点词本身（判分回执里的正确答案）",
        a3.get("correct") is False
        and a3.get("expected_answer") in ("隔离级别", "MVCC"),
        f"expected_answer={a3.get('expected_answer')}（来自 t08 的考点词）",
    ))

    # ---- 结束会话 ----
    e1 = ctx.app.post_json("/api/sessions/end", {"session_id": sid1})
    res.checks.append(Check(
        "结束会话：3 题 1 对，时长按最后事件计，会话小结入记忆",
        e1.get("questions_asked") == 3 and e1.get("questions_correct") == 1
        and (e1.get("duration_seconds") or 0) >= 0
        and bool((e1.get("summary_memory") or {}).get("artifact_id")),
        f"duration={e1.get('duration_seconds')}s，"
        f"小结 artifact={(e1.get('summary_memory') or {}).get('artifact_id')}",
    ))

    # ---- 会话 2：开场白提到上次答错的知识点 ----
    s2 = ctx.app.post_json("/api/sessions/start",
                           {"learner": learner, "course_id": COURSE_ID})
    opening = s2.get("opening_line") or ""
    res.checks.append(Check(
        "新会话开场白提到上次答错的知识点（复习计划首行）",
        "错" in opening and ("函数依赖与范式" in opening
                             or "隔离级别与 MVCC" in opening),
        opening[:80] or "（空）",
    ))
    res.checks.append(Check(
        "会话 2 bootstrap 就绪（复习计划带 bootstrap-context 标签）",
        (s2.get("bootstrap") or {}).get("status") == "ready"
        and bool((s2.get("bootstrap") or {}).get("items")),
        f"bootstrap items={len(((s2.get('bootstrap') or {}).get('items') or []))}",
    ))

    # ---- PowerContext 直接核对：计划 handle / 标签 / 卡片 revision 历史 ----
    handle = ctx.pc.get(
        f"/v1/scopes/{scope_id}/artifact-handles/atomic-memory/review-plan")
    plan_artifact = ((handle.get("artifact") or handle) or {}).get("artifact_id")
    plan_info = e1.get("review_plan") or {}
    res.checks.append(Check(
        "复习计划 handle 指向会话结束时更新的 artifact",
        bool(plan_artifact) and plan_artifact == plan_info.get("artifact_id"),
        f"handle→{plan_artifact}，结束会话写入 rev={plan_info.get('revision')}",
    ))
    tags = ctx.pc.get(
        f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{plan_artifact}/tags"
    ).get("tags") or []
    res.checks.append(Check(
        "复习计划标签含 bootstrap-context（新会话开场白来源）",
        "bootstrap-context" in tags,
        f"tags={tags}",
    ))
    card_artifact = m2.get("artifact_id")
    revs = _pc_revision_texts(ctx.pc, scope_id, card_artifact)
    res.checks.append(Check(
        "掌握度卡片（t04）revision 历史：盒 1 → 盒 2 轨迹可见",
        len(revs) >= 2 and "盒 1" in revs[0][1] and "盒 2" in revs[-1][1],
        f"{len(revs)} 个 revision：" + "；".join(
            f"rev{r}→{_first_box(t)}" for r, t in revs),
    ))

    # ---- 使用记录：答题事件与会话时长入账，导出无学习者名字 ----
    stats = ctx.app.get(
        f"/api/usage/stats?course_id={COURSE_ID}&source=auto&tz=UTC")
    res.checks.append(Check(
        "使用记录（auto）：本次 3 次答题入账，会话数 ≥ 1",
        (stats.get("quiz_count") or 0) >= 3 and (stats.get("session_count") or 0) >= 1,
        f"答题 {stats.get('quiz_count')} 次，会话 {stats.get('session_count')} 个，"
        f"累计学习时长 {stats.get('study_minutes')} 分钟",
    ))
    export = ctx.app.request(
        "GET", f"/api/usage/export?course_id={COURSE_ID}&source=auto&format=json")
    export_text = export if isinstance(export, str) \
        else json.dumps(export, ensure_ascii=False)
    res.checks.append(Check(
        "使用记录导出（JSON）不含学习者名字（只有 8 位哈希）",
        export is not None and learner not in export_text,
        f"导出 {len(export_text)} 字节，未出现「{learner}」",
    ))

    # ---- 报告正文：题目原文 + PC 读写清单 + revision 历史 ----
    lines = ["复习教练全程（无大模型路径；学习者每次运行都用新名字，"
             "保证首会话 bootstrap 为空）：", ""]
    lines.append(f"- 学习者：{learner}（usage_events 里只有其 sha256 前 8 位哈希）")
    lines.append(f"- 会话 1：{sid1}，3 题（t04 自测答错 → t04 自测答对 → "
                 f"t08 填空答错），1 对；结束后新会话开场白：{opening}")
    lines += ["", "t04（missing）往年原题自测题目原文：", "",
              "```", q1_text, "```", ""]
    lines.append(f"- 出处：{(q1.get('source') or {}).get('label')}")
    lines.append(f"- 提示：{q1.get('hint')}")
    lines += ["", "t08（thin）填空题原文（挖空的是考点词，出处为找到考点词的段落）：",
              "", "```", (q3.get("question") or ""), "```", ""]
    lines.append(f"- 出处：{src3}；正确答案：{a3.get('expected_answer')}（t08 的考点词）")

    lines += ["", "这一路对 PowerContext 的关键读写"
                  "（接口、artifact id、revision、标签；由应用 API 响应与脚本"
                  "直接核对汇总）：", "",
              "| 方向 | 接口 | artifact / 说明 | revision / 标签 |",
              "| --- | --- | --- | --- |"]
    mistake1 = a1.get("mistake_memory") or {}
    mistake3 = a3.get("mistake_memory") or {}
    summary = e1.get("summary_memory") or {}
    rw = [
        ("写", "POST /v1/scopes（幂等 key examradar:learner:…）", scope_id, "Scope"),
        ("读", "POST /v1/context/bootstrap（会话 1 开始）", "—（空，第一次复习）", "items=[]"),
        ("读", "POST /v1/context/prepare（t04 出题前）", "—（尚无错题）", "history=[]"),
        ("写", "POST artifacts + PUT tags + PUT handle（t04 掌握度卡片）",
         m1.get("artifact_id"), f"rev {m1.get('revision')}；tags examradar/"
         f"type-mastery/topic-t04"),
        ("写", "POST /v1/memory/remember + PUT tags（t04 错题）",
         mistake1.get("artifact_id"), f"rev {mistake1.get('revision')}；"
         f"tags examradar/type-mistake/topic-t04"),
        ("读", "POST /v1/context/prepare（t04 再出题前）",
         mistake1.get("artifact_id"), f"召回错题 {len(mistake_hist)} 条"),
        ("写", "PUT artifacts（If-Match，t04 卡片）", m2.get("artifact_id"),
         f"rev {m2.get('revision')}（盒 1→2）"),
        ("写", "POST artifacts + tags + handle（t08 掌握度卡片）",
         (a3.get("mastery") or {}).get("artifact_id"),
         f"rev {(a3.get('mastery') or {}).get('revision')}"),
        ("写", "POST /v1/memory/remember + PUT tags（t08 错题）",
         mistake3.get("artifact_id"), f"rev {mistake3.get('revision')}"),
        ("写", "PUT artifacts（If-Match，复习计划）", plan_info.get("artifact_id"),
         f"rev {plan_info.get('revision')}；tags {','.join(tags)}"),
        ("写", "POST /v1/memory/remember + PUT tags（会话小结）",
         summary.get("artifact_id"), f"rev {summary.get('revision')}"),
        ("读", "POST /v1/context/bootstrap（会话 2 开始）",
         plan_info.get("artifact_id"), "开场白 = 计划首行"),
        ("读", "GET artifact-handles / tags / revisions（脚本核对）",
         plan_info.get("artifact_id"), f"handle→rev {plan_info.get('revision')}"),
    ]
    for direction, api, artifact, note in rw:
        lines.append(f"| {direction} | {api} | {artifact} | {note} |")

    lines += ["", f"掌握度卡片（t04，{card_artifact}）revision 历史：", ""]
    for r, text in revs:
        lines.append(f"- rev {r}：{text.splitlines()[0]}")
    if mistake_hist:
        lines += ["", "context/prepare 召回的错题（第 2 题出题前）：", ""]
        for h in mistake_hist[:3]:
            lines.append(f"- {((h.get('text') or '').splitlines() or ['—'])[0]}")
    res.body = "\n".join(lines) + "\n"

    ctx.app.post_json("/api/sessions/end", {"session_id": s2.get("session_id")})
    return res


def _first_box(text: str) -> str:
    for line in text.splitlines():
        if "盒" in line:
            return line.strip()
    return text[:40] or "（空）"


# ===========================================================================
# 步骤表
# ===========================================================================

STEPS: list[tuple[str, Callable[[Ctx], StepResult]]] = [
    ("健康检查", step_health),
    ("导入样例资料", step_import),
    ("验收检索", step_search),
    ("覆盖雷达", step_coverage),
    ("复习教练", step_coach),
]


def render_report(app_url: str, pc_url: str, results: list[StepResult],
                  error: Optional[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = ["# ExamRadar 端到端验证报告", "",
             f"- 时间：{now}",
             f"- 应用地址：{app_url}",
             f"- PowerContext 地址：{pc_url}",
             f"- 课程：{COURSE_ID}（samples/course-db）",
             f"- 期望值出处：samples/course-db/README.md（设计真值）、"
             f"dev-records/prompts/02-m1-ingest-search.md（验收检索表）",
             "", "## 总览", "",
             "| 步骤 | 结果 |", "| --- | --- |"]
    for r in results:
        mark = "✅" if r.passed else "❌"
        lines.append(f"| {r.name} | {mark} |")
    all_pass = all(r.passed for r in results) and error is None
    lines += ["", f"**总结：{'全部通过 ✅' if all_pass else '存在未通过项 ❌'}**", ""]

    for r in results:
        lines += ["---", "", f"## {r.name}", ""]
        if r.checks:
            lines += ["| 检查项 | 结果 | 说明 |", "| --- | --- | --- |"]
            for c in r.checks:
                mark = "✅" if c.passed else "❌"
                detail = c.detail.replace("\n", " ")
                lines.append(f"| {c.label} | {mark} | {detail} |")
            lines.append("")
        if r.body:
            lines += [r.body, ""]

    if error:
        lines += ["---", "", "## 执行中断", "", f"```\n{error}\n```", ""]
        lines += ["**总结：存在未通过项 ❌**（执行中断，未能完成全部步骤）", ""]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="ExamRadar 端到端验证（标准库实现，无需第三方依赖）")
    parser.add_argument(
        "--app-url", default="http://127.0.0.1:18800",
        help="应用地址（本地开发默认 18800，Docker CI 栈用 "
             "http://127.0.0.1:18807）")
    parser.add_argument(
        "--pc-url", default="http://127.0.0.1:18806",
        help="PowerContext 地址（CI 栈默认 18806，本地开发栈为 18801）")
    parser.add_argument(
        "--report", default=str(Path(__file__).resolve().parent.parent
                                / "docs" / "validation" / "e2e-report.md"),
        help="Markdown 报告输出路径")
    args = parser.parse_args(argv)

    app = HttpClient(args.app_url)
    pc = HttpClient(args.pc_url)
    ctx = Ctx(app=app, pc=pc)

    results: list[StepResult] = []
    error: Optional[str] = None
    for name, func in STEPS:
        try:
            results.append(func(ctx))
        except ApiError as e:
            error = f"步骤「{name}」中止：{e}"
            print(f"ERROR: {error}", file=sys.stderr)
            break
        mark = "✅" if results[-1].passed else "❌"
        print(f"{mark} {name}"
              + ("" if results[-1].passed else "（有未通过检查项）"))

    report = render_report(args.app_url, args.pc_url, results, error)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"报告已写入 {report_path}")

    if error is not None:
        return 1
    if not all(r.passed for r in results):
        failed = [c.label for r in results for c in r.checks if not c.passed]
        print("未通过：", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
