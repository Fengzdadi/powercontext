"""Search endpoint: hybrid search with RRF."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from ..seekdb import hybrid_search, insert_usage_event
from ..embedding import get_embedding_model

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    course_id: str
    doc_kinds: Optional[list[str]] = None
    top_k: int = 10
    include_exam: bool = False


@router.post("/api/search")
def search(req: SearchRequest, x_examradar_source: Optional[str] = Header(None)):
    source = "auto" if x_examradar_source == "auto" else "real"

    doc_kinds = req.doc_kinds
    if doc_kinds is None:
        doc_kinds = ["notes", "slides", "paper"]
        if req.include_exam:
            doc_kinds.append("exam")

    model = get_embedding_model()
    query_vector = model.embed_one(req.query)

    hits, search_json, actual_sql = hybrid_search(
        query_text=req.query,
        query_vector=query_vector,
        course_id=req.course_id,
        doc_kinds=doc_kinds,
        top_k=req.top_k,
    )

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
            "keyword_score": hit.get("_keyword_score"),
            "semantic_score": hit.get("_semantic_score"),
            "keyword_rank": hit.get("_keyword_rank"),
            "semantic_rank": hit.get("_semantic_rank"),
            "score": hit.get("_score"),
        })

    insert_usage_event(req.course_id, source, "search", {
        "query": req.query,
        "top_k": req.top_k,
        "result_count": len(results),
        "doc_kinds": doc_kinds,
    })

    return {
        "results": results,
        "search_json": json.loads(search_json) if isinstance(search_json, str) else search_json,
        "actual_sql": actual_sql,
    }
