"""学习会话路由：start（bootstrap）/ end（会话小结 + 复习计划）。"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import get_settings
from ..mastery import learner_hash, format_session_summary
from ..pc_client import (
    PowerContextClient, PowerContextUnavailable, bootstrap_opening_line,
)
from ..seekdb import insert_usage_event
from .. import learning_store
from ..coach import (
    MEMORY_NOTICE, build_review_plan_inputs, coverage_snapshot, due_topics,
    load_mastery_states, review_plan_opening, update_review_plan,
)

router = APIRouter()


class SessionStartRequest(BaseModel):
    learner: str
    course_id: str


@router.get("/api/coach/status")
def coach_status():
    from ..llm import get_llm_client
    s = get_settings()
    llm = get_llm_client()
    pc = PowerContextClient()
    pc_ok, pc_detail = pc.health()
    return {
        "llm": {
            "configured": llm.configured,
            "model": llm.model,
            "base_url": llm.base_url,
        },
        "powercontext": {"ok": pc_ok, "detail": pc_detail},
        "session_idle_minutes": s.session_idle_minutes,
    }


@router.post("/api/sessions/start")
def session_start(req: SessionStartRequest,
                  x_examradar_source: Optional[str] = Header(None)):
    source = "auto" if x_examradar_source == "auto" else "real"
    learner = (req.learner or "").strip()
    if not learner:
        return JSONResponse({"error": "learner 不能为空"}, status_code=400)

    session_id = uuid.uuid4().hex[:16]
    learning_store.mark_idle_sessions_ended()

    s = get_settings()
    client = PowerContextClient()
    scope_id: Optional[str] = None
    memory_ok = True
    bootstrap: Optional[dict] = None
    opening_line: Optional[str] = None
    mastery: dict[str, dict] = {}

    try:
        scope_id = client.ensure_scope(learner, req.course_id)
    except PowerContextUnavailable:
        memory_ok = False

    if scope_id and memory_ok:
        try:
            bootstrap = client.bootstrap(scope_id, event_id=session_id,
                                         max_bytes=s.pc_context_max_bytes)
            mastery = load_mastery_states(client, scope_id)
            opening_line = (review_plan_opening(client, scope_id)
                            or bootstrap_opening_line(bootstrap))
        except PowerContextUnavailable:
            memory_ok = False
            bootstrap = None
            opening_line = None

    cov = coverage_snapshot(req.course_id)
    due = due_topics(mastery)
    blind = sorted(
        (it for it in (cov or {}).get("items") or []
         if it["coverage_level"] in ("thin", "missing")),
        key=lambda it: -it["blind_spot_score"])

    learning_store.create_session(session_id, scope_id, learner_hash(learner),
                                  req.course_id)
    insert_usage_event(req.course_id, source, "session_start", {
        "session_id": session_id,
        "course_id": req.course_id,
        "learner": learner_hash(learner),
    }, session_id=session_id)

    return {
        "session_id": session_id,
        "course_id": req.course_id,
        "learner_hash": learner_hash(learner),
        "scope_id": scope_id,
        "memory_ok": memory_ok,
        "memory_notice": None if memory_ok else MEMORY_NOTICE,
        "opening_line": opening_line,
        "bootstrap": {
            "status": (bootstrap or {}).get("status"),
            "reason": (bootstrap or {}).get("reason"),
            "content": (bootstrap or {}).get("content"),
            "items": [
                {"artifact_id": (((it.get("artifact") or {}).get("artifact_id"))),
                 "revision": ((it.get("artifact") or {}).get("revision"))}
                for it in (bootstrap or {}).get("items") or []
            ],
        } if bootstrap else None,
        "due_topics": due,
        "blind_topics": [
            {"topic_id": it["topic_id"], "topic_name": it["topic_name"],
             "coverage_level": it["coverage_level"],
             "exam_weight": it["exam_weight"],
             "blind_spot_score": it["blind_spot_score"]}
            for it in blind[:10]
        ],
        "coverage_run_id": (cov or {}).get("run_id"),
    }


@router.post("/api/sessions/end")
async def session_end(request: Request):
    """同时接受普通 JSON 和 sendBeacon 的 text/plain。"""
    raw = await request.body()
    try:
        data = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"error": "请求体不是合法 JSON"}, status_code=400)
    session_id = (data.get("session_id") or "").strip()
    if not session_id:
        return JSONResponse({"error": "session_id 不能为空"}, status_code=400)
    source = request.headers.get("X-ExamRadar-Source")
    if source != "auto" and data.get("source") == "auto":
        source = "auto"
    source = "auto" if source == "auto" else "real"

    session = learning_store.get_session(session_id)
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    already_ended = session.get("ended_at") is not None

    if not already_ended:
        # 结束请求本身是一个事件：时长按最后一个事件计
        learning_store.touch_session(session_id)
        session = learning_store.end_session(session_id)

    stats = learning_store.session_question_stats(session_id)
    duration = learning_store.session_duration_seconds(session or {})

    # scope_id 为空说明会话创建时 PowerContext 就不可用，直接进入降级
    memory_ok = bool(session and session.get("scope_id"))
    summary_memory: Optional[dict] = None
    plan_memory: Optional[dict] = None
    if not already_ended and session and session.get("scope_id"):
        client = PowerContextClient()
        scope_id = session["scope_id"]
        try:
            weak = sorted(
                ((tid, name, count) for tid, (name, count)
                 in stats["wrong_by_topic"].items()),
                key=lambda x: -x[2])
            text = format_session_summary(
                max(duration, 0.0) / 60.0, stats["asked"], stats["correct"], weak,
                started_at=session.get("started_at"))
            created = client.remember(scope_id, "session", text)
            if created:
                try:
                    client.put_tags(scope_id, created[0],
                                    ["examradar", "type-session"])
                except Exception:
                    pass
                summary_memory = {"artifact_id": created[0],
                                  "revision": created[1], "text": text}
            cov = coverage_snapshot(session["course_id"])
            mastery = load_mastery_states(client, scope_id)
            plan_memory = update_review_plan(client, scope_id,
                                             *build_review_plan_inputs(mastery, cov))
        except PowerContextUnavailable:
            memory_ok = False

    if not already_ended:
        insert_usage_event(session["course_id"], source, "session_end", {
            "session_id": session_id,
            "duration_seconds": round(duration, 1),
            "questions_asked": stats["asked"],
            "questions_correct": stats["correct"],
        }, session_id=session_id)

    return {
        "session_id": session_id,
        "already_ended": already_ended,
        "duration_seconds": round(duration, 1),
        "questions_asked": stats["asked"],
        "questions_correct": stats["correct"],
        "memory_ok": memory_ok,
        "memory_notice": None if memory_ok else MEMORY_NOTICE,
        "summary_memory": summary_memory,
        "review_plan": plan_memory,
    }
