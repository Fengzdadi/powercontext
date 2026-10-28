"""court-api — 喵青天·鸡毛蒜皮法庭的数据服务。

Dify 的 HTTP 请求节点通过它读写 seekdb：立案登记、判例与法条混合检索、宣判后把案件编入判例集、本院统计。
每个接口同时返回结构化字段和可直接放进提示词 / 回复里的 *_text 字段，让工作流里的代码节点尽量简单。
"""

from __future__ import annotations

import logging
import re
import unicodedata
from contextlib import asynccontextmanager
from itertools import zip_longest
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .embedding import Embedder
from .store import DEFENDANT_TYPES, OUTCOME_LABELS, TYPE_LABELS, CourtStore, chinese_number

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("court.api")

embedder = Embedder()
store = CourtStore(embedder)


@asynccontextmanager
async def lifespan(_: FastAPI):
    embedder.load()
    store.wait_until_ready()
    store.init_schema()
    added = store.load_seed()
    log.info("court ready: seed added %s, seekdb %s", added, store.ping())
    yield


app = FastAPI(title="喵青天·鸡毛蒜皮法庭 court-api", version="1.0.0", lifespan=lifespan)


def clean(text: str | None, limit: int) -> str:
    # NFC keeps full-width Chinese punctuation (case numbers use （）), unlike NFKC.
    text = unicodedata.normalize("NFC", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def clean_name(text: str | None, fallback: str) -> str:
    return clean(text, 20) or fallback


# ---------------------------------------------------------------------- text renderings
def precedent_line(i: int, p: dict[str, Any]) -> str:
    origin = "玩家判例" if p.get("source") == "player" else "种子判例"
    return (f"[判例{chinese_number(i)}]{p['case_no']}《{p['title']}》（{origin}，{OUTCOME_LABELS.get(p.get('outcome'), '已判')}）\n"
            f"  案情：{p['grievance']}\n  判决：{p.get('verdict') or ''}\n  法官金句：{p.get('judge_quote') or ''}")


def statute_line(s: dict[str, Any]) -> str:
    return f"《鸡毛蒜皮法典》第{chinese_number(int(s['article_no']))}条【{s['title']}】{s['content']}"


def search_markdown(query: str, hits: list[dict[str, Any]]) -> str:
    if not hits:
        return f"🔎 判例检索「{query}」：判例集里还没有相似的案子——你可以亲自起诉，开创先例！"
    lines = [f"🔎 判例检索「{query}」—— seekdb 混合检索（全文 + 向量）命中 {len(hits)} 件："]
    for i, p in enumerate(hits, start=1):
        origin = f"玩家「{p['plaintiff']}」的判例" if p.get("source") == "player" else "种子判例"
        lines.append(f"{i}. **{p['case_no']}《{p['title']}》**（{origin} · {OUTCOME_LABELS.get(p.get('outcome'), '已判')}）")
        lines.append(f"   - 判决：{p.get('verdict') or ''}")
        if p.get("judge_quote"):
            lines.append(f"   - 喵青天：「{p['judge_quote']}」")
    return "\n".join(lines)


# ---------------------------------------------------------------------- request models
class FileCaseRequest(BaseModel):
    player: str = Field(..., description="原告（玩家昵称）")
    defendant: str = Field(..., description="被告")
    defendant_type: str = "other"
    grievance: str = Field(..., description="案情")
    demand: str = ""
    conversation_id: str = ""


class SearchRequest(BaseModel):
    query: str
    defendant_type: str = ""
    exclude_case_no: str = ""
    precedent_k: int = Field(3, ge=0, le=10)
    statute_k: int = Field(2, ge=0, le=10)


class VerdictRequest(BaseModel):
    case_no: str
    title: str = ""
    verdict: str
    outcome: str = "split"
    judge_quote: str = ""
    tags: str = ""


class CaseRef(BaseModel):
    case_no: str


# ---------------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict[str, Any]:
    try:
        seekdb = {"status": "ok", **store.ping()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"seekdb unavailable: {exc}") from exc
    return {
        "status": "ok",
        "seekdb": seekdb,
        "embedding": {"model": embedder.model_name, "dim": embedder.dim, "ready": embedder.ready, "error": embedder.error},
        "hybrid_search": "DBMS_HYBRID_SEARCH" if store.hybrid_native else "SQL fallback",
    }


@app.post("/api/cases")
def file_case(req: FileCaseRequest) -> dict[str, Any]:
    player = clean_name(req.player, "无名氏")
    defendant = clean_name(req.defendant, "不明物体")
    dtype = req.defendant_type if req.defendant_type in DEFENDANT_TYPES else "other"
    grievance = clean(req.grievance, 600) or f"{player}对{defendant}很生气。"
    case = store.file_case(player, defendant, dtype, grievance, clean(req.demand, 200),
                           clean(req.conversation_id, 64))
    log.info("seekdb write: filed %s %s (type=%s)", case["case_no"], case["title"], dtype)
    return {**case, "player": player, "defendant": defendant, "defendant_type": dtype,
            "defendant_type_label": TYPE_LABELS[dtype], "grievance": grievance,
            "docket_text": f"📜 立案登记：{case['case_no']}《{case['title']}》（被告类型：{TYPE_LABELS[dtype]}）"}


@app.post("/api/search")
def search(req: SearchRequest) -> dict[str, Any]:
    query = clean(req.query, 300)
    dtype = req.defendant_type if req.defendant_type in DEFENDANT_TYPES else ""
    precedents: list[dict[str, Any]] = []
    if req.precedent_k:
        # Interleave the best matches against the same kind of defendant (a structured filter inside the
        # hybrid search) with the best matches overall, so a similar story is cited even when the
        # defendant was classified differently.
        exclude = req.exclude_case_no or None
        same_kind = store.search_cases(query, req.precedent_k, dtype, exclude) if dtype else []
        overall = store.search_cases(query, req.precedent_k, None, exclude)
        seen: set[str] = set()
        for p in (p for pair in zip_longest(same_kind, overall) for p in pair if p):
            if p["case_no"] not in seen and len(precedents) < req.precedent_k:
                seen.add(p["case_no"])
                precedents.append(p)
    statutes = store.search_statutes(query, req.statute_k) if req.statute_k else []
    log.info("seekdb hybrid search q=%r type=%s -> precedents %s, statutes %s", query, dtype or "*",
             [p["case_no"] for p in precedents], [s["article_no"] for s in statutes])
    return {
        "query": query,
        "mode": "hybrid" if embedder.ready else "fulltext",
        "precedents": precedents,
        "statutes": statutes,
        "precedents_text": "\n".join(precedent_line(i, p) for i, p in enumerate(precedents, start=1)) or "（判例集中暂无相似判例）",
        "statutes_text": "\n".join(statute_line(s) for s in statutes) or "（法典中暂无直接相关条文）",
        "citations_text": "；".join([p["case_no"] for p in precedents]
                                    + [f"《法典》第{chinese_number(int(s['article_no']))}条" for s in statutes]),
        "markdown": search_markdown(query, precedents),
    }


@app.post("/api/cases/verdict")
def record_verdict(req: VerdictRequest) -> dict[str, Any]:
    outcome = req.outcome if req.outcome in ("plaintiff", "defendant", "split") else "split"
    result = store.record_verdict(clean(req.case_no, 64), clean(req.title, 120), clean(req.verdict, 1200),
                                  outcome, clean(req.judge_quote, 200), clean(req.tags, 120))
    if result is None:
        raise HTTPException(404, f"case {req.case_no} not found")
    log.info("seekdb write: verdict %s outcome=%s -> now %d precedents", result["case_no"], outcome,
             result["precedent_count"])
    return {**result, "outcome": outcome, "outcome_label": OUTCOME_LABELS[outcome],
            "archived_text": f"📚 本案已编入《鸡毛蒜皮判例集》（seekdb）：{result['case_no']}《{result['title']}》。"
                             f"判例集现有 {result['precedent_count']} 件，以后的相似案件会援引它。"}


@app.post("/api/cases/withdraw")
def withdraw(req: CaseRef) -> dict[str, Any]:
    ok = store.withdraw(clean(req.case_no, 64))
    log.info("seekdb write: withdraw %s -> %s", req.case_no, ok)
    return {"case_no": req.case_no, "withdrawn": ok}


@app.get("/api/cases/{case_no}")
def get_case(case_no: str) -> dict[str, Any]:
    case = store.get_case(case_no)
    if case is None:
        raise HTTPException(404, f"case {case_no} not found")
    return case


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    s = store.stats()
    total_outcomes = sum(s["outcomes"].values()) or 1
    win_rate = round(100 * s["outcomes"].get("plaintiff", 0) / total_outcomes)
    lines = [
        "📊 **鸡毛蒜皮法庭 · 本院公告**（数据来自 seekdb 实时统计）",
        f"- 《鸡毛蒜皮判例集》共收录 **{s['precedents_total']}** 件判例，其中 **{s['precedents_player']}** 件由玩家诉讼产生；"
        f"《法典》共 {s['statutes']} 条；尚在审理中的案件 {s['pending_cases']} 件",
        f"- 原告胜诉率 {win_rate}%（原告胜 {s['outcomes'].get('plaintiff', 0)} / 被告胜 {s['outcomes'].get('defendant', 0)}"
        f" / 各打五十大板 {s['outcomes'].get('split', 0)}）",
        "- 最常被告：" + "、".join(f"{d['defendant']}（{d['n']} 次）" for d in s["top_defendants"]),
    ]
    if s["top_plaintiffs"]:
        lines.append("- 本院常客：" + "、".join(f"{p['plaintiff']}（{p['n']} 案）" for p in s["top_plaintiffs"]))
    for c in s["recent_player_cases"]:
        lines.append(f"- 最新宣判：{c['case_no']}《{c['title']}》—— {OUTCOME_LABELS.get(c['outcome'], '')}")
    return {**s, "plaintiff_win_rate": win_rate, "markdown": "\n".join(lines)}
