"""Unit tests for chunker.py."""
from examradar.chunker import (
    chunk_markdown, chunk_text, chunk_exam_pdf, Chunk,
)


class TestChunkMarkdown:
    def test_basic_headings(self):
        md = """# Chapter 1

Some intro text.

## Section 1.1

Content of section 1.1.

## Section 1.2

Content of section 1.2.
"""
        chunks = chunk_markdown(md)
        assert len(chunks) >= 3
        headings = [c.heading for c in chunks]
        assert any("Chapter 1" in (h or "") for h in headings)
        assert any("Section 1.1" in (h or "") for h in headings)

    def test_heading_path_preserved(self):
        md = """# Top

## Mid

### Deep

Content here.
"""
        chunks = chunk_markdown(md)
        deep_chunks = [c for c in chunks if c.heading and "Deep" in c.heading]
        assert len(deep_chunks) >= 1
        assert "Top" in deep_chunks[0].heading
        assert "Mid" in deep_chunks[0].heading
        assert "Deep" in deep_chunks[0].heading

    def test_long_section_split(self):
        long_para = "\n\n".join([f"Paragraph {i} with some content." for i in range(20)])
        md = f"# Title\n\n{long_para}"
        chunks = chunk_markdown(md, max_chars=200)
        assert len(chunks) > 1

    def test_empty_input(self):
        assert chunk_markdown("") == []

    def test_chinese_headings(self):
        md = """# 第3章 索引

## 3.1 为什么需要索引

内容。

## 3.2 B+树的结构

更多内容。
"""
        chunks = chunk_markdown(md)
        assert len(chunks) >= 2
        assert any("3.1" in (c.heading or "") for c in chunks)
        assert any("3.2" in (c.heading or "") for c in chunks)


class TestChunkText:
    def test_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, max_chars=30)
        assert len(chunks) == 3

    def test_empty(self):
        assert chunk_text("") == []

    def test_single_paragraph(self):
        chunks = chunk_text("Just one paragraph.")
        assert len(chunks) == 1


class TestChunkExamPdf:
    def test_question_splitting(self):
        text = """2025—2026 学年第一学期《数据库系统原理》期末考试试卷（A 卷）
一、关系模型与 SQL（共 25 分）
1.（5 分）设有关系学生S(Sno, Sname, Dept)。用关系代数表达式写出查询。
2.（10 分）用 SQL 写出查询平均成绩高于85分的学生学号。
3.（10 分）一棵阶数为4的B+树。
二、关系数据库设计（共 25 分）
4.（15 分）设关系模式R(A, B, C, D, E)，函数依赖集F。
5.（10 分）将上题的R分解为满足BCNF的关系模式集合。
三、查询处理与事务（共 50 分）
6.（5 分）查询优化中为什么要尽早执行选择操作？
7.（5 分）事务的ACID特性中，原子性和持久性分别由什么机制保证？
8.（10 分）什么是两阶段锁协议？
9.（10 分）比较读已提交和可重复读两种隔离级别。
10.（10 分）简述ARIES恢复算法的三个阶段。
11.（10 分）在分布式事务中，两阶段提交协议的两个阶段分别做什么？"""

        chunks = chunk_exam_pdf("", [text])
        assert len(chunks) == 11, f"Expected 11 questions, got {len(chunks)}"

        for c in chunks:
            assert c.question_no is not None
            assert c.points is not None

        q4 = [c for c in chunks if c.question_no == 4][0]
        assert q4.points == 15.0

        total_points = sum(c.points for c in chunks)
        assert total_points == 100.0, f"Expected 100 total points, got {total_points}"

    def test_trailing_section_title_not_in_question_content(self):
        """大题标题（“三、……（共 50 分）”）不留在上一题的原文末尾。"""
        text = """4.（15 分）求候选码。
5.（10 分）分解为 BCNF。
三、查询处理与事务（共 50 分）
6.（5 分）为什么尽早执行选择？"""
        chunks = chunk_exam_pdf("", [text])
        q5 = [c for c in chunks if c.question_no == 5][0]
        assert q5.content.strip().endswith("分解为 BCNF。")
        assert "三、" not in q5.content
        assert "共 50 分" not in q5.content

    def test_no_questions_fallback(self):
        text = "This is just a regular text without any question markers."
        chunks = chunk_exam_pdf("", [text])
        assert len(chunks) >= 1


class TestJoinExamLines:
    def test_hard_wrap_inside_question_joined(self):
        from examradar.cleaner import join_exam_lines
        text = "1.（5 分）用关系代数表达式写\n出查询结果。\n2.（10 分）下一题。"
        joined = join_exam_lines(text)
        assert "写出查询结果。" in joined

    def test_question_header_never_glued_to_previous_question(self):
        from examradar.cleaner import join_exam_lines
        text = "1.（5 分）第一题没有句号结尾\n2.（10 分）第二题开始"
        joined = join_exam_lines(text)
        assert "第一题没有句号结尾" in joined
        assert joined.index("第一题没有句号结尾") < joined.index("2.（10 分）")
        lines = joined.split("\n")
        assert any(l.startswith("2.（10 分）") for l in lines)

    def test_section_header_starts_new_block(self):
        from examradar.cleaner import join_exam_lines
        text = "3.（10 分）画出一棵B+树\n二、关系数据库设计（共 25 分）\n4.（15 分）求候选码"
        joined = join_exam_lines(text)
        lines = joined.split("\n")
        assert "二、关系数据库设计（共 25 分）" in lines
        assert not any(l.startswith("3.（10 分）画出一棵B+树 二、") for l in lines)

    def test_cjk_latin_boundary_gets_space(self):
        from examradar.cleaner import join_exam_lines
        text = "1.（5 分）说明先写日志（WAL）原\n则为什么成立。"
        joined = join_exam_lines(text)
        assert "原则" in joined


class TestJoinIntraParagraphLines:
    def test_english_section_heading_stays_standalone(self):
        from examradar.cleaner import join_intra_paragraph_lines
        page = ("Two-Phase Commit: A Short Primer\n"
                "Supplementary reading, Fall 2026\n"
                "1. The Atomic Commitment Problem\n"
                "A distributed transaction updates data stored on several nodes.")
        joined = join_intra_paragraph_lines(page)
        assert "1. The Atomic Commitment Problem" in joined.split("\n")
        assert "Commitment Problem A distributed" not in joined

    def test_cjk_latin_join_inserts_space(self):
        from examradar.cleaner import join_intra_paragraph_lines
        page = "标题\n对没有\ncommit 也没有 abort 的事务撤销。"
        joined = join_intra_paragraph_lines(page)
        assert "对没有 commit" in joined

    def test_cjk_cjk_join_without_space(self):
        from examradar.cleaner import join_intra_paragraph_lines
        page = "标题\n用关系代数表达式写\n出学生姓名。"
        joined = join_intra_paragraph_lines(page)
        assert "写出学生姓名。" in joined

    def test_long_numbered_line_is_body_not_heading(self):
        from examradar.cleaner import join_intra_paragraph_lines
        numbered = "3. " + "word " * 25  # numbered but far longer than a heading
        page = "Title\nSome intro without ending punct\n" + numbered
        joined = join_intra_paragraph_lines(page)
        assert "Some intro without ending punct 3. word" in joined
