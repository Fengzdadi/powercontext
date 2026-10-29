"""Unit tests for text cleaning (cleaner.py)."""
import unicodedata
from examradar.cleaner import (
    clean_extracted_text, normalize_text, validate_cjk_chars, is_mostly_cjk,
)


class TestNormalizeText:
    def test_kangxi_radical_to_standard(self):
        kangxi_ri = "\u2f47"  # Kangxi radical for 日
        result = normalize_text(kangxi_ri)
        assert result == "日"
        assert ord(result) == 0x65E5

    def test_standard_cjk_unchanged(self):
        text = "数据库系统原理"
        assert normalize_text(text) == text

    def test_mixed_text(self):
        text = "⽇志记录与⽇志文件"  # Kangxi radicals mixed with standard chars
        result = normalize_text(text)
        assert "日志" in result
        assert "\u2f47" not in result


class TestCleanExtractedText:
    def test_remove_spaces_between_chinese(self):
        text = "数据 库 系统 原理"
        result = clean_extracted_text(text)
        assert "数据库系统原理" in result

    def test_preserve_english_spaces(self):
        text = "hello world"
        result = clean_extracted_text(text)
        assert result == "hello world"

    def test_collapse_blank_lines(self):
        text = "line1\n\n\n\nline2"
        result = clean_extracted_text(text)
        assert result == "line1\n\nline2"

    def test_strip_whitespace(self):
        text = "  hello  \n  world  "
        result = clean_extracted_text(text)
        assert result.startswith("hello")
        assert result.endswith("world")

    def test_kangxi_normalization_in_context(self):
        text = "⽇志先写原则"
        result = clean_extracted_text(text)
        assert "日志先写原则" in result

    def test_mixed_chinese_english(self):
        text = "B+树 的 范围 查询"
        result = clean_extracted_text(text)
        assert "B+树" in result


class TestValidateCjkChars:
    def test_clean_text(self):
        suspicious = validate_cjk_chars("数据库系统")
        assert len(suspicious) == 0

    def test_kangxi_detected(self):
        suspicious = validate_cjk_chars("⽇志")
        assert len(suspicious) > 0

    def test_after_normalize_clean(self):
        text = normalize_text("⽇志")
        suspicious = validate_cjk_chars(text)
        assert len(suspicious) == 0


class TestIsMostlyCjk:
    def test_chinese_text(self):
        assert is_mostly_cjk("数据库系统原理") is True

    def test_english_text(self):
        assert is_mostly_cjk("hello world") is False

    def test_empty(self):
        assert is_mostly_cjk("") is False

    def test_mixed(self):
        assert is_mostly_cjk("B+树索引") is True
