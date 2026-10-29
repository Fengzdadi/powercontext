"""LLM 客户端单元测试：thinking 剥离、JSON 容错解析、未配置降级。

qwen3.5 的 thinking 标签用字符串拼接构造，避免源文件里出现裸标签。
"""
import pytest

from examradar.llm import LLMClient, LLMError, parse_json_tolerant, strip_thinking

T_OPEN = "<" + "think>"
T_CLOSE = "</" + "think>"


class TestStripThinking:
    def test_strips_closed_think_block(self):
        text = T_OPEN + "我应该仔细分析…" + T_CLOSE + "最终答案"
        assert strip_thinking(text) == "最终答案"

    def test_strips_unclosed_think_block(self):
        text = "开头" + T_OPEN + "推理中被打断"
        assert strip_thinking(text) == "开头"

    def test_no_think_tags_untouched(self):
        assert strip_thinking("普通回答") == "普通回答"


class TestParseJsonTolerant:
    def test_plain_json(self):
        assert parse_json_tolerant('{"a": 1}') == {"a": 1}

    def test_markdown_fence(self):
        assert parse_json_tolerant('```json\n{"a": 1}\n```') == {"a": 1}

    def test_surrounding_text(self):
        assert parse_json_tolerant('好的，结果如下：{"a": 1} 希望有帮助') == {"a": 1}

    def test_nested_braces_in_strings(self):
        assert parse_json_tolerant('{"a": "包含}大括号", "b": 2}') == {
            "a": "包含}大括号", "b": 2}

    def test_truncated_json(self):
        out = parse_json_tolerant('{"a": "x", "b":')
        assert out is None

    def test_array(self):
        assert parse_json_tolerant('[1, 2, 3]') == [1, 2, 3]

    def test_think_then_json(self):
        text = T_OPEN + "推理" + T_CLOSE + '```json\n{"correct": true}\n```'
        assert parse_json_tolerant(strip_thinking(text)) == {"correct": True}

    def test_empty(self):
        assert parse_json_tolerant("") is None
        assert parse_json_tolerant("完全没有 JSON") is None


class TestUnconfigured:
    def test_not_configured(self):
        client = LLMClient()
        assert client.configured is False

    def test_chat_raises_when_unconfigured(self):
        with pytest.raises(LLMError):
            LLMClient().chat([{"role": "user", "content": "hi"}])

    def test_chat_json_raises_when_unconfigured(self):
        with pytest.raises(LLMError):
            LLMClient().chat_json([{"role": "user", "content": "hi"}])
