"""Coverage analysis: per-topic key-term evidence, exam weight, blind spots.

Judgment is based on whether a topic's key terms (考点词) actually appear in
the course materials (notes / slides / paper). Semantic scores from
DBMS_HYBRID_SEARCH rank and annotate the evidence but never decide coverage:
with bge-small-zh-v1.5, cosine similarity for unrelated short Chinese terms
stays above ~0.7, so it cannot separate "covered" from "missing" (measured
in DEVLOG sessions 04/05).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .config import get_settings
from .seekdb import (
    hybrid_search, get_connection, save_coverage_run,
    get_latest_coverage, insert_usage_event, get_coverage_chunks,
    get_exam_chunks,
)
from .embedding import get_embedding_model
from .syllabus import Topic, Term, normalize_for_match, tokenize_term, parse_syllabus

COVERAGE_DOC_KINDS = ["notes", "slides", "paper"]


@dataclass
class ChunkInfo:
    """One candidate chunk from the course materials."""
    chunk_id: int
    content: str
    heading: Optional[str]
    page: Optional[int]
    document_name: Optional[str]
    body_chars: int = 0
    norm_text: str = ""
    matched_terms: list[str] = field(default_factory=list)
    sem_score: Optional[float] = None
    kw_score: Optional[float] = None


@dataclass
class TermEvidence:
    term: str
    aliases: list[str]
    found: bool
    # chunks where the term (or an alias) appears, as {doc, page, heading}
    chunk_refs: list[dict] = field(default_factory=list)
    # ids of the chunks above, to derive per-chunk matched terms
    chunk_ids: list[int] = field(default_factory=list)
    best_sem: Optional[float] = None


@dataclass
class ExamQuestion:
    question_no: int
    points: float
    topic_id: str
    similarity: float
    matched_terms: list[str]
    content: str


@dataclass
class TopicResult:
    topic_id: str
    topic_name: str
    keywords: list[str]
    terms: list[TermEvidence]
    coverage_level: str
    coverage_score: float
    support_chunks: int
    support_chars: int
    best_evidence: Optional[ChunkInfo]
    exam_weight: float
    exam_questions: list[ExamQuestion]
    blind_spot_score: float
    reason: str
    all_evidence: list[ChunkInfo] = field(default_factory=list)


# --------------------------------------------------------------------------
# Pure matching logic (unit-tested without a database)
# --------------------------------------------------------------------------

def match_variant(norm_text: str, variant: str) -> bool:
    """Does one term variant (text or alias) appear in normalized text?

    A variant with a single token must appear contiguously. A multi-token
    variant ("SQL 查询", "事务的 ACID 特性") matches when a strict majority of
    its content tokens occur in the same paragraph — generic trailing words
    (的/特性) must not block an otherwise exact co-occurrence.
    """
    norm_text = normalize_for_match(norm_text)
    v = normalize_for_match(variant)
    if not v or not norm_text:
        return False
    if v in norm_text:
        return True
    tokens = tokenize_term(variant)
    if len(tokens) >= 2:
        hits = sum(1 for t in tokens if t in norm_text)
        return hits * 2 > len(tokens)
    return False


def term_matches(term: Term, norm_text: str) -> bool:
    return any(match_variant(norm_text, v) for v in term.variants())


def body_text(content: str) -> str:
    """Chunk content minus markdown heading lines and blank lines.

    Only body text counts toward support: a chunk that is just a heading
    plus a one-line remark is a table of contents entry, not evidence.
    """
    lines = [l.strip() for l in content.split("\n")
             if l.strip() and not l.lstrip().startswith("#")]
    return "".join(lines)


def judge_topic(found_terms: int, total_terms: int, support_chars: int,
                ratio_threshold: float, support_threshold: int) -> tuple[str, float]:
    """Judge coverage from interpretable quantities. Returns (level, score).

    - missing: no term found at all
    - covered: at least `ratio_threshold` of the terms found AND at least
      `support_threshold` chars of supporting body text
    - thin: anything in between (some terms found, but not enough breadth
      or not enough substance)

    score: 0 for missing; thin stays below 0.5, covered stays at or above
    0.5 — the radar value and blind-spot score share it, so the chart never
    contradicts the judgment.
    """
    if total_terms == 0 or found_terms == 0:
        return "missing", 0.0
    ratio = found_terms / total_terms
    support_factor = min(1.0, support_chars / support_threshold) \
        if support_threshold > 0 else 1.0
    degree = ratio * support_factor
    if ratio >= ratio_threshold and support_chars >= support_threshold:
        return "covered", 0.5 + 0.5 * degree
    return "thin", 0.5 * degree


def _short_ref(ref: dict) -> str:
    """Compact evidence reference for reasons: doc name + last heading level.

    Full heading paths repeat the chapter title for every paragraph of the
    same document and made reasons unusably long.
    """
    doc = ref.get("doc") or ""
    heading = ref.get("heading") or ""
    if " > " in heading:
        heading = heading.rsplit(" > ", 1)[-1]
    if heading:
        return f"{doc}·{heading}" if doc else heading
    if ref.get("page"):
        return f"{doc}·第{ref['page']}页" if doc else f"第{ref['page']}页"
    return doc


def blind_spot_sort_key(topic_id: str, blind_spot_score) -> tuple:
    """Blind-spot score high→low, ties broken by topic_id (asc).

    The single ordering used by both the fresh analysis result and the
    persisted run read back via get_latest(), so the two APIs and the
    radar page's blind-spot table always agree.
    """
    return (-float(blind_spot_score or 0), topic_id)


def build_reason(level: str, score: float, terms: list[TermEvidence],
                 support_chunks: int, support_chars: int) -> str:
    s = get_settings()
    ratio_t = s.coverage_term_ratio_covered
    support_t = s.coverage_support_chars
    total = len(terms)
    found = [t for t in terms if t.found]
    missing = [t for t in terms if not t.found]

    found_parts = []
    for t in found:
        refs = [_short_ref(r) for r in t.chunk_refs[:2]]
        more = f" 等{len(t.chunk_refs)}段" if len(t.chunk_refs) > 2 else ""
        found_parts.append(f"{t.term}→{'、'.join(refs)}{more}")
    found_desc = "考点词 {}/{} 找到（{}）".format(
        len(found), total, "；".join(found_parts)) if found_parts else \
        f"考点词 0/{total} 找到"

    if level == "missing":
        names = "、".join(t.term for t in missing)
        return (f"{found_desc}：{names}在笔记、课件和阅读材料中均未出现，"
                f"覆盖度 0。")
    if level == "covered":
        head = f"{found_desc}。"
        if missing:
            head += "未找到：" + "、".join(t.term for t in missing) + "。"
        ratio = len(found) / total
        if ratio > ratio_t:
            ratio_phrase = (f"考点词比例 {len(found)}/{total}，"
                            f"高于阈值 {ratio_t}（高出 {ratio - ratio_t:.2f}）")
        else:
            ratio_phrase = f"考点词比例 {len(found)}/{total}，达到阈值 {ratio_t}"
        return (head + f"支撑段落 {support_chunks} 段共 {support_chars} 字，"
                f"高出 covered 支撑阈值（{support_t} 字）{support_chars - support_t} 字，"
                f"{ratio_phrase}。")
    # thin
    ratio = len(found) / total if total else 0.0
    head = f"{found_desc}。"
    if missing:
        head += "未找到：" + "、".join(t.term for t in missing) + "。"
    if ratio < ratio_t:
        return (head + f"考点词比例 {ratio:.2f} 低于 covered 阈值 {ratio_t}"
                f"（差 {ratio_t - ratio:.2f}），判为 thin。")
    return (head + f"支撑段落 {support_chunks} 段共 {support_chars} 字，"
            f"距 covered 阈值（{support_t} 字）还差 {support_t - support_chars} 字，"
            f"判为 thin。")


# --------------------------------------------------------------------------
# Analysis pipeline
# --------------------------------------------------------------------------

def _load_chunks(course_id: str) -> list[ChunkInfo]:
    rows = get_coverage_chunks(course_id, COVERAGE_DOC_KINDS)
    return [
        ChunkInfo(
            chunk_id=r["id"],
            content=r["content"],
            heading=r.get("heading"),
            page=r.get("page"),
            document_name=r.get("doc_name"),
            body_chars=len(body_text(r["content"])),
            norm_text=normalize_for_match(
                (r.get("heading") or "") + "\n" + r["content"]),
        )
        for r in rows
    ]


def _cosine(a, b) -> float:
    import numpy as np
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _parse_embedding(raw) -> Optional[list[float]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = json.loads(raw)
    return [float(x) for x in raw]


def make_chunk(chunk_id: int, content: str, heading: Optional[str] = None,
               document_name: Optional[str] = None,
               page: Optional[int] = None) -> ChunkInfo:
    """Build a ChunkInfo from raw text (unit tests construct these by hand)."""
    return ChunkInfo(
        chunk_id=chunk_id,
        content=content,
        heading=heading,
        page=page,
        document_name=document_name,
        body_chars=len(body_text(content)),
        norm_text=normalize_for_match((heading or "") + "\n" + content),
    )


def evaluate_topic(topic: Topic, chunks: list[ChunkInfo],
                   min_body: int) -> tuple[list[TermEvidence], list[ChunkInfo], int]:
    """Match a topic's terms against material chunks (pure, no DB).

    Returns (term_evidence, supporting_chunks, support_chars). A chunk
    supports the topic when at least one term matches and its body text is
    at least min_body chars. Semantic scores on the chunks are only used to
    order evidence and annotate terms.
    """
    term_evidence: list[TermEvidence] = []
    for term in topic.terms:
        refs = []
        matched_ids = []
        best_sem = None
        for c in chunks:
            if term_matches(term, c.norm_text):
                refs.append({"doc": c.document_name, "page": c.page,
                             "heading": c.heading})
                matched_ids.append(c.chunk_id)
                if c.sem_score is not None:
                    best_sem = max(best_sem or 0.0, c.sem_score)
        term_evidence.append(TermEvidence(
            term=term.text, aliases=list(term.aliases),
            found=bool(refs), chunk_refs=refs, chunk_ids=matched_ids,
            best_sem=best_sem,
        ))

    for c in chunks:
        c.matched_terms = [te.term for te in term_evidence
                           if c.chunk_id in te.chunk_ids]

    supporting = [c for c in chunks
                  if c.matched_terms and c.body_chars >= min_body]
    support_chars = sum(c.body_chars for c in supporting)
    supporting.sort(key=lambda c: (-(c.sem_score or 0), -c.body_chars))
    return term_evidence, supporting, support_chars


def assign_question(question_text: str, topics: list[Topic],
                    sims: dict[str, float]) -> tuple[Optional[str], list[str]]:
    """Assign one exam question to a topic (pure, no DB).

    Primary evidence: the topics' key terms appearing in the question text;
    among the topics with the most matched terms, semantic similarity
    decides. When no topic's terms appear at all, only semantics decide.
    Returns (topic_id, matched_terms).
    """
    q_norm = normalize_for_match(question_text)
    matched: dict[str, list[str]] = {}
    for t in topics:
        hits = [term.text for term in t.terms if term_matches(term, q_norm)]
        if hits:
            matched[t.topic_id] = hits

    if matched:
        best_count = max(len(v) for v in matched.values())
        candidates = [tid for tid, v in matched.items() if len(v) == best_count]
        best_topic = max(candidates, key=lambda tid: sims.get(tid, -1.0))
        return best_topic, matched[best_topic]
    if sims:
        return max(sims, key=lambda tid: sims[tid]), []
    return None, []


def _assign_exam_questions(course_id: str, topics: list[Topic],
                           topic_embeddings: dict[str, list[float]]
                           ) -> dict[str, list[ExamQuestion]]:
    """Assign each exam question to one topic (DB access + embeddings)."""
    questions = get_exam_chunks(course_id)
    assignment: dict[str, list[ExamQuestion]] = {t.topic_id: [] for t in topics}
    if not questions:
        return assignment

    for q in questions:
        sims = {}
        q_vec = _parse_embedding(q.get("embedding"))
        if q_vec is not None:
            for tid, t_vec in topic_embeddings.items():
                sims[tid] = (1 + _cosine(q_vec, t_vec)) / 2

        best_topic, basis = assign_question(q["content"], topics, sims)
        if best_topic:
            assignment[best_topic].append(ExamQuestion(
                question_no=q["question_no"],
                points=float(q.get("points") or 0),
                topic_id=best_topic,
                similarity=sims.get(best_topic, 0.0),
                matched_terms=basis,
                content=q["content"],
            ))
    return assignment


def analyze(course_id: str, syllabus_text: str, source: str = "real",
            session_id: Optional[str] = None) -> dict:
    """Run full coverage analysis. Returns the result dict and persists it."""
    topics = parse_syllabus(syllabus_text)
    if not topics:
        raise ValueError("没有从考试范围中解析出知识点")

    s = get_settings()
    ratio_t = s.coverage_term_ratio_covered
    support_t = s.coverage_support_chars
    min_body = s.coverage_min_body_chars

    chunks = _load_chunks(course_id)
    model = get_embedding_model()

    # embeddings for chunks not recalled by hybrid search (fallback scoring)
    chunk_embs: dict[int, Optional[list[float]]] = {}
    if chunks:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, embedding FROM chunks WHERE id IN (%s)" %
                    ",".join(str(c.chunk_id) for c in chunks),
                )
                chunk_embs = {r["id"]: _parse_embedding(r["embedding"])
                              for r in cur.fetchall()}
        finally:
            conn.close()

    topic_results: list[TopicResult] = []
    topic_embeddings = {
        t.topic_id: model.embed_one(t.search_query, is_query=True)
        for t in topics
    }

    for topic in topics:
        query_vec = topic_embeddings[topic.topic_id]
        hits, _, _ = hybrid_search(
            query_text=topic.search_query,
            query_vector=query_vec,
            course_id=course_id,
            doc_kinds=COVERAGE_DOC_KINDS,
            top_k=10,
        )
        hybrid_scores = {h["id"]: h for h in hits}

        for c in chunks:
            h = hybrid_scores.get(c.chunk_id)
            if h is not None:
                c.sem_score = h.get("_semantic_score")
                c.kw_score = h.get("_keyword_score")
            elif chunk_embs.get(c.chunk_id) is not None:
                c.sem_score = (1 + _cosine(query_vec, chunk_embs[c.chunk_id])) / 2
                c.kw_score = None
            else:
                c.sem_score = None
                c.kw_score = None

        # term matching over ALL material chunks (not just the hybrid recall
        # pool): the judgment must not depend on recall completeness
        term_evidence, supporting, support_chars = evaluate_topic(
            topic, chunks, min_body)

        found_count = sum(1 for te in term_evidence if te.found)
        level, score = judge_topic(found_count, len(topic.terms),
                                   support_chars, ratio_t, support_t)
        reason = build_reason(level, score, term_evidence,
                              len(supporting), support_chars)

        best = supporting[0] if supporting else None

        topic_results.append(TopicResult(
            topic_id=topic.topic_id,
            topic_name=topic.name,
            keywords=topic.keywords,
            terms=term_evidence,
            coverage_level=level,
            coverage_score=round(score, 4),
            support_chunks=len(supporting),
            support_chars=support_chars,
            best_evidence=best,
            exam_weight=0.0,
            exam_questions=[],
            blind_spot_score=0.0,
            reason=reason,
            all_evidence=supporting,
        ))

    exam_assignment = _assign_exam_questions(course_id, topics, topic_embeddings)
    for tr in topic_results:
        qs = exam_assignment.get(tr.topic_id, [])
        tr.exam_questions = qs
        tr.exam_weight = sum(q.points for q in qs)
        tr.blind_spot_score = round(tr.exam_weight * (1.0 - tr.coverage_score), 2)

    topic_results.sort(
        key=lambda t: blind_spot_sort_key(t.topic_id, t.blind_spot_score))

    config_json = json.dumps({
        "term_ratio_covered": ratio_t,
        "support_chars_covered": support_t,
        "min_body_chars": min_body,
    })
    topics_json = json.dumps(
        [{"id": t.topic_id, "name": t.name, "keywords": t.keywords,
          "terms": [{"text": term.text, "aliases": term.aliases}
                    for term in t.terms]} for t in topics],
        ensure_ascii=False,
    )

    items = [_item_dict(tr) for tr in topic_results]
    run_id = save_coverage_run(course_id, source, topics_json, config_json, items)

    insert_usage_event(course_id, source, "analyze", {
        "run_id": run_id,
        "topic_count": len(topics),
        "syllabus_text": syllabus_text[:500],
    }, session_id=session_id)

    return _format_result(run_id, course_id, topic_results, topics_json,
                          config_json)


def _item_dict(tr: TopicResult) -> dict:
    best = tr.best_evidence
    return {
        "topic_id": tr.topic_id,
        "topic_name": tr.topic_name,
        "keywords_json": json.dumps(tr.keywords, ensure_ascii=False),
        "coverage_level": tr.coverage_level,
        "coverage_score": tr.coverage_score,
        "terms_json": json.dumps([{
            "term": te.term,
            "aliases": te.aliases,
            "found": te.found,
            "chunks": te.chunk_refs[:10],
            "best_sem": te.best_sem,
        } for te in tr.terms], ensure_ascii=False),
        "support_chunks": tr.support_chunks,
        "support_chars": tr.support_chars,
        "best_sem_score": best.sem_score if best else None,
        "best_kw_score": best.kw_score if best else None,
        "best_content": best.content if best else None,
        "best_heading": best.heading if best else None,
        "best_page": best.page if best else None,
        "best_doc_name": best.document_name if best else None,
        "exam_weight": tr.exam_weight,
        "exam_qs_json": json.dumps([{
            "question_no": q.question_no, "points": q.points,
            "similarity": q.similarity, "matched_terms": q.matched_terms,
            "content": q.content,
        } for q in tr.exam_questions], ensure_ascii=False),
        "blind_spot_score": tr.blind_spot_score,
        "reason": tr.reason,
    }


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
        "support_chunks": tr.support_chunks,
        "support_chars": tr.support_chars,
        "terms": [{
            "term": te.term,
            "aliases": te.aliases,
            "found": te.found,
            "chunks": te.chunk_refs,
            "best_sem": te.best_sem,
        } for te in tr.terms],
        "best_evidence": {
            "content": best.content,
            "heading": best.heading,
            "page": best.page,
            "document_name": best.document_name,
            "semantic_score": best.sem_score,
            "keyword_score": best.kw_score,
            "matched_terms": best.matched_terms,
            "body_chars": best.body_chars,
        } if best else None,
        "exam_weight": tr.exam_weight,
        "exam_questions": [
            {"question_no": q.question_no, "points": q.points,
             "similarity": q.similarity, "matched_terms": q.matched_terms,
             "content": q.content}
            for q in tr.exam_questions
        ],
        "blind_spot_score": tr.blind_spot_score,
        "reason": tr.reason,
        "all_evidence": [
            {
                "content": e.content,
                "heading": e.heading,
                "page": e.page,
                "document_name": e.document_name,
                "semantic_score": e.sem_score,
                "keyword_score": e.kw_score,
                "matched_terms": e.matched_terms,
                "body_chars": e.body_chars,
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
        terms = json.loads(item.get("terms_json") or "[]")
        items.append({
            "topic_id": item["topic_id"],
            "topic_name": item["topic_name"],
            "keywords": keywords,
            "coverage_level": item.get("coverage_level"),
            "coverage_score": item.get("coverage_score"),
            "support_chunks": item.get("support_chunks"),
            "support_chars": item.get("support_chars"),
            "terms": terms,
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
    # the persisted run comes back ORDER BY topic_id; re-apply the same
    # ordering as analyze() so both APIs return an identical sequence
    items.sort(key=lambda it: blind_spot_sort_key(
        it["topic_id"], it.get("blind_spot_score")))
    return {
        "run_id": run["id"],
        "course_id": run["course_id"],
        "created_at": run["created_at"],
        "topics": json.loads(run.get("topics_json") or "[]"),
        "config": json.loads(run.get("config_json") or "{}"),
        "items": items,
    }
