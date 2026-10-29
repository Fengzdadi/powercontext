"""Unit tests for syllabus parser."""
from examradar.syllabus import parse_syllabus, Topic


class TestParseSyllabus:
    def test_basic_parsing(self):
        text = """期末考试范围
1. 关系模型与关系代数
2. SQL 查询与视图
3. 索引：B+树与哈希索引"""
        topics = parse_syllabus(text)
        assert len(topics) == 3
        assert topics[0].topic_id == "t01"
        assert topics[0].name == "关系模型与关系代数"
        assert topics[1].topic_id == "t02"
        assert topics[2].topic_id == "t03"

    def test_keywords_extraction(self):
        text = "1. 函数依赖与范式（3NF、BCNF）"
        topics = parse_syllabus(text)
        assert len(topics) == 1
        assert topics[0].keywords == ["3NF", "BCNF"]

    def test_keywords_with_parentheses(self):
        text = "1. 分布式事务与两阶段提交（2PC）"
        topics = parse_syllabus(text)
        assert len(topics) == 1
        assert topics[0].keywords == ["2PC"]

    def test_title_line_skipped(self):
        text = """《数据库系统原理》2026 秋 期末考试范围
1. 关系模型与关系代数
2. SQL 查询与视图"""
        topics = parse_syllabus(text)
        assert len(topics) == 2

    def test_empty_input(self):
        assert parse_syllabus("") == []

    def test_search_query_includes_keywords(self):
        text = "1. 函数依赖与范式（3NF、BCNF）"
        topics = parse_syllabus(text)
        assert "3NF" in topics[0].search_query
        assert "BCNF" in topics[0].search_query

    def test_full_syllabus(self):
        text = """《数据库系统原理》2026 秋 期末考试范围
1. 关系模型与关系代数
2. SQL 查询与视图
3. 索引：B+树与哈希索引
4. 函数依赖与范式（3NF、BCNF）
5. 查询处理与优化
6. 事务的 ACID 特性
7. 并发控制：两阶段锁与死锁
8. 隔离级别与 MVCC
9. 故障恢复：WAL 与 ARIES
10. 分布式事务与两阶段提交（2PC）"""
        topics = parse_syllabus(text)
        assert len(topics) == 10
        assert topics[0].topic_id == "t01"
        assert topics[9].topic_id == "t10"
        assert topics[3].keywords == ["3NF", "BCNF"]
        assert topics[9].keywords == ["2PC"]
