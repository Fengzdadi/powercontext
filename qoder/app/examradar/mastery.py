"""Leitner 掌握度递推 + 记忆文本格式（mastery / mistake / plan / session）。

写进记忆的只有判分代码确定的事实：对错、学生自己的答案、正确答案、出处。
掌握度卡片和错题记忆的文本里都写上知识点 id 和名称，
保证 PowerContext 全文召回（"t08 隔离级别与 MVCC" 这类查询）能命中。

卡片 / 计划文本格式：第一行给人看，后面几行 `key: value` 机器可解析。
"""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .config import get_settings


def learner_hash(learner: str) -> str:
    """学习者名字的不可逆短哈希（sha256 前 8 位）。使用记录公开材料里只有它。"""
    return hashlib.sha256(learner.encode("utf-8")).hexdigest()[:8]


# --------------------------------------------------------------------- Leitner

def next_box(box: int, correct: bool) -> int:
    """答对 +1（最多 5）；答错或"不会"回到 1 号盒（经典 Leitner）。"""
    if correct:
        return min(5, box + 1)
    return 1


def next_review(box: int, today: Optional[date] = None) -> date:
    intervals = get_settings().leitner_intervals_list
    days = intervals[box - 1]
    today = today or datetime.now(timezone.utc).date()
    return today + timedelta(days=days)


@dataclass
class MasteryState:
    topic_id: str
    topic_name: str
    box: int = 1
    correct: int = 0
    wrong: int = 0
    next_review: Optional[date] = None
    updated: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def apply_answer(self, correct: bool, today: Optional[date] = None) -> "MasteryState":
        today = today or datetime.now(timezone.utc).date()
        new_box = next_box(self.box, correct)
        return MasteryState(
            topic_id=self.topic_id,
            topic_name=self.topic_name,
            box=new_box,
            correct=self.correct + (1 if correct else 0),
            wrong=self.wrong + (0 if correct else 1),
            next_review=next_review(new_box, today),
            updated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )


def format_mastery_text(state: MasteryState) -> str:
    """第一行给人看；后面几行机器可解析。"""
    nr = state.next_review.isoformat() if state.next_review else ""
    first = (f"掌握度：{state.topic_name}（{state.topic_id}）—— 盒 {state.box}，"
             f"答对 {state.correct} 次 / 答错 {state.wrong} 次，"
             f"下次复习 {nr}")
    lines = [
        first,
        f"topic_id: {state.topic_id}",
        f"topic_name: {state.topic_name}",
        f"box: {state.box}",
        f"correct: {state.correct}",
        f"wrong: {state.wrong}",
        f"next_review: {nr}",
    ]
    if state.updated:
        lines.append(f"updated: {state.updated}")
    return "\n".join(lines)


def parse_mastery_text(text: str) -> Optional[MasteryState]:
    """从卡片文本解析回状态；解析不出 topic_id 时返回 None。"""
    kv: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("掌握度"):
            key, _, value = line.partition(":")
            kv[key.strip()] = value.strip()
    topic_id = kv.get("topic_id")
    if not topic_id:
        return None
    nr = kv.get("next_review")
    return MasteryState(
        topic_id=topic_id,
        topic_name=kv.get("topic_name", ""),
        box=int(kv.get("box", 1)),
        correct=int(kv.get("correct", 0)),
        wrong=int(kv.get("wrong", 0)),
        next_review=date.fromisoformat(nr) if nr else None,
        updated=kv.get("updated"),
    )


# --------------------------------------------------------------------- mistake

def format_mistake_text(topic_id: str, topic_name: str, question: str,
                        learner_answer: str, correct_answer: str, source: str) -> str:
    """错题记忆：只写判分确定的事实（题目、学生答案、正确答案、出处）。"""
    lines = [
        f"【错题】{topic_id} {topic_name}：题目「{question}」",
        f"你的回答「{learner_answer}」，正确答案「{correct_answer}」，出处 {source}",
        f"topic_id: {topic_id}",
        f"topic_name: {topic_name}",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ review plan

@dataclass
class ReviewPlanData:
    opening: str
    wrong_recent: list[str] = field(default_factory=list)   # ["t08:2", ...]
    due_today: list[str] = field(default_factory=list)      # ["t03", ...]
    blind_missing: list[str] = field(default_factory=list)  # ["t04", ...]
    updated: Optional[str] = None


def build_review_plan(data: ReviewPlanData) -> str:
    """第一行就是下次开场要说的话。"""
    lines = [data.opening]
    if data.wrong_recent:
        lines.append("wrong_recent: " + ",".join(data.wrong_recent))
    if data.due_today:
        lines.append("due_today: " + ",".join(data.due_today))
    if data.blind_missing:
        lines.append("blind_missing: " + ",".join(data.blind_missing))
    if data.updated:
        lines.append(f"updated: {data.updated}")
    return "\n".join(lines)


def parse_review_plan(text: str) -> Optional[ReviewPlanData]:
    if not text:
        return None
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    kv: dict[str, str] = {}
    for line in lines[1:]:
        key, _, value = line.strip().partition(":")
        kv[key.strip()] = value.strip()
    return ReviewPlanData(
        opening=lines[0].strip(),
        wrong_recent=[x for x in kv.get("wrong_recent", "").split(",") if x],
        due_today=[x for x in kv.get("due_today", "").split(",") if x],
        blind_missing=[x for x in kv.get("blind_missing", "").split(",") if x],
        updated=kv.get("updated"),
    )


def build_opening_line(wrong_recent: list[tuple[str, str, int]],
                       due_today: list[tuple[str, str]],
                       blind_missing: list[tuple[str, str, float]]) -> str:
    """开场白，例如：
    上次你在『隔离级别与 MVCC』上错了 2 次，先复习它；『B+树与哈希索引』今天到期；
    『函数依赖与范式』往年考 25 分但笔记里没有。

    同一个知识点只出现一次：既错了又是盲区的合并成一句
    （『X』上错了 N 次（往年考 25 分但笔记里没有））。
    """
    blind_by_tid = {tid: (name, weight) for tid, name, weight in blind_missing}
    parts: list[str] = []
    mentioned: set[str] = set()

    def _blind_note(tid: str) -> str:
        info = blind_by_tid.get(tid)
        if not info:
            return ""
        return f"（往年考 {info[1]:g} 分但笔记里没有）"

    if wrong_recent:
        tid, name, count = wrong_recent[0]
        parts.append(f"上次你在『{name}』上错了 {count} 次，先复习它{_blind_note(tid)}")
        mentioned.add(tid)
        for tid, name, count in wrong_recent[1:3]:
            parts.append(f"『{name}』错了 {count} 次{_blind_note(tid)}")
            mentioned.add(tid)
    for tid, name in due_today[:3]:
        if tid in mentioned:
            continue
        parts.append(f"『{name}』今天到期{_blind_note(tid)}")
        mentioned.add(tid)
    for tid, name, weight in blind_missing[:2]:
        if tid in mentioned:
            continue
        parts.append(f"『{name}』往年考 {weight:g} 分但笔记里没有")
        mentioned.add(tid)
    if not parts:
        return "上次没有留下复习记录，从头开始按考试权重复习吧"
    return "；".join(parts)


# ---------------------------------------------------------------- session summary

def format_session_summary(duration_minutes: float, questions_asked: int,
                           questions_correct: int, weak_topics: list[tuple[str, str, int]],
                           started_at: Optional[str] = None) -> str:
    rate = (questions_correct / questions_asked * 100) if questions_asked else 0.0
    first = (f"会话小结：时长 {duration_minutes:.0f} 分钟，做题 {questions_asked} 道，"
             f"正确率 {rate:.0f}%")
    if weak_topics:
        names = "、".join(f"{name}（{topic_id}，错 {count} 次）"
                          for topic_id, name, count in weak_topics[:5])
        first += f"，薄弱点：{names}"
    lines = [first,
             f"duration_minutes: {duration_minutes:.1f}",
             f"questions_asked: {questions_asked}",
             f"questions_correct: {questions_correct}"]
    if weak_topics:
        lines.append("weak_topics: " +
                     ",".join(f"{tid}:{count}" for tid, _n, count in weak_topics))
    if started_at:
        lines.append(f"started_at: {started_at}")
    return "\n".join(lines)


# ------------------------------------------------------------------- grading

def normalize_answer(text: str) -> str:
    """判分归一化：忽略空白、全半角、大小写。"""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = "".join(text.split())
    return text.lower()


def grade_fill(expected: str, answer: str) -> bool:
    return normalize_answer(expected) == normalize_answer(answer)


def grade_choice(expected: str, answer: str) -> bool:
    return normalize_answer(expected) == normalize_answer(answer)
