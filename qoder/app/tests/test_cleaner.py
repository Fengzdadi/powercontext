"""Unit tests for text cleaning (cleaner.py)."""
from examradar.cleaner import (
    clean_extracted_text, normalize_text, validate_cjk_chars, is_mostly_cjk,
    strip_footer_page_number,
)


class TestNormalizeText:
    def test_kangxi_radical_to_standard(self):
        kangxi_ri = "\u2f47"  # Kangxi radical for 日
        result = normalize_text(kangxi_ri)
        assert result == "日"
        assert ord(result) == 0x65E5

    def test_radical_supplement_to_standard(self):
        # ⻚ U+2EDA (CJK Radicals Supplement) -> 页
        assert normalize_text("\u2eda") == "页"

    def test_standard_cjk_unchanged(self):
        text = "数据库系统原理"
        assert normalize_text(text) == text

    def test_mixed_text(self):
        text = "⽇志记录与⽇志文件"  # Kangxi radicals mixed with standard chars
        result = normalize_text(text)
        assert "日志" in result
        assert "\u2f47" not in result

    def test_fullwidth_punctuation_preserved(self):
        # No full-text NFKC: full-width punctuation must stay full-width.
        text = "先写日志原则（WAL）：第7讲"
        assert normalize_text(text) == text

    def test_ascii_unchanged(self):
        text = "(5 分) B+树: 第7讲"
        assert normalize_text(text) == text


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

    def test_newline_between_chinese_preserved(self):
        # A newline between two CJK chars is a real line break (e.g. title
        # followed by body on the next line) and must NOT be removed.
        text = "日志记录与日志文件\n日志按时间顺序追加写入"
        result = clean_extracted_text(text)
        assert "日志文件\n日志按" in result

    def test_cjk_space_across_newline_not_joined(self):
        text = "标题有尾随空格 \n正文开头"
        result = clean_extracted_text(text)
        assert result == "标题有尾随空格\n正文开头"

    def test_mixed_chinese_english(self):
        text = "B+树 的 范围 查询"
        result = clean_extracted_text(text)
        assert "B+树" in result

    def test_fullwidth_punctuation_preserved(self):
        text = "1.（5 分）设有关系学生 S(Sno, Sname)。"
        result = clean_extracted_text(text)
        assert "（5 分）" in result
        assert "。" in result

    def test_crlf_normalized(self):
        text = "第一行\r\n第二行"
        result = clean_extracted_text(text)
        assert result == "第一行\n第二行"

    def test_ideographic_space_between_cjk_removed(self):
        text = "满分：100 分　　闭卷"
        result = clean_extracted_text(text)
        assert result == "满分：100 分闭卷"


class TestStripFooterPageNumber:
    def test_strips_trailing_digit_line(self):
        assert strip_footer_page_number("标题\n正文内容\n12") == "标题\n正文内容"

    def test_keeps_digit_in_body(self):
        assert strip_footer_page_number("第12页\n正文") == "第12页\n正文"

    def test_keeps_plain_text(self):
        assert strip_footer_page_number("只有正文") == "只有正文"

    def test_no_leading_blank_line_left(self):
        assert strip_footer_page_number("标题\n正文\n3") == "标题\n正文"


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
