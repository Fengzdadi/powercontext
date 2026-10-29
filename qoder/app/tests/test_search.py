"""Unit tests for search JSON construction and escaping."""
import json
from examradar.seekdb import build_search_json, _escape_search_text


class TestEscapeSearchText:
    def test_removes_quotes(self):
        assert "'" not in _escape_search_text("it's a test")
        assert '"' not in _escape_search_text('say "hello"')

    def test_removes_backslash(self):
        assert "\\" not in _escape_search_text("path\\to\\file")

    def test_preserves_normal_text(self):
        assert _escape_search_text("B+树插入") == "B+树插入"

    def test_strips_whitespace(self):
        assert _escape_search_text("  hello  ") == "hello"


class TestBuildSearchJson:
    def test_basic_structure(self):
        result = build_search_json(
            query_text="事务隔离级别",
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["notes", "slides"],
            top_k=10,
        )
        assert "query" in result
        assert "knn" in result
        assert "rank" in result
        assert result["rank"] == {"rrf": {}}
        assert result["size"] == 10

    def test_filters_in_both_branches(self):
        result = build_search_json(
            query_text="test",
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["notes"],
            top_k=5,
        )
        query_filters = result["query"]["bool"]["filter"]
        knn_filters = result["knn"]["filter"]
        assert len(query_filters) == 2
        assert len(knn_filters) == 2
        assert query_filters[0] == {"term": {"course_id": "db101"}}
        assert query_filters[1] == {"terms": {"doc_kind": ["notes"]}}

    def test_source_fields(self):
        result = build_search_json(
            query_text="test",
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["notes"],
        )
        source = result["_source"]
        assert "id" in source
        assert "content" in source
        assert "_keyword_score" in source
        assert "_semantic_score" in source
        assert "question_no" in source
        assert "points" in source

    def test_query_text_escaped(self):
        result = build_search_json(
            query_text='say "hello" to it\'s',
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["notes"],
        )
        match = result["query"]["bool"]["must"][0]["multi_match"]
        assert '"' not in match["query"]
        assert "'" not in match["query"]

    def test_multi_match_covers_content_and_heading(self):
        result = build_search_json(
            query_text="先写日志原则",
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["slides"],
        )
        match = result["query"]["bool"]["must"][0]["multi_match"]
        assert match["query"] == "先写日志原则"
        assert "content" in match["fields"]
        assert "heading" in match["fields"]

    def test_serializable(self):
        result = build_search_json(
            query_text="B+树",
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["notes", "slides", "paper"],
        )
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["query"]["bool"]["must"][0]["multi_match"]["query"] == "B+树"

    def test_knn_k_value(self):
        result = build_search_json(
            query_text="test",
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["notes"],
            top_k=10,
        )
        assert result["knn"]["k"] >= 20

    def test_include_exam(self):
        result = build_search_json(
            query_text="函数依赖",
            query_vector=[0.1] * 512,
            course_id="db101",
            doc_kinds=["notes", "slides", "paper", "exam"],
        )
        filters = result["query"]["bool"]["filter"]
        doc_kind_filter = [f for f in filters if "terms" in f][0]
        assert "exam" in doc_kind_filter["terms"]["doc_kind"]
