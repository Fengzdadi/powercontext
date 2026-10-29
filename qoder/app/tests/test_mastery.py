"""Leitner 递推、记忆文本格式、判分归一化的单元测试。"""
from datetime import date

import pytest

from examradar.mastery import (
    MasteryState, ReviewPlanData, build_opening_line, build_review_plan,
    format_mastery_text, format_session_summary, grade_choice, grade_fill,
    learner_hash, next_box, next_review, normalize_answer, parse_mastery_text,
    parse_review_plan,
)


# --------------------------------------------------------------------- Leitner

class TestLeitner:
    def test_correct_advances_box(self):
        assert next_box(1, True) == 2
        assert next_box(2, True) == 3
        assert next_box(4, True) == 5

    def test_correct_caps_at_5(self):
        assert next_box(5, True) == 5

    def test_wrong_resets_to_box_1(self):
        assert next_box(3, False) == 1
        assert next_box(5, False) == 1
        assert next_box(1, False) == 1

    def test_intervals_from_config(self):
        from examradar.config import get_settings
        assert get_settings().leitner_intervals_list == [1, 2, 4, 7, 14]

    def test_next_review_uses_box_interval(self):
        today = date(2026, 10, 28)
        assert next_review(1, today) == date(2026, 10, 29)
        assert next_review(2, today) == date(2026, 10, 30)
        assert next_review(5, today) == date(2026, 11, 11)

    def test_apply_answer_wrong_then_correct(self):
        st = MasteryState(topic_id="t08", topic_name="隔离级别与 MVCC",
                          box=3, correct=2, wrong=1)
        wrong = st.apply_answer(False, today=date(2026, 10, 28))
        assert wrong.box == 1
        assert wrong.wrong == 2
        assert wrong.correct == 2
        assert wrong.next_review == date(2026, 10, 29)
        right = wrong.apply_answer(True, today=date(2026, 10, 28))
        assert right.box == 2
        assert right.next_review == date(2026, 10, 30)


# ------------------------------------------------------------- mastery format

class TestMasteryText:
    def test_roundtrip(self):
        st = MasteryState(topic_id="t03", topic_name="索引：B+树与哈希索引",
                          box=4, correct=5, wrong=2,
                          next_review=date(2026, 11, 4), updated="2026-10-28T01:00:00Z")
        text = format_mastery_text(st)
        # 第一行给人看，且包含知识点 id 和名称（全文召回依赖）
        first = text.splitlines()[0]
        assert "t03" in first and "索引：B+树与哈希索引" in first
        parsed = parse_mastery_text(text)
        assert parsed.topic_id == "t03"
        assert parsed.topic_name == "索引：B+树与哈希索引"
        assert parsed.box == 4
        assert parsed.correct == 5
        assert parsed.wrong == 2
        assert parsed.next_review == date(2026, 11, 4)

    def test_parse_garbage_returns_none(self):
        assert parse_mastery_text("随便一段话\n没有键值") is None

    def test_text_first_line_human_readable(self):
        st = MasteryState(topic_id="t01", topic_name="关系模型与关系代数",
                          box=1, correct=0, wrong=3, next_review=date(2026, 10, 29))
        first = format_mastery_text(st).splitlines()[0]
        assert "盒 1" in first and "答对 0 次 / 答错 3 次" in first


# ------------------------------------------------------------- review plan

class TestReviewPlan:
    def test_roundtrip(self):
        text = build_review_plan(ReviewPlanData(
            opening="你在『隔离级别与 MVCC』上累计错了 2 次，先复习它",
            wrong_recent=["t08:2"], due_today=["t03"], blind_missing=["t04"],
            updated="2026-10-28T01:00:00Z"))
        plan = parse_review_plan(text)
        assert plan.opening == "你在『隔离级别与 MVCC』上累计错了 2 次，先复习它"
        assert plan.wrong_recent == ["t08:2"]
        assert plan.due_today == ["t03"]
        assert plan.blind_missing == ["t04"]

    def test_opening_line_parts(self):
        line = build_opening_line(
            wrong_recent=[("t08", "隔离级别与 MVCC", 2)],
            due_today=[("t03", "索引：B+树与哈希索引")],
            blind_missing=[("t04", "函数依赖与范式（3NF、BCNF）", 25.0)])
        assert "你在『隔离级别与 MVCC』上累计错了 2 次，先复习它" in line
        assert "『索引：B+树与哈希索引』今天到期" in line
        assert "『函数依赖与范式（3NF、BCNF）』往年考 25 分但笔记里没有" in line

    def test_opening_line_empty(self):
        assert "复习" in build_opening_line([], [], [])

    def test_opening_line_counts_are_cumulative_wording(self):
        """开场白次数取自掌握度卡片的累计答错数，说法不能用"上次"。"""
        line = build_opening_line(
            wrong_recent=[("t04", "函数依赖与范式（3NF、BCNF）", 4),
                          ("t08", "隔离级别与 MVCC", 1)],
            due_today=[], blind_missing=[])
        assert "你在『函数依赖与范式（3NF、BCNF）』上累计错了 4 次，先复习它" in line
        assert "『隔离级别与 MVCC』累计错了 1 次" in line
        assert "上次" not in line

    def test_opening_line_counts_match_mastery_cumulative_wrong(self):
        """build_review_plan_inputs 传入的是掌握度卡片累计答错数，开场白原样带出。"""
        from examradar.coach import build_review_plan_inputs
        mastery = {
            "t04": {"state": MasteryState("t04", "函数依赖与范式（3NF、BCNF）",
                                          wrong=4)},
            "t08": {"state": MasteryState("t08", "隔离级别与 MVCC", wrong=1)},
        }
        wrong_recent, due_today, blind_missing = build_review_plan_inputs(
            mastery, {"items": []})
        line = build_opening_line(wrong_recent, due_today, blind_missing)
        assert "累计错了 4 次" in line
        assert "累计错了 1 次" in line
        assert "上次" not in line

    def test_opening_line_topic_mentioned_once(self):
        """既错了又是盲区的知识点在开场白里合成一句，不出现两次。"""
        line = build_opening_line(
            wrong_recent=[("t04", "函数依赖与范式（3NF、BCNF）", 2)],
            due_today=[],
            blind_missing=[("t04", "函数依赖与范式（3NF、BCNF）", 25.0)])
        assert line.count("函数依赖与范式") == 1
        assert "累计错了 2 次" in line
        assert "往年考 25 分但笔记里没有" in line

    def test_opening_line_due_and_blind_merged(self):
        line = build_opening_line(
            wrong_recent=[("t08", "隔离级别与 MVCC", 1)],
            due_today=[("t02", "SQL 查询")],
            blind_missing=[("t02", "SQL 查询", 20.0),
                           ("t04", "函数依赖与范式（3NF、BCNF）", 25.0)])
        assert line.count("SQL 查询") == 1
        assert "『SQL 查询』今天到期（往年考 20 分但笔记里没有）" in line
        assert "『函数依赖与范式（3NF、BCNF）』往年考 25 分但笔记里没有" in line


# ---------------------------------------------------------------- session text

class TestSessionSummary:
    def test_summary_contains_stats(self):
        text = format_session_summary(
            12.5, 6, 4, [("t08", "隔离级别与 MVCC", 2)],
            started_at="2026-10-28T01:00:00+00:00")
        assert "12 分钟" in text or "13 分钟" in text
        assert "做题 6 道" in text
        assert "正确率 67%" in text
        assert "隔离级别与 MVCC" in text


# ------------------------------------------------------------------- grading

class TestGrading:
    def test_normalize_ignores_whitespace_width_case(self):
        assert normalize_answer(" MVCC ") == normalize_answer("ｍｖｃｃ")
        assert normalize_answer("两阶段 锁") == normalize_answer("两阶段锁")
        assert normalize_answer("ＷＡＬ") == normalize_answer("wal")

    def test_grade_fill(self):
        assert grade_fill("MVCC", " ｍｖｃｃ ")
        assert not grade_fill("MVCC", "WAL")

    def test_grade_choice_exact(self):
        assert grade_choice("A", "A")
        assert not grade_choice("A", "B")
        assert grade_choice("A", "a")


# ---------------------------------------------------------------------- hash

class TestPrivacy:
    def test_learner_hash_is_short_and_stable(self):
        h1 = learner_hash("验收同学")
        assert h1 == learner_hash("验收同学")
        assert len(h1) == 8
        assert h1 != learner_hash("别的同学")
        assert "验收同学" not in h1
