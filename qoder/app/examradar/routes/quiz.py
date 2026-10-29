"""出题与判分路由：quiz/next、quiz/answer。

出题优先级：到期复习 > 覆盖分析 thin/missing（按盲区分）> 其余；
同一知识点至少隔 2 道别的题，计划池先轮一遍再回到答错的；
自测题在同一知识点的多道往年原题之间轮换。
进入知识点前 context/prepare 召回历史错题。
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import get_settings
from ..llm import get_llm_client
from ..mastery import MasteryState, grade_choice, grade_fill, parse_mastery_text
from ..pc_client import PowerContextClient, PowerContextUnavailable, parse_prepared_content
from ..seekdb import insert_usage_event
from .. import learning_store
from ..coach import (
    MEMORY_NOTICE, SELF_RATINGS, _fetch_chunk, _search_topic_chunks,
    _term_matched_chunks, build_review_plan_inputs, coverage_snapshot,
    grade_short_with_llm, load_mastery_states, make_fill_question,
    make_llm_question, make_self_test_question, remember_mistake, select_topic,
    update_review_plan, upsert_mastery_card,
)

router = APIRouter()


class QuizNextRequest(BaseModel):
    session_id: str
    topic_id: Optional[str] = None
    question_type: Optional[str] = None  # fill / choice / short；缺省自动


class QuizAnswerRequest(BaseModel):
    question_id: str
    session_id: Optional[str] = None
    answer: Optional[str] = None
    self_rating: Optional[str] = None  # 会 / 模糊 / 不会


def _topic_from_cov(cov: Optional[dict], topic_id: str) -> Optional[dict]:
    for it in (cov or {}).get("items") or []:
        if it["topic_id"] == topic_id:
            return it
    return None


def _public_payload(payload: dict) -> dict:
    out = dict(payload)
    out.pop("expected_answer", None)
    out.pop("reference_answer", None)
    return out


@router.post("/api/quiz/next")
def quiz_next(req: QuizNextRequest,
              x_examradar_source: Optional[str] = Header(None)):
    source = "auto" if x_examradar_source == "auto" else "real"
    session = learning_store.get_session(req.session_id)
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    if session.get("ended_at"):
        return JSONResponse({"error": "会话已结束，请重新开始会话"}, status_code=409)

    course_id = session["course_id"]
    scope_id = session.get("scope_id")
    cov = coverage_snapshot(course_id)

    client = PowerContextClient()
    # scope_id 为空说明会话创建时 PowerContext 就不可用，直接进入降级
    memory_ok = scope_id is not None
    mastery: dict[str, dict] = {}
    if scope_id:
        try:
            mastery = load_mastery_states(client, scope_id)
        except PowerContextUnavailable:
            memory_ok = False

    session_qs = learning_store.session_questions(req.session_id)
    last_q = session_qs[-1] if session_qs else None
    recent_topic_ids = [h["topic_id"] for h in session_qs]
    wrong_counts: dict[str, int] = {}
    for h in session_qs:
        if h.get("answered_at") and h.get("correct") == 0:
            tid = h["topic_id"]
            wrong_counts[tid] = wrong_counts.get(tid, 0) + 1

    if req.topic_id:
        topic = _topic_from_cov(cov, req.topic_id)
        if not topic and req.topic_id in mastery:
            st = mastery[req.topic_id]["state"]
            topic = {"topic_id": st.topic_id, "topic_name": st.topic_name,
                     "coverage_level": None, "keywords": []}
    else:
        topic = select_topic(mastery, cov, recent_topic_ids, wrong_counts)
    if not topic:
        return JSONResponse(
            {"error": "没有可选的知识点：请先导入资料并运行覆盖分析"}, status_code=409)

    # 进入知识点前召回历史错题（query 用"知识点 id + 知识点名称"）
    history: list[dict] = []
    if scope_id and memory_ok:
        try:
            prep = client.prepare(
                scope_id, f"{topic['topic_id']} {topic['topic_name']}",
                max_bytes=get_settings().pc_context_max_bytes)
            history = parse_prepared_content(prep.get("content") or "")
        except PowerContextUnavailable:
            memory_ok = False

    # 本会话这个知识点已经用过的出题材料：自测题在多道原题之间轮换，
    # 填空题优先换一个挖空点
    topic_history = [h for h in session_qs
                     if h["topic_id"] == topic["topic_id"]]
    used_exam_nos = [
        (h["payload"].get("source") or {}).get("question_no")
        for h in topic_history if h["payload"].get("question_type") == "self"]
    used_exam_nos = [n for n in used_exam_nos if n is not None]
    used_terms = {
        h["payload"].get("expected_answer")
        for h in topic_history if h["payload"].get("question_type") == "fill"}
    used_terms.discard(None)

    def _topic_material_chunks() -> list[dict]:
        """出题材料：thin/covered 只用找到考点词的段落（原文属于这个知识点）。

        没有覆盖数据（topic 无 terms，例如按掌握度卡片轮转）时退回 hybrid 检索。
        """
        chunks = _term_matched_chunks(course_id, topic)
        if not chunks and not topic.get("terms"):
            chunks = _search_topic_chunks(course_id, topic)
        return chunks

    def _rule_fill() -> Optional[dict]:
        chunks = _topic_material_chunks()
        fallback: Optional[dict] = None
        for chunk in chunks:
            q = make_fill_question(topic, chunk, used_terms)
            if q is None:
                continue
            if fallback is None:
                fallback = q
            if q["expected_answer"] not in used_terms:
                return q
        return fallback

    payload: Optional[dict] = None
    llm_used = False

    if topic.get("coverage_level") == "missing":
        # missing 知识点：学生资料里没有原文，给往年原题自测
        payload = make_self_test_question(topic, course_id, used_exam_nos)
        if payload is None:
            payload = _rule_fill()
    else:
        requested = req.question_type
        llm = get_llm_client()
        if requested not in ("choice", "short"):
            if requested == "fill":
                pass
            elif llm.configured:
                # 默认在选择题 / 简答题之间轮换
                requested = ("short" if last_q and last_q["question_type"] == "choice"
                             else "choice")
            else:
                requested = "fill"
        if llm.configured and requested in ("choice", "short"):
            chunks = _topic_material_chunks()
            payload = make_llm_question(llm, topic, chunks, history, requested,
                                        f"{topic['topic_id']} {topic['topic_name']}")
            if payload is not None:
                llm_used = True
        if payload is None:
            payload = _rule_fill()

    if payload is None:
        return JSONResponse(
            {"error": f"知识点「{topic['topic_name']}」没有可用的出题材料"},
            status_code=409)

    question_id = uuid.uuid4().hex[:12]
    learning_store.create_question(
        question_id, req.session_id, course_id, topic["topic_id"],
        topic["topic_name"], payload["question_type"], payload)
    insert_usage_event(course_id, source, "question", {
        "question_id": question_id,
        "topic_id": topic["topic_id"],
        "topic_name": topic["topic_name"],
        "question_type": payload["question_type"],
        "source_doc": (payload.get("source") or {}).get("label"),
        "llm_generated": payload.get("llm_generated", False),
    }, session_id=req.session_id)
    learning_store.touch_session(req.session_id)

    mistake_history = [h for h in history if "【错题】" in h.get("text", "")]
    return {
        "question_id": question_id,
        "session_id": req.session_id,
        "topic_id": topic["topic_id"],
        "topic_name": topic["topic_name"],
        "selection_source": topic.get("source") or ("requested" if req.topic_id else "auto"),
        **_public_payload(payload),
        "history": history,
        "mistake_history": mistake_history,
        "llm_used": llm_used,
        "memory_ok": memory_ok,
        "memory_notice": None if memory_ok else MEMORY_NOTICE,
    }


@router.post("/api/quiz/answer")
def quiz_answer(req: QuizAnswerRequest,
                x_examradar_source: Optional[str] = Header(None)):
    source = "auto" if x_examradar_source == "auto" else "real"
    q = learning_store.get_question(req.question_id)
    if not q:
        return JSONResponse({"error": "题目不存在"}, status_code=404)
    if q.get("answered_at"):
        return JSONResponse({"error": "这道题已经判过分了"}, status_code=409)
    if req.session_id and q["session_id"] != req.session_id:
        return JSONResponse({"error": "题目不属于这个会话"}, status_code=409)

    session = learning_store.get_session(q["session_id"])
    payload = q["payload"]
    qtype = payload.get("question_type")
    answer = (req.answer or "").strip()
    self_rating = (req.self_rating or "").strip()

    llm = get_llm_client()
    correct: Optional[bool] = None
    feedback: str = ""
    misconception: Optional[str] = None
    needs_self_rating = False
    judged_by = qtype

    if qtype == "fill":
        correct = grade_fill(payload.get("expected_answer") or "", answer)
        feedback = ("答对了！" if correct
                    else f"答错了。正确答案：{payload.get('expected_answer')}")
    elif qtype == "choice":
        correct = grade_choice(payload.get("expected_answer") or "", answer)
        feedback = ("答对了！" if correct
                    else f"答错了。正确答案：{payload.get('expected_answer')}")
    elif qtype == "short":
        judged = None
        if llm.configured and answer:
            source_text = ""
            if payload.get("chunk_id"):
                chunk = _fetch_chunk(payload["chunk_id"])
                source_text = (chunk or {}).get("content") or ""
            judged = grade_short_with_llm(
                llm, payload.get("question") or "",
                payload.get("reference_answer") or "", answer, source_text)
        if judged is not None:
            correct = judged["correct"]
            misconception = judged["misconception"] or None
            judged_by = "llm"
            feedback = ("答对了。" if correct else "答错了。") + (
                f"误区：{judged['misconception']}" if judged["misconception"] else "")
            feedback += f" 参考答案：{payload.get('reference_answer')}"
        else:
            needs_self_rating = True
            judged_by = "self"
            if self_rating not in SELF_RATINGS:
                return JSONResponse({
                    "error": "没有可用的大模型判分，请先看参考答案并自评",
                    "reference_answer": payload.get("reference_answer"),
                    "self_ratings": SELF_RATINGS,
                }, status_code=400)
            correct = self_rating == "会"
            feedback = (f"自评：{self_rating}。参考答案：{payload.get('reference_answer')}")
    elif qtype == "self":
        judged_by = "self"
        if self_rating not in SELF_RATINGS:
            return JSONResponse({
                "error": "自测题请自评：会 / 模糊 / 不会",
                "self_ratings": SELF_RATINGS,
            }, status_code=400)
        correct = self_rating == "会"
        feedback = f"自评：{self_rating}。" + ("已经掌握了。" if correct else "回到 1 号盒，尽快复习。")
    else:
        return JSONResponse({"error": f"未知题型 {qtype}"}, status_code=400)

    if correct is None:
        return JSONResponse({"error": "判分失败"}, status_code=500)

    # -------------------------------------------------- 记忆写入（可降级）
    scope_id = (session or {}).get("scope_id")
    memory_ok = scope_id is not None
    box_before: Optional[int] = None
    box_after: Optional[int] = None
    mastery_info: Optional[dict] = None
    mistake_info: Optional[dict] = None
    plan_info: Optional[dict] = None

    if scope_id:
        client = PowerContextClient()
        try:
            handle = client.get_handle(scope_id, f"mastery-{q['topic_id']}")
            existing = None
            state = MasteryState(topic_id=q["topic_id"], topic_name=q["topic_name"])
            if handle and handle.get("artifact_id"):
                text, _rev = client.get_memory(scope_id, handle["artifact_id"])
                parsed = parse_mastery_text(text)
                if parsed:
                    state = parsed
                    existing = {"artifact_id": handle["artifact_id"],
                                "revision": handle.get("revision")}
            box_before = state.box
            new_state = state.apply_answer(correct)
            box_after = new_state.box
            mastery_info = upsert_mastery_card(client, scope_id, new_state, existing)

            if not correct:
                mistake_info = remember_mistake(
                    client, scope_id, q["topic_id"], q["topic_name"],
                    payload.get("question") or "", answer,
                    str(payload.get("expected_answer")
                        or payload.get("reference_answer") or "（自评未通过）"),
                    (payload.get("source") or {}).get("label") or "")

            mastery = load_mastery_states(client, scope_id)
            cov = coverage_snapshot(q["course_id"])
            plan_info = update_review_plan(
                client, scope_id, *build_review_plan_inputs(mastery, cov))
        except PowerContextUnavailable:
            memory_ok = False

    learning_store.save_answer(req.question_id, answer, correct, box_before, box_after)
    insert_usage_event(q["course_id"], source, "answer", {
        "question_id": req.question_id,
        "topic_id": q["topic_id"],
        "topic_name": q["topic_name"],
        "question_type": qtype,
        "correct": bool(correct),
        "box_before": box_before,
        "box_after": box_after,
        "judged_by": judged_by,
    }, session_id=q["session_id"])
    learning_store.touch_session(q["session_id"])

    result = {
        "question_id": req.question_id,
        "correct": bool(correct),
        "feedback": feedback,
        "judged_by": judged_by,
        "needs_self_rating": needs_self_rating,
        "box_before": box_before,
        "box_after": box_after,
        "expected_answer": payload.get("expected_answer"),
        "reference_answer": payload.get("reference_answer"),
        "explanation": payload.get("explanation"),
        "misconception": misconception,
        "learner_answer": answer,
        "memory_ok": memory_ok,
        "memory_notice": None if memory_ok else MEMORY_NOTICE,
        "mastery": mastery_info,
        "mistake_memory": mistake_info,
        "review_plan": plan_info,
    }
    return result
