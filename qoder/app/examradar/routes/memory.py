"""我的记忆页 API：掌握度卡片（含 revision 轨迹）、错题、复习计划、
会话小结、PowerContext artifact id / revision，以及 PC 调用日志。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..mastery import parse_mastery_text, parse_review_plan
from ..pc_client import (
    PowerContextClient, PowerContextUnavailable, recent_calls,
)
from ..coach import MEMORY_NOTICE, coverage_snapshot

router = APIRouter()


@router.get("/api/memory")
def memory_page(learner: str, course_id: str):
    learner = (learner or "").strip()
    if not learner:
        return JSONResponse({"error": "learner 不能为空"}, status_code=400)

    client = PowerContextClient()
    try:
        scope_id = client.ensure_scope(learner, course_id)
    except PowerContextUnavailable as e:
        return {
            "learner": learner,
            "course_id": course_id,
            "memory_ok": False,
            "memory_notice": MEMORY_NOTICE,
            "error": str(e),
            "pc_calls": recent_calls(30),
        }

    mastery_cards = []
    mistakes = []
    plan = None
    session_summaries = []
    try:
        # 掌握度卡片（含每张卡片的 revision 历史 = 掌握度变化轨迹）
        for it in client.query_by_tags(scope_id, ["type-mastery"],
                                       families=["atomic-memory"]):
            ref = it.get("reference") or {}
            artifact_id = ref.get("artifact_id")
            if not artifact_id:
                continue
            text, revision = client.get_memory(scope_id, artifact_id)
            state = parse_mastery_text(text)
            if not state:
                continue
            revisions = client.get_revisions(scope_id, artifact_id)
            mastery_cards.append({
                "topic_id": state.topic_id,
                "topic_name": state.topic_name,
                "box": state.box,
                "correct": state.correct,
                "wrong": state.wrong,
                "next_review": state.next_review.isoformat() if state.next_review else None,
                "text": text,
                "artifact_id": artifact_id,
                "revision": revision,
                "revisions": revisions,
            })
        mastery_cards.sort(key=lambda c: c["topic_id"])

        for m in client.list_memories(scope_id, "mistake"):
            mistakes.append({
                "text": m.get("text"),
                "artifact_id": m.get("artifact_id"),
                "revision": m.get("revision"),
            })

        handle = client.get_handle(scope_id, "review-plan")
        if handle and handle.get("artifact_id"):
            artifact_id = handle["artifact_id"]
            text, revision = client.get_memory(scope_id, artifact_id)
            plan = {
                "text": text,
                "parsed": None,
                "artifact_id": artifact_id,
                "revision": revision,
                "revisions": client.get_revisions(scope_id, artifact_id),
            }
            parsed = parse_review_plan(text)
            if parsed:
                plan["parsed"] = {
                    "opening": parsed.opening,
                    "wrong_recent": parsed.wrong_recent,
                    "due_today": parsed.due_today,
                    "blind_missing": parsed.blind_missing,
                    "updated": parsed.updated,
                }

        for m in client.list_memories(scope_id, "session"):
            session_summaries.append({
                "text": m.get("text"),
                "artifact_id": m.get("artifact_id"),
                "revision": m.get("revision"),
            })
        session_summaries.reverse()

        bootstrap = client.bootstrap(scope_id, event_id=f"memory-view-{scope_id[-8:]}")
        bootstrap_items = [
            {"artifact_id": ((it.get("artifact") or {}).get("artifact_id")),
             "revision": (it.get("artifact") or {}).get("revision")}
            for it in bootstrap.get("items") or []
        ]
        bootstrap_info = {
            "status": bootstrap.get("status"),
            "content": bootstrap.get("content"),
            "items": bootstrap_items,
        }
    except PowerContextUnavailable as e:
        return {
            "learner": learner,
            "course_id": course_id,
            "scope_id": scope_id,
            "memory_ok": False,
            "memory_notice": MEMORY_NOTICE,
            "error": str(e),
            "pc_calls": recent_calls(30),
        }

    cov = coverage_snapshot(course_id)
    return {
        "learner": learner,
        "course_id": course_id,
        "scope_id": scope_id,
        "memory_ok": True,
        "mastery_cards": mastery_cards,
        "mistakes": mistakes,
        "review_plan": plan,
        "session_summaries": session_summaries,
        "bootstrap": bootstrap_info,
        "coverage_run_id": (cov or {}).get("run_id"),
        "pc_calls": recent_calls(100),
    }
