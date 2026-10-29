"""Coverage analysis: per-topic evidence, exam weight, blind spots."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .config import get_settings
from .seekdb import (
    hybrid_search, get_document_names, get_connection, save_coverage_run,
    get_latest_coverage, insert_usage_event,
)
from .embedding import get_embedding_model
from .syllabus import Topic


@dataclass
class Evidence:
    content: str
    heading: Optional[str]
    page: Optional[int]
    document_id: Optional[int]
    document_name: Optional[str]
    semantic_score: Optional[float]
    keyword_score: Optional[float]
    semantic_rank: Optional[int]
    keyword_rank: Optional[int]
    rrf_score: Optional[float]


@dataclass
class ExamQuestion:
    question_no: int
    points: float
    topic_id: str
    similarity: float


@dataclass
class TopicResult:
    topic_id: str
    topic_name: str
    keywords: list[str]
    coverage_level: str
    coverage_score: float
    best_evidence: Optional[Evidence]
    exam_weight: float
    exam_questions: list[ExamQuestion]
    blind_spot_score: float
    reason: str
    all_evidence: list[Evidence] = field(default_factory=list)


def _normalize_kw(kw_score: float, kw_scale: float) -> float:
    return min(kw_score / kw_scale, 1.0) if kw_score and kw_score > 0 else 0.0


def _compute_coverage_score(sem_score: Optional[float], kw_score: Optional[float],
                            kw_scale: float) -> float:
    s = get_settings()
    sem = sem_score if sem_score is not None else 0.0
    kw_norm = _normalize_kw(kw_score or 0.0, kw_scale)
    return 0.6 * sem + 0.4 * kw_norm


def _judge_level(score: float) -> str:
    s = get_settings()
    if score >= s.coverage_t_covered:
        return "covered"
    if score >= s.coverage_t_thin:
        return "thin"
    return "missing"


def _build_reason(level: str, score: float, evidence: Optional[Evidence],
                  topic_name: str) -> str:
    s = get_settings()
    if level == "missing":
        return f"在笔记、课件和阅读材料里都没有找到关于「{topic_name}」的有效覆盖"
    if evidence is None:
        return f"没有找到关于「{topic_name}」的内容"
    sem_str = f"{evidence.semantic_score:.4f}" if evidence.semantic_score is not None else "—"
    kw_str = f"{evidence.keyword_score:.2f}" if evidence.keyword_score is not None else "—"
    if level == "covered":
        gap = s.coverage_t_covered - score
        return (
            f"最强证据：{evidence.document_name or ''}"
            f"{' 第' + str(evidence.page) + '页' if evidence.page else ''}"
            f"{' · ' + evidence.heading if evidence.heading else ''}，"
            f"语义分 {sem_str}，关键词分 {kw_str}，"
            f"综合 {score:.4f}（距 covered 阈值 {s.coverage_t_covered} 还有 {gap:.4f}）"
        )
    gap = score - s.coverage_t_thin
    return (
        f"最强证据：{evidence.document_name or ''}"
        f"{' 第' + str(evidence.page) + '页' if evidence.page else ''}"
        f"{' · ' + evidence.heading if evidence.heading else ''}，"
        f"语义分 {sem_str}，关键词分 {kw_str}，"
        f"综合 {score:.4f}（距 covered 阈值 {s.coverage_t_covered} 差 {s.coverage_t_covered - score:.4f}，"
        f"距 thin 阈值 {s.coverage_t_thin} 上方 {gap:.4f}）"
    )


def _search_topic(topic: Topic, course_id: str, top_k: int = 5) -> list[Evidence]:
    model = get_embedding_model()
    query_vec = model.embed_one(topic.search_query, is_query=True)
    hits, _, _ = hybrid_search(
        query_text=topic.search_query,
        query_vector=query_vec,
        course_id=course_id,
        doc_kinds=["notes", "slides", "paper"],
        top_k=top_k,
    )
    doc_names = get_document_names(course_id)
    evidence_list: list[Evidence] = []
    for hit in hits:
        evidence_list.append(Evidence(
            content=hit.get("content", ""),
            heading=hit.get("heading"),
            page=hit.get("page"),
            document_id=hit.get("document_id"),
            document_name=doc_names.get(hit.get("document_id")),
            semantic_score=hit.get("_semantic_score"),
            keyword_score=hit.get("_keyword_score"),
            semantic_rank=hit.get("_semantic_rank"),
            keyword_rank=hit.get("_keyword_rank"),
            rrf_score=hit.get("_score"),
        ))
    return evidence_list


def _assign_exam_questions(course_id: str, topics: list[Topic]) -> dict[str, list[ExamQuestion]]:
    """Assign each exam question to the most relevant topic using cosine similarity."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content, heading, question_no, points, embedding "
                "FROM chunks WHERE course_id = %s AND doc_kind = 'exam' "
                "AND question_no IS NOT NULL ORDER BY question_no",
                (course_id,),
            )
            exam_chunks = cur.fetchall()
    finally:
        conn.close()

    if not exam_chunks:
        return {t.topic_id: [] for t in topics}

    import numpy as np
    model = get_embedding_model()
    topic_embeddings = {}
    for t in topics:
        vec = model.embed_one(t.search_query, is_query=True)
        topic_embeddings[t.topic_id] = np.array(vec)

    assignment: dict[str, list[ExamQuestion]] = {t.topic_id: [] for t in topics}

    for chunk in exam_chunks:
        q_no = chunk["question_no"]
        pts = float(chunk.get("points") or 0)
        emb_raw = chunk.get("embedding")
        if emb_raw is None:
            continue
        if isinstance(emb_raw, str):
            emb_raw = json.loads(emb_raw)
        q_vec = np.array([float(x) for x in emb_raw])

        best_topic = None
        best_sim = -1.0
        for t in topics:
            t_vec = topic_embeddings[t.topic_id]
            cos_sim = float(np.dot(q_vec, t_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(t_vec)))
            sim = (1 + cos_sim) / 2
            if sim > best_sim:
                best_sim = sim
                best_topic = t.topic_id

        if best_topic:
            assignment[best_topic].append(ExamQuestion(
                question_no=q_no, points=pts,
                topic_id=best_topic, similarity=best_sim,
            ))

    return assignment


def analyze(course_id: str, syllabus_text: str, source: str = "real",
            session_id: Optional[str] = None) -> dict:
    """Run full coverage analysis. Returns the result dict and persists it."""
    from .syllabus import parse_syllabus
    topics = parse_syllabus(syllabus_text)
    if not topics:
        raise ValueError("没有从考试范围中解析出知识点")

    s = get_settings()
    kw_scale = s.coverage_kw_scale

    topic_results: list[TopicResult] = []
    exam_assignment = _assign_exam_questions(course_id, topics)

    for topic in topics:
        evidence_list = _search_topic(topic, course_id)
        best = evidence_list[0] if evidence_list else None
        sem = best.semantic_score if best else None
        kw = best.keyword_score if best else None
        score = _compute_coverage_score(sem, kw, kw_scale)
        level = _judge_level(score)
        reason = _build_reason(level, score, best, topic.name)

        qs = exam_assignment.get(topic.topic_id, [])
        weight = sum(q.points for q in qs)
        blind = weight * (1.0 - score)

        topic_results.append(TopicResult(
            topic_id=topic.topic_id,
            topic_name=topic.name,
            keywords=topic.keywords,
            coverage_level=level,
            coverage_score=score,
            best_evidence=best,
            exam_weight=weight,
            exam_questions=qs,
            blind_spot_score=blind,
            reason=reason,
            all_evidence=evidence_list,
        ))

    topic_results.sort(key=lambda t: -t.blind_spot_score)

    config_json = json.dumps({
        "t_covered": s.coverage_t_covered,
        "t_thin": s.coverage_t_thin,
        "kw_scale": kw_scale,
    })
    topics_json = json.dumps(
        [{"id": t.topic_id, "name": t.name, "keywords": t.keywords} for t in topics],
        ensure_ascii=False,
    )

    items = []
    for tr in topic_results:
        best = tr.best_evidence
        items.append({
            "topic_id": tr.topic_id,
            "topic_name": tr.topic_name,
            "keywords_json": json.dumps(tr.keywords, ensure_ascii=False),
            "coverage_level": tr.coverage_level,
            "coverage_score": tr.coverage_score,
            "best_sem_score": best.semantic_score if best else None,
            "best_kw_score": best.keyword_score if best else None,
            "best_content": best.content if best else None,
            "best_heading": best.heading if best else None,
            "best_page": best.page if best else None,
            "best_doc_name": best.document_name if best else None,
            "exam_weight": tr.exam_weight,
            "exam_qs_json": json.dumps(
                [{"question_no": q.question_no, "points": q.points, "similarity": q.similarity}
                 for q in tr.exam_questions],
                ensure_ascii=False,
            ),
            "blind_spot_score": tr.blind_spot_score,
            "reason": tr.reason,
        })

    run_id = save_coverage_run(course_id, source, topics_json, config_json, items)

    insert_usage_event(course_id, source, "analyze", {
        "run_id": run_id,
        "topic_count": len(topics),
        "syllabus_text": syllabus_text[:500],
    }, session_id=session_id)

    return _format_result(run_id, course_id, topic_results, topics_json, config_json)


def _format_result(run_id: int, course_id: str,
                   topic_results: list[TopicResult],
                   topics_json: str, config_json: str) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "run_id": run_id,
        "course_id": course_id,
        "created_at": now.replace(tzinfo=timezone.utc).isoformat(),
        "topics": json.loads(topics_json),
        "config": json.loads(config_json),
        "items": [_format_topic_result(tr) for tr in topic_results],
    }


def _format_topic_result(tr: TopicResult) -> dict:
    best = tr.best_evidence
    return {
        "topic_id": tr.topic_id,
        "topic_name": tr.topic_name,
        "keywords": tr.keywords,
        "coverage_level": tr.coverage_level,
        "coverage_score": tr.coverage_score,
        "best_evidence": {
            "content": best.content,
            "heading": best.heading,
            "page": best.page,
            "document_name": best.document_name,
            "semantic_score": best.semantic_score,
            "keyword_score": best.keyword_score,
            "semantic_rank": best.semantic_rank,
            "keyword_rank": best.keyword_rank,
            "rrf_score": best.rrf_score,
        } if best else None,
        "exam_weight": tr.exam_weight,
        "exam_questions": [
            {"question_no": q.question_no, "points": q.points, "similarity": q.similarity}
            for q in tr.exam_questions
        ],
        "blind_spot_score": tr.blind_spot_score,
        "reason": tr.reason,
        "all_evidence": [
            {
                "content": e.content[:200],
                "heading": e.heading,
                "page": e.page,
                "document_name": e.document_name,
                "semantic_score": e.semantic_score,
                "keyword_score": e.keyword_score,
            }
            for e in tr.all_evidence
        ],
    }


def get_latest(course_id: str) -> Optional[dict]:
    """Get the latest coverage analysis for a course from the database."""
    run = get_latest_coverage(course_id)
    if not run:
        return None
    items = []
    for item in run.get("items", []):
        exam_qs = json.loads(item.get("exam_qs_json") or "[]")
        keywords = json.loads(item.get("keywords_json") or "[]")
        items.append({
            "topic_id": item["topic_id"],
            "topic_name": item["topic_name"],
            "keywords": keywords,
            "coverage_level": item.get("coverage_level"),
            "coverage_score": item.get("coverage_score"),
            "best_evidence": {
                "content": item.get("best_content"),
                "heading": item.get("best_heading"),
                "page": item.get("best_page"),
                "document_name": item.get("best_doc_name"),
                "semantic_score": item.get("best_sem_score"),
                "keyword_score": item.get("best_kw_score"),
            } if item.get("best_content") else None,
            "exam_weight": item.get("exam_weight", 0),
            "exam_questions": exam_qs,
            "blind_spot_score": item.get("blind_spot_score"),
            "reason": item.get("reason"),
        })
    return {
        "run_id": run["id"],
        "course_id": run["course_id"],
        "created_at": run["created_at"],
        "topics": json.loads(run.get("topics_json") or "[]"),
        "config": json.loads(run.get("config_json") or "{}"),
        "items": items,
    }
