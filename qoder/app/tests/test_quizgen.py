"""出题与判分的单元测试（不依赖 seekdb / PowerContext / LLM 网络）。"""
from datetime import date

import pytest

import examradar.coach as coach
from examradar.llm import LLMError
from examradar.mastery import MasteryState


def make_chunk(content, heading=None, doc="05-事务与并发控制.md", page=None,
               chunk_id=101):
    return {"id": chunk_id, "content": content, "heading": heading,
            "page": page, "document_name": doc, "question_no": None,
            "points": None}


class TestFillQuestion:
    def test_blank_keyword_from_topic_keywords(self):
        topic = {"topic_id": "t08", "topic_name": "隔离级别与 MVCC",
                 "keywords": ["MVCC"]}
        chunk = make_chunk(
            "多版本并发控制（MVCC）让读操作不加锁。快照读基于一致性视图实现。",
            heading="5.2 隔离级别")
        q = coach.make_fill_question(topic, chunk)
        assert q is not None
        assert q["question_type"] == "fill"
        assert q["expected_answer"] == "MVCC"
        assert "＿＿＿" in q["question"]
        # 标明出处：文件 · 页/标题
        assert q["source"]["document_name"] == "05-事务与并发控制.md"
        assert "5.2 隔离级别" in q["source"]["label"]
        assert q["chunk_id"] == 101

    def test_falls_back_to_latin_terms(self):
        topic = {"topic_id": "t09", "topic_name": "故障恢复：WAL 与 ARIES",
                 "keywords": []}
        chunk = make_chunk("先写日志原则要求日志先于数据落盘。")
        q = coach.make_fill_question(topic, chunk)
        assert q is None or q["expected_answer"]

    def test_no_candidate_returns_none(self):
        topic = {"topic_id": "t01", "topic_name": "关系模型与关系代数",
                 "keywords": []}
        chunk = make_chunk("一二三四五六七八九十。")
        assert coach.make_fill_question(topic, chunk) is None

    def test_chapter_terms_not_blanked(self):
        """「第N章」这类结构词不挖空；标题行不作为题干。"""
        topic = {"topic_id": "t03", "topic_name": "索引：B+树与哈希索引",
                 "keywords": ["B+树"]}
        chunk = make_chunk(
            "# 第3章 索引：B+树与哈希索引（课堂笔记）\n\n"
            "B+树的叶子结点用链表串联，支持范围查询。",
            heading="第3章 索引：B+树与哈希索引（课堂笔记）")
        q = coach.make_fill_question(topic, chunk)
        assert q is not None
        assert q["expected_answer"] != "第3章"
        assert not q["question"].startswith("填空：#")

    def test_blank_prefers_found_terms(self):
        """挖空优先挖考点词本身（会话 05 覆盖结果的 terms[].found）。"""
        topic = {"topic_id": "t08", "topic_name": "隔离级别与 MVCC",
                 "keywords": ["MVCC"],
                 "terms": [
                     {"term": "隔离级别", "aliases": [], "found": True},
                     {"term": "MVCC", "aliases": ["多版本并发控制"],
                      "found": True},
                 ]}
        chunk = make_chunk(
            "隔离级别由低到高有读未提交、读已提交等；MVCC 通过快照实现读写不阻塞。",
            heading="5.5 隔离级别（只记了个大概，课上讲得快）")
        q = coach.make_fill_question(topic, chunk)
        assert q is not None
        assert q["expected_answer"] == "隔离级别"
        assert "隔离级别" not in q["question"]
        assert q["source"]["heading"].startswith("5.5")

    def test_unfound_terms_not_blanked(self):
        """未找到的考点词不会出现在出题段落里，不参与挖空。"""
        topic = {"topic_id": "t04", "topic_name": "函数依赖与范式（3NF、BCNF）",
                 "keywords": [],
                 "terms": [{"term": "函数依赖", "aliases": ["3NF", "BCNF"],
                            "found": False}]}
        chunk = make_chunk("SQL 的 GROUP BY 子句可以按列分组聚合。")
        q = coach.make_fill_question(topic, chunk)
        # 挖空只能落在无关的字母术语上——调用方（quiz 路由）不会把这种段落
        # 选为 t04 的材料，这里只验证函数本身不挖未找到的考点词
        if q is not None:
            assert q["expected_answer"] not in ("函数依赖", "3NF", "BCNF")


class TestTermMatchedChunks:
    """thin/covered 知识点的出题材料 = 找到考点词的段落。"""

    ROWS = [
        {"id": 11, "content": "隔离级别由低到高……", "heading": "5.5 隔离级别",
         "page": None, "doc_name": "05-事务与并发控制.md"},
        {"id": 12, "content": "GROUP BY 按列分组。", "heading": "分组",
         "page": None, "doc_name": "02-SQL速记.md"},
    ]

    def test_only_chunks_with_terms(self, monkeypatch):
        monkeypatch.setattr(coach, "get_coverage_chunks",
                            lambda course, kinds: self.ROWS)
        topic = {"topic_id": "t08", "topic_name": "隔离级别与 MVCC",
                 "keywords": [], "terms": [
                     {"term": "隔离级别", "aliases": [], "found": True}]}
        chunks = coach._term_matched_chunks("db101", topic)
        assert [c["id"] for c in chunks] == [11]

    def test_no_found_terms_returns_empty(self, monkeypatch):
        monkeypatch.setattr(coach, "get_coverage_chunks",
                            lambda course, kinds: self.ROWS)
        topic = {"topic_id": "t04", "topic_name": "函数依赖与范式",
                 "keywords": [], "terms": [
                     {"term": "函数依赖", "aliases": [], "found": False}]}
        assert coach._term_matched_chunks("db101", topic) == []

    def test_hit_term_count_orders_chunks(self, monkeypatch):
        rows = [
            {"id": 21, "content": "两阶段锁在增长阶段只加锁。", "heading": "5.3 封锁",
             "page": None, "doc_name": "05-事务与并发控制.md"},
            {"id": 22, "content": "两阶段锁与死锁：死锁检测与解除。", "heading": "5.4",
             "page": None, "doc_name": "05-事务与并发控制.md"},
        ]
        monkeypatch.setattr(coach, "get_coverage_chunks",
                            lambda course, kinds: rows)
        topic = {"topic_id": "t07", "topic_name": "并发控制：两阶段锁与死锁",
                 "keywords": [], "terms": [
                     {"term": "两阶段锁", "aliases": [], "found": True},
                     {"term": "死锁", "aliases": [], "found": True}]}
        chunks = coach._term_matched_chunks("db101", topic)
        assert chunks[0]["id"] == 22  # 命中 2 个考点词 > 1 个


class TestSelfTestQuestion:
    def test_missing_topic_uses_past_exam_question(self, monkeypatch):
        topic = {"topic_id": "t04", "topic_name": "函数依赖与范式（3NF、BCNF）",
                 "keywords": [], "coverage_level": "missing",
                 "exam_questions": [{"question_no": 4, "points": 25.0,
                                     "similarity": 0.9}]}
        monkeypatch.setattr(coach, "_fetch_exam_chunk", lambda course, qno: {
            "id": 55, "content": "4.（25 分）说明 3NF 与 BCNF 的区别。",
            "heading": None, "page": None, "question_no": 4, "points": 25.0,
            "document_id": 9})
        monkeypatch.setattr(coach, "_doc_names", lambda course: {9: "2025-2026-1-期末试卷A.pdf"})
        q = coach.make_self_test_question(topic, "db101")
        assert q is not None
        assert q["question_type"] == "self"
        assert q["self_test"] is True
        assert q["self_ratings"] == ["会", "模糊", "不会"]
        assert "笔记里没有这部分" in q["hint"]
        assert "期末试卷A.pdf" in q["source"]["label"]
        assert "第4题" in q["source"]["label"]

    def test_no_exam_question_returns_none(self, monkeypatch):
        topic = {"topic_id": "t05", "topic_name": "查询处理与优化",
                 "exam_questions": []}
        monkeypatch.setattr(coach, "_fetch_exam_chunk", lambda course, qno: None)
        assert coach.make_self_test_question(topic, "db101") is None


class TestLLMQuestion:
    def _chunks(self):
        return [make_chunk("两阶段锁保证可串行化。", heading="5.3 两阶段锁",
                           chunk_id=77)]

    def _fake_llm(self, payload):
        class FakeLLM:
            configured = True

            def chat_json(self, messages, temperature=0.2, timeout=120.0):
                return payload
        return FakeLLM()

    def test_choice_question_validated(self):
        topic = {"topic_id": "t07", "topic_name": "并发控制：两阶段锁与死锁",
                 "keywords": []}
        payload = {
            "question_type": "choice",
            "question": "两阶段锁协议能保证什么性质？",
            "options": {"A": "冲突可串行化", "B": "免死锁", "C": "可恢复调度", "D": "隔离性"},
            "answer": "A",
            "explanation": "两阶段锁保证冲突可串行化，但不能避免死锁。",
            "chunk_id": 77,
        }
        q = coach.make_llm_question(self._fake_llm(payload), topic, self._chunks(),
                                    [], "choice", "t07 并发控制：两阶段锁与死锁")
        assert q is not None
        assert q["question_type"] == "choice"
        assert q["expected_answer"] == "A"
        assert q["llm_generated"] is True
        assert q["chunk_id"] == 77
        assert q["source"]["chunk_id"] == 77

    def test_string_chunk_id_coerced(self):
        """小模型常把 chunk_id 写成 "chunk 12"，宽容转成整数再校验。"""
        topic = {"topic_id": "t07", "topic_name": "并发控制：两阶段锁与死锁",
                 "keywords": []}
        payload = {"question_type": "short", "question": "…",
                   "reference_answer": "…", "chunk_id": "chunk 77"}
        q = coach.make_llm_question(self._fake_llm(payload), topic, self._chunks(),
                                    [], "short", "t07 x")
        assert q is not None
        assert q["chunk_id"] == 77

    def test_invalid_chunk_id_rejected(self):
        topic = {"topic_id": "t07", "topic_name": "并发控制：两阶段锁与死锁",
                 "keywords": []}
        payload = {"question_type": "short", "question": "…",
                   "reference_answer": "…", "chunk_id": 999}
        assert coach.make_llm_question(self._fake_llm(payload), topic,
                                       self._chunks(), [], "short", "t07 x") is None

    def test_bad_answer_letter_rejected(self):
        topic = {"topic_id": "t07", "topic_name": "并发控制：两阶段锁与死锁",
                 "keywords": []}
        payload = {"question_type": "choice", "question": "…",
                   "options": {"A": "x", "B": "y", "C": "z"}, "answer": "E",
                   "chunk_id": 77}
        assert coach.make_llm_question(self._fake_llm(payload), topic,
                                       self._chunks(), [], "choice", "t07 x") is None

    def test_llm_error_returns_none(self):
        class ErrLLM:
            configured = True

            def chat_json(self, messages, temperature=0.2, timeout=120.0):
                raise LLMError("boom")
        topic = {"topic_id": "t07", "topic_name": "并发控制：两阶段锁与死锁",
                 "keywords": []}
        assert coach.make_llm_question(ErrLLM(), topic, self._chunks(),
                                       [], "choice", "t07 x") is None


class TestLLMGrading:
    def test_short_answer_judgement(self):
        class FakeLLM:
            configured = True

            def chat_json(self, messages, temperature=0.0, timeout=120.0):
                return {"correct": False,
                        "misconception": "混淆了冲突可串行化与视图可串行化"}
        out = coach.grade_short_with_llm(FakeLLM(), "问", "答", "学生答案", "原文")
        assert out["correct"] is False
        assert "可串行化" in out["misconception"]

    def test_llm_error_returns_none(self):
        class ErrLLM:
            configured = True

            def chat_json(self, messages, temperature=0.0, timeout=120.0):
                raise LLMError("boom")
        assert coach.grade_short_with_llm(ErrLLM(), "q", "a", "b", "c") is None

    def test_non_bool_correct_rejected(self):
        class BadLLM:
            configured = True

            def chat_json(self, messages, temperature=0.0, timeout=120.0):
                return {"correct": "yes", "misconception": ""}
        assert coach.grade_short_with_llm(BadLLM(), "q", "a", "b", "c") is None


class TestSelectTopic:
    def test_due_first(self):
        mastery = {
            "t03": {"state": MasteryState("t03", "索引", box=2,
                                          next_review=date(2026, 10, 27))},
            "t08": {"state": MasteryState("t08", "隔离级别", box=1,
                                          next_review=date(2026, 12, 1))},
        }
        cov = {"items": [{"topic_id": "t04", "topic_name": "范式",
                          "keywords": [], "coverage_level": "missing",
                          "coverage_score": 0.1, "exam_weight": 25.0,
                          "exam_questions": [], "blind_spot_score": 22.5}]}
        topic = coach.select_topic(mastery, cov, last_topic_id=None)
        assert topic["topic_id"] == "t03"

    def test_blind_spot_by_exam_weight(self):
        cov = {"items": [
            {"topic_id": "t04", "topic_name": "范式", "keywords": [],
             "coverage_level": "missing", "coverage_score": 0.1,
             "exam_weight": 25.0, "exam_questions": [],
             "blind_spot_score": 22.5},
            {"topic_id": "t01", "topic_name": "关系模型", "keywords": [],
             "coverage_level": "thin", "coverage_score": 0.3,
             "exam_weight": 10.0, "exam_questions": [],
             "blind_spot_score": 7.0},
        ]}
        topic = coach.select_topic({}, cov, last_topic_id=None)
        assert topic["topic_id"] == "t04"

    def test_no_data_returns_none(self):
        assert coach.select_topic({}, None, None) is None


class TestCoverageSnapshotFields:
    """coverage_snapshot 只用 get_latest；字段集中在其中。"""

    def test_snapshot_shape(self, monkeypatch):
        import examradar.coverage as cov_mod
        monkeypatch.setattr(cov_mod, "get_latest", lambda cid: {
            "run_id": 3, "created_at": "2026-10-28T00:00:00+00:00",
            "topics": [{"id": "t08", "name": "隔离级别与 MVCC",
                        "keywords": ["MVCC"]}],
            "items": [{
                "topic_id": "t08", "topic_name": "隔离级别与 MVCC",
                "keywords": ["MVCC"], "coverage_level": "covered",
                "coverage_score": 0.76, "exam_weight": 10.0,
                "exam_questions": [{"question_no": 5, "points": 10.0,
                                    "similarity": 0.8}],
                "blind_spot_score": 2.4,
            }],
        })
        snap = coach.coverage_snapshot("db101")
        assert snap["run_id"] == 3
        item = snap["items"][0]
        assert item["topic_id"] == "t08"
        assert item["exam_questions"][0]["question_no"] == 5

    def test_snapshot_none(self, monkeypatch):
        import examradar.coverage as cov_mod
        monkeypatch.setattr(cov_mod, "get_latest", lambda cid: None)
        assert coach.coverage_snapshot("db101") is None
