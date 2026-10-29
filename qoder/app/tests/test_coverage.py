"""Unit tests for coverage judgment logic, on constructed mini-corpus data.

These use no database and no sample data: the rules must generalize, not
just classify the course-db sample.
"""
from examradar.coverage import (
    judge_topic, match_variant, term_matches, body_text,
    evaluate_topic, assign_question, build_reason, make_chunk,
    blind_spot_sort_key,
)
from examradar.syllabus import parse_syllabus, parse_terms, normalize_for_match


class TestNormalizeForMatch:
    def test_fullwidth_to_halfwidth(self):
        assert normalize_for_match("ＳＱＬ 查询") == "sql查询"

    def test_casefold(self):
        assert normalize_for_match("ACID") == "acid"

    def test_whitespace_removed(self):
        assert normalize_for_match("事务的\nACID 特性") == "事务的acid特性"


class TestParseTerms:
    def test_colon_and_conjunction(self):
        terms = parse_terms("索引：B+树与哈希索引")
        assert [t.text for t in terms] == ["索引", "B+树", "哈希索引"]

    def test_paren_aliases_attach_to_previous_term(self):
        terms = parse_terms("函数依赖与范式（3NF、BCNF）")
        assert [t.text for t in terms] == ["函数依赖", "范式"]
        assert terms[1].aliases == ["3NF", "BCNF"]

    def test_single_alias(self):
        terms = parse_terms("分布式事务与两阶段提交（2PC）")
        assert terms[1].aliases == ["2PC"]

    def test_no_split_inside_multiterm_word(self):
        terms = parse_terms("事务的 ACID 特性")
        assert [t.text for t in terms] == ["事务的 ACID 特性"]


class TestMatchVariant:
    def test_contiguous_single_token(self):
        assert match_variant("索引是一种额外的数据结构", "索引")

    def test_not_present(self):
        assert not match_variant("索引是一种额外的数据结构", "视图")

    def test_fullwidth_case_insensitive(self):
        assert match_variant("使用 ２ＰＣ 协议", "2pc")

    def test_multitoken_all_present(self):
        assert match_variant("多表查询用 JOIN，SQL 基础", "SQL 查询")

    def test_multitoken_one_of_two_not_enough(self):
        # 查询 alone must not count as "查询处理"
        assert not match_variant("按查询条件查找", "查询处理")

    def test_multitoken_strict_majority(self):
        # "事务的 ACID 特性": 事务+ACID present, generic 特性 missing
        assert match_variant("事务由 ACID 保证", "事务的 ACID 特性")

    def test_multitoken_minority_fails(self):
        assert not match_variant("事务开始", "事务的 ACID 特性")


class TestTermMatches:
    def test_alias_counts(self):
        term = parse_terms("范式（3NF、BCNF）")[0]
        assert term_matches(term, normalize_for_match("分解为满足 BCNF 的模式"))
        assert term_matches(term, normalize_for_match("判断最高属于第几范式"))
        assert not term_matches(term, normalize_for_match("关系代数"))

    def test_contiguous_beats_word_order(self):
        term = parse_terms("SQL 查询")[0]
        assert term_matches(term, normalize_for_match("写出 SQL 的查询语句"))


class TestBodyText:
    def test_markdown_headings_excluded(self):
        assert body_text("## 分组\n\n- `GROUP BY` 分组后配合聚集函数。") == \
            "- `GROUP BY` 分组后配合聚集函数。"

    def test_title_only_chunk_has_tiny_body(self):
        assert len(body_text("第3章 索引\n\n> 第 5 周课堂笔记。")) < 20


# -- judgment ----------------------------------------------------------------

RATIO_T, SUPPORT_T, MIN_BODY = 0.5, 280, 50


class TestJudgeTopic:
    def test_missing(self):
        level, score = judge_topic(0, 3, 0, RATIO_T, SUPPORT_T)
        assert level == "missing"
        assert score == 0.0

    def test_covered(self):
        level, score = judge_topic(3, 3, 800, RATIO_T, SUPPORT_T)
        assert level == "covered"
        assert score >= 0.5

    def test_thin_by_support(self):
        # all terms found but only one small paragraph
        level, score = judge_topic(2, 2, 118, RATIO_T, SUPPORT_T)
        assert level == "thin"
        assert 0 < score < 0.5

    def test_thin_by_ratio(self):
        # one of three terms found, plenty of text about the wrong part
        level, score = judge_topic(1, 3, 2000, RATIO_T, SUPPORT_T)
        assert level == "thin"
        assert 0 < score < 0.5

    def test_half_ratio_with_big_support_is_covered(self):
        # e.g. the term only appears in an English reading (via its alias)
        level, _ = judge_topic(1, 2, 3000, RATIO_T, SUPPORT_T)
        assert level == "covered"

    def test_boundary_support_is_covered(self):
        assert judge_topic(2, 2, SUPPORT_T, RATIO_T, SUPPORT_T)[0] == "covered"

    def test_boundary_ratio_is_covered(self):
        # 1 of 2 terms exactly meets ratio_threshold 0.5
        assert judge_topic(1, 2, 400, RATIO_T, SUPPORT_T)[0] == "covered"

    def test_no_terms(self):
        assert judge_topic(0, 0, 0, RATIO_T, SUPPORT_T)[0] == "missing"


# -- evaluate_topic on a constructed mini corpus ------------------------------

SYLLABUS = """考试范围
1. 视图与子查询
2. 两阶段锁与死锁
3. 分布式事务与两阶段提交（2PC）"""


def _corpus():
    return [
        # big paragraph about 视图 (t01 term 1)
        make_chunk(1, "视图是虚表，对视图的查询会被改写为对基本表的查询。"
                      "视图可以简化常用查询的书写，也可以提供权限隔离。" * 6,
                   heading="视图", document_name="n1.md"),
        # one-line chunk: 子查询 only in its heading, body says "not recorded"
        make_chunk(2, "## 子查询\n\n（这节没记）", heading="子查询",
                   document_name="n1.md"),
        # solid coverage of t02
        make_chunk(3, "两阶段锁协议要求加锁和解锁分成两个阶段。"
                      "增长阶段只能加锁，收缩阶段只能解锁。" * 8,
                   heading="封锁与两阶段锁协议", document_name="n2.md"),
        make_chunk(4, "死锁：事务互相等待对方持有的锁。检测方法包括等待图和超时法。" * 2,
                   heading="死锁", document_name="n2.md"),
        # t03: Chinese term absent, but 2PC appears in an English paragraph
        make_chunk(5, "Two-phase commit (2PC) is the most widely used atomic "
                      "commitment protocol. " * 4,
                   heading="2PC", document_name="paper.md"),
        # both terms of a small topic in one short paragraph -> thin
        make_chunk(6, "隔离级别包括读已提交和可重复读。MVCC 实现快照读。",
                   heading="隔离级别", document_name="n3.md"),
    ]


class TestEvaluateTopic:
    def test_topic_with_heading_only_term_is_supported_by_other_term(self):
        topics = parse_syllabus(SYLLABUS)
        chunks = _corpus()
        te, supporting, support = evaluate_topic(topics[0], chunks, MIN_BODY)
        # both terms found; 子查询 only via the one-line chunk's heading
        assert [t.term for t in te if t.found] == ["视图", "子查询"]
        # chunk 2's body is too short to be evidence; chunk 1 supports
        assert [c.chunk_id for c in supporting] == [1]
        level, score = judge_topic(2, 2, support, RATIO_T, SUPPORT_T)
        assert level == "covered"

    def test_all_missing(self):
        topics = parse_syllabus("1. 关系模型与关系代数\n2. 函数依赖与范式")
        te, supporting, support = evaluate_topic(topics[0], _corpus(), MIN_BODY)
        assert not any(t.found for t in te)
        assert supporting == []
        assert support == 0
        level, score = judge_topic(0, 2, 0, RATIO_T, SUPPORT_T)
        assert (level, score) == ("missing", 0.0)

    def test_covered_topic(self):
        topics = parse_syllabus(SYLLABUS)
        te, supporting, support = evaluate_topic(topics[1], _corpus(), MIN_BODY)
        assert all(t.found for t in te)
        assert len(supporting) == 2
        assert support > SUPPORT_T
        level, score = judge_topic(2, 2, support, RATIO_T, SUPPORT_T)
        assert level == "covered"
        assert score >= 0.5

    def test_thin_topic_small_support(self):
        # both terms found but the only paragraph is tiny -> thin, not covered
        topics = parse_syllabus("1. 隔离级别与 MVCC")
        te, supporting, support = evaluate_topic(topics[0], _corpus(), MIN_BODY)
        assert all(t.found for t in te)
        assert supporting == []
        assert support == 0
        level, score = judge_topic(2, 2, support, RATIO_T, SUPPORT_T)
        assert level == "thin"
        assert score < 0.5

    def test_alias_via_english_paper(self):
        topics = parse_syllabus(SYLLABUS)
        te, supporting, support = evaluate_topic(topics[2], _corpus(), MIN_BODY)
        by_term = {t.term: t for t in te}
        assert not by_term["分布式事务"].found
        assert by_term["两阶段提交"].found  # via 2PC alias
        level, score = judge_topic(1, 2, support, RATIO_T, SUPPORT_T)
        assert level == "covered"

    def test_title_only_chunk_is_not_evidence(self):
        topics = parse_syllabus(SYLLABUS)
        te, supporting, _ = evaluate_topic(topics[0], _corpus(), MIN_BODY)
        sub = next(t for t in te if t.term == "子查询")
        assert sub.found  # appears in chunk 2's heading...
        assert sub.chunk_ids == [2]  # ...but only in that one-line chunk
        assert 2 not in [c.chunk_id for c in supporting]  # not evidence


# -- blind-spot ordering -------------------------------------------------------

class TestBlindSpotSortKey:
    def test_descending_by_score(self):
        order = sorted(
            [{"id": i} for i in ["t01", "t02", "t03"]],
            key=lambda x: blind_spot_sort_key(x["id"],
                                              {"t01": 5, "t02": 25, "t03": 8}[x["id"]]),
        )
        assert [x["id"] for x in order] == ["t02", "t03", "t01"]

    def test_ties_broken_by_topic_id(self):
        items = ["t09", "t02", "t10", "t01"]
        order = sorted(items, key=lambda tid: blind_spot_sort_key(tid, 7.67))
        assert order == ["t01", "t02", "t09", "t10"]

    def test_all_zero_scores_ordered_by_topic_id(self):
        items = ["t05", "t01", "t07", "t03"]
        order = sorted(items, key=lambda tid: blind_spot_sort_key(tid, 0.0))
        assert order == ["t01", "t03", "t05", "t07"]

    def test_none_score_sorts_last_within_zeros(self):
        # get_latest items may carry NULL blind_spot_score
        assert blind_spot_sort_key("t04", None) == (0.0, "t04")


# -- exam question assignment -------------------------------------------------

class TestAssignQuestion:
    def setup_method(self):
        self.topics = parse_syllabus(SYLLABUS)

    def test_term_match_beats_semantics(self):
        # semantics favor t03 but the terms belong to t02
        sims = {"t01": 0.70, "t02": 0.71, "t03": 0.95}
        q = "什么是两阶段锁协议？遵守两阶段锁协议能否避免死锁？举例说明。"
        topic_id, matched = assign_question(q, self.topics, sims)
        assert topic_id == "t02"
        assert sorted(matched) == ["两阶段锁", "死锁"]

    def test_two_topics_match_most_terms_wins(self):
        # question contains terms of both t01 and t02; t02 has 2 matches
        q = "通过视图更新数据有哪些限制？什么是两阶段锁协议，如何避免死锁？"
        sims = {"t01": 0.90, "t02": 0.70, "t03": 0.50}
        topic_id, matched = assign_question(q, self.topics, sims)
        assert topic_id == "t02"
        assert len(matched) == 2

    def test_tie_between_topics_semantics_decides(self):
        # one term from t01 and one from t02 -> tie, semantics decides
        q = "说明视图的作用，并解释死锁的检测方法。"
        sims = {"t01": 0.60, "t02": 0.80, "t03": 0.40}
        topic_id, matched = assign_question(q, self.topics, sims)
        assert topic_id == "t02"
        assert len(matched) == 1

    def test_no_terms_semantics_only(self):
        q = "解释缓冲区管理中 steal 与 no-force 策略的取舍。"
        sims = {"t01": 0.60, "t02": 0.70, "t03": 0.40}
        topic_id, matched = assign_question(q, self.topics, sims)
        assert topic_id == "t02"
        assert matched == []

    def test_alias_in_question(self):
        q = "2PC 的两个阶段分别做什么？为什么说它是阻塞的协议？"
        sims = {"t01": 0.90, "t02": 0.85, "t03": 0.10}
        topic_id, matched = assign_question(q, self.topics, sims)
        assert topic_id == "t03"
        assert matched == ["两阶段提交"]  # via the 2PC alias


class TestBuildReason:
    def _evaluate(self, topic, chunks):
        te, supporting, support = evaluate_topic(topic, chunks, MIN_BODY)
        found = sum(1 for t in te if t.found)
        level, score = judge_topic(found, len(te), support, RATIO_T, SUPPORT_T)
        return build_reason(level, score, te, len(supporting), support), level

    def test_covered_reason_mentions_margin(self):
        topics = parse_syllabus(SYLLABUS)
        reason, level = self._evaluate(topics[1], _corpus())
        assert level == "covered"
        assert "2/2" in reason
        assert "高出 covered 支撑阈值" in reason
        assert "-" not in reason.split("高出 covered 支撑阈值")[1][:10]
        # ratio above threshold is phrased naturally, with the distance kept
        assert "高于阈值 0.5（高出 0.50）" in reason

    def test_covered_reason_at_exact_ratio_says_reached(self):
        # 1 of 2 terms found + big support: ratio exactly meets 0.5
        topics = parse_syllabus(SYLLABUS)
        reason, level = self._evaluate(topics[2], _corpus())
        assert level == "covered"
        assert "考点词比例 1/2，达到阈值 0.5" in reason

    def test_reason_uses_short_refs_and_caps_the_list(self):
        # every chunk repeats the same chapter path; the reason must state
        # doc·last-heading, at most 2 refs per term, then "等 N 段"
        chunks = [
            make_chunk(i,
                       "两阶段锁协议要求加锁和解锁分成两个阶段。增长阶段只能加锁。" * 8,
                       heading=f"第5章 事务管理 > 5.{i} 封锁协议",
                       document_name="notes-事务.md")
            for i in range(1, 5)
        ]
        topics = parse_syllabus("1. 两阶段锁")
        reason, level = self._evaluate(topics[0], chunks)
        assert level == "covered"
        assert "notes-事务.md·5.1 封锁协议" in reason
        assert "第5章 事务管理" not in reason
        assert "等4段" in reason
        # at most two refs listed for the term
        listed = reason.split("两阶段锁→")[1].split("；")[0]
        assert listed.count("notes-事务.md") <= 2

    def test_missing_reason_names_terms(self):
        topics = parse_syllabus("1. 关系模型与关系代数")
        reason, level = self._evaluate(topics[0], _corpus())
        assert level == "missing"
        assert "关系模型" in reason and "关系代数" in reason
        assert "0/2" in reason
