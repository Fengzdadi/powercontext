"""Search endpoint: hybrid search with RRF."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from ..seekdb import hybrid_search, insert_usage_event, get_document_names
from ..embedding import get_embedding_model

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    course_id: str
    doc_kinds: Optional[list[str]] = None
    top_k: int = 10
    include_exam: bool = False
    with_answer: bool = False  # 有大模型时生成带 [n] 引用的回答


def _generate_llm_answer(query: str, results: list[dict]) -> Optional[dict]:
    """基于检索结果生成带 [n] 引用的回答；[n] 越界时在代码里校验剔除。"""
    from ..llm import LLMError, get_llm_client
    llm = get_llm_client()
    if not llm.configured or not results:
        return None
    context_blocks = []
    for i, r in enumerate(results[:5], start=1):
        src = " · ".join(filter(None, [
            r.get("document_name"),
            f"第{r['page']}页" if r.get("page") else None,
            f"第{r['question_no']}题" if r.get("question_no") else None,
            r.get("heading"),
        ]))
        context_blocks.append(f"[{i}] {src}\n{r.get('content', '')}")
    system = "你是数据库课程的助教。只依据给定的资料回答，不要编造。/no_think"
    user = (
        f"问题：{query}\n\n资料：\n" + "\n\n".join(context_blocks) + "\n\n"
        "请依据资料回答问题。引用资料时在句末标注编号，如 [1] 或 [2][3]。"
        "只能引用上面给出的编号，不要使用其他编号。"
        "如果资料不足以回答，请明确说明。/no_think"
    )
    try:
        text = llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.2)
    except LLMError as e:
        return {"answer": None, "error": str(e)}
    # 代码里再校验一遍：剔除越界的引用编号
    valid = set(range(1, len(results[:5]) + 1))
    import re as _re
    def _check(m):
        n = int(m.group(1))
        return m.group(0) if n in valid else ""
    text = _re.sub(r"\[(\d+)\]", _check, text)
    return {"answer": text, "context_count": len(results[:5])}


@router.post("/api/search")
def search(req: SearchRequest, x_examradar_source: Optional[str] = Header(None)):
    source = "auto" if x_examradar_source == "auto" else "real"

    doc_kinds = req.doc_kinds
    if doc_kinds is None:
        doc_kinds = ["notes", "slides", "paper"]
        if req.include_exam:
            doc_kinds.append("exam")

    model = get_embedding_model()
    query_vector = model.embed_one(req.query, is_query=True)

    hits, search_json, actual_sql = hybrid_search(
        query_text=req.query,
        query_vector=query_vector,
        course_id=req.course_id,
        doc_kinds=doc_kinds,
        top_k=req.top_k,
    )

    doc_names = get_document_names(req.course_id)

    results = []
    for i, hit in enumerate(hits):
        results.append({
            "rank": i + 1,
            "content": hit.get("content", ""),
            "heading": hit.get("heading"),
            "page": hit.get("page"),
            "question_no": hit.get("question_no"),
            "points": hit.get("points"),
            "document_id": hit.get("document_id"),
            "document_name": doc_names.get(hit.get("document_id")),
            "keyword_score": hit.get("_keyword_score"),
            "semantic_score": hit.get("_semantic_score"),
            "keyword_rank": hit.get("_keyword_rank"),
            "semantic_rank": hit.get("_semantic_rank"),
            "score": hit.get("_score"),
        })

    llm_answer = _generate_llm_answer(req.query, results) if req.with_answer else None

    insert_usage_event(req.course_id, source, "search", {
        "query": req.query,
        "top_k": req.top_k,
        "result_count": len(results),
        "doc_kinds": doc_kinds,
        "llm_answer": bool(llm_answer and llm_answer.get("answer")),
    })

    return {
        "results": results,
        "llm_answer": llm_answer,
        "search_json": json.loads(search_json) if isinstance(search_json, str) else search_json,
        "actual_sql": actual_sql,
    }
