"""Unicode text cleaning for Chinese PDF extraction."""
from __future__ import annotations

import re
import unicodedata


# Kangxi radicals and CJK Radicals Supplement: map each char to its
# standard CJK unified ideograph. Avoid full-text NFKC, which would also
# convert full-width punctuation to half-width.
_RADICAL_RE = re.compile(r"[\u2e80-\u2eff\u2f00-\u2fdf]")

# CJK Radicals Supplement chars with no NFKC decomposition, mapped via the
# "x" equivalences in the Unicode UCD NamesList.txt.
_RADICAL_MAP = {
    0x2E81: 0x20086, 0x2E82: 0x4E5B, 0x2E83: 0x4E5A, 0x2E84: 0x4E59,
    0x2E85: 0x4EBB, 0x2E86: 0x5182, 0x2E87: 0x20628, 0x2E88: 0x2008A,
    0x2E89: 0x5202, 0x2E8A: 0x535C, 0x2E8B: 0x353E, 0x2E8C: 0x5C0F,
    0x2E8D: 0x2D544, 0x2E8E: 0x5140, 0x2E8F: 0x5C23, 0x2E90: 0x5C22,
    0x2E91: 0x21BC2, 0x2E92: 0x5DF3, 0x2E93: 0x5E7A, 0x2E94: 0x5F51,
    0x2E95: 0x2B739, 0x2E96: 0x5FC4, 0x2E97: 0x5FC3, 0x2E98: 0x624C,
    0x2E99: 0x6535, 0x2E9B: 0x65E1, 0x2E9C: 0x65E5, 0x2E9D: 0x6708,
    0x2E9E: 0x6B7A, 0x2EA0: 0x6C11, 0x2EA1: 0x6C35, 0x2EA2: 0x6C3A,
    0x2EA3: 0x706C, 0x2EA4: 0x722B, 0x2EA5: 0x722B, 0x2EA6: 0x4E2C,
    0x2EA7: 0x20092, 0x2EA8: 0x72AD, 0x2EA9: 0x248E9, 0x2EAA: 0x24D14,
    0x2EAB: 0x7F52, 0x2EAC: 0x793A, 0x2EAD: 0x793B, 0x2EAE: 0x25AD7,
    0x2EAF: 0x7CF9, 0x2EB0: 0x7E9F, 0x2EB1: 0x7F53, 0x2EB2: 0x26270,
    0x2EB3: 0x7F51, 0x2EB4: 0x7F51, 0x2EB5: 0x2626B, 0x2EB6: 0x7F8A,
    0x2EB7: 0x2634C, 0x2EB8: 0x2634B, 0x2EB9: 0x8002, 0x2EBA: 0x8080,
    0x2EBB: 0x807F, 0x2EBC: 0x8089, 0x2EBD: 0x26951, 0x2EBE: 0x8279,
    0x2EBF: 0x8279, 0x2EC0: 0x8279, 0x2EC1: 0x864E, 0x2EC2: 0x8864,
    0x2EC3: 0x8980, 0x2EC4: 0x897F, 0x2EC5: 0x89C1, 0x2EC6: 0x89D2,
    0x2EC7: 0x278B2, 0x2EC8: 0x8BA0, 0x2EC9: 0x8D1D, 0x2ECA: 0x27FB7,
    0x2ECB: 0x8F66, 0x2ECC: 0x8FB6, 0x2ECD: 0x8FB6, 0x2ECE: 0x8FB6,
    0x2ECF: 0x9091, 0x2ED0: 0x9485, 0x2ED1: 0x9577, 0x2ED2: 0x9578,
    0x2ED3: 0x957F, 0x2ED4: 0x95E8, 0x2ED5: 0x28E0F, 0x2ED6: 0x961D,
    0x2ED7: 0x96E8, 0x2ED8: 0x9752, 0x2ED9: 0x97E6, 0x2EDA: 0x9875,
    0x2EDB: 0x98CE, 0x2EDC: 0x98DE, 0x2EDD: 0x98DF, 0x2EDE: 0x2967F,
    0x2EDF: 0x98E0, 0x2EE0: 0x9963, 0x2EE1: 0x29810, 0x2EE2: 0x9A6C,
    0x2EE3: 0x9AA8, 0x2EE4: 0x9B3C, 0x2EE5: 0x9C7C, 0x2EE6: 0x9E1F,
    0x2EE7: 0x5364, 0x2EE8: 0x9EA6, 0x2EE9: 0x9EC4, 0x2EEA: 0x9EFE,
    0x2EEB: 0x6589, 0x2EEC: 0x9F50, 0x2EED: 0x6B6F, 0x2EEE: 0x9F7F,
    0x2EEF: 0x9F8D, 0x2EF0: 0x9F99, 0x2EF1: 0x9F9C, 0x2EF2: 0x4E80,
}

# Horizontal whitespace only (no newlines) — a newline between two CJK chars
# is a real line break and must be preserved.
_HSPACE = r"[ \t\u3000]"

_CJK = r"\u4e00-\u9fff\u3400-\u4dbf"

_CJK_SPACE_RE = re.compile(f"([{_CJK}]){_HSPACE}+([{_CJK}])")


def _map_radical_char(ch: str) -> str:
    cur = ch
    for _ in range(3):
        if not _RADICAL_RE.fullmatch(cur):
            break
        if ord(cur) in _RADICAL_MAP:
            cur = chr(_RADICAL_MAP[ord(cur)])
            continue
        mapped = unicodedata.normalize("NFKC", cur)
        if mapped == cur:
            break
        cur = mapped
    return cur


def normalize_text(text: str) -> str:
    """Map Kangxi radicals (U+2F00–U+2FDF) and CJK Radicals Supplement
    (U+2E80–U+2EFF) chars to standard CJK. Everything else is unchanged."""
    if not _RADICAL_RE.search(text):
        return text
    return "".join(_map_radical_char(ch) for ch in text)


def clean_extracted_text(text: str) -> str:
    """Clean text extracted from PDF:
    - Map radical-region chars to standard CJK
    - Normalize line endings
    - Remove spaces between adjacent Chinese characters on the same line
    - Collapse multiple blank lines
    """
    text = normalize_text(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    while True:
        new_text = _CJK_SPACE_RE.sub(r"\1\2", text)
        if new_text == text:
            break
        text = new_text

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_footer_page_number(text: str) -> str:
    """Drop a trailing line that is only a page number (e.g. '12')."""
    lines = text.rstrip().split("\n")
    if lines and re.fullmatch(r"\d{1,4}", lines[-1].strip()):
        lines = lines[:-1]
    return "\n".join(lines).rstrip()


def validate_cjk_chars(text: str) -> list[str]:
    """Return a list of suspicious CJK characters that are not standard CJK
    (Kangxi radicals / CJK radical supplement)."""
    suspicious = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if 0x2F00 <= cp <= 0x2FD5:
            suspicious.append(f"pos={i} char={ch} U+{cp:04X} (Kangxi radical)")
        elif 0x2E80 <= cp <= 0x2EFF:
            suspicious.append(f"pos={i} char={ch} U+{cp:04X} (CJK radical supplement)")
    return suspicious


def is_mostly_cjk(text: str) -> bool:
    """Check if the text contains a reasonable proportion of CJK characters."""
    if not text:
        return False
    cjk_count = sum(1 for ch in text if _is_cjk(ch))
    return cjk_count > len(text) * 0.1


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0xF900 <= cp <= 0xFAFF
    )


_SENTENCE_END_RE = re.compile(r"[。！？；：…\.\!\?\;]$")

# Exam-paper line boundaries: a new question ("3.（10 分）…") or a section
# header ("二、关系数据库设计（共 25 分）") always starts a new block.
_EXAM_QUESTION_START_RE = re.compile(r"\d+\s*[.、．]\s*[（(]\s*\d+(?:\.\d+)?\s*分\s*[）)]")
_EXAM_SECTION_START_RE = re.compile(r"^[一二三四五六七八九十]+\s*[、.．]")


def join_exam_lines(text: str) -> str:
    """Join hard line breaks inside an exam paper.

    Unlike a slide page, an exam page has no single title line, so nothing
    is special-cased as a title; instead question headers ("N.（M 分）") and
    section headers ("二、…") always start a new block and are never glued
    to the previous question's text.
    """
    result: list[str] = []
    buf = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if buf:
                result.append(buf)
                buf = ""
            result.append("")
            continue
        starts_block = (_EXAM_QUESTION_START_RE.match(stripped)
                        or _EXAM_SECTION_START_RE.match(stripped))
        if buf and starts_block:
            result.append(buf)
            buf = ""
        buf = stripped if not buf else _join_pair(buf, stripped)
    if buf:
        result.append(buf)
    return "\n".join(result)


# Short numbered lines like "1. The Atomic Commitment Problem" are section
# headings inside a paper page, not body sentences — they must not be glued
# to neighbouring text when joining hard-wrapped lines.
_HEADING_LINE_RE = re.compile(r"^\d+(\.\d+)*[.、]?\s+\S.{0,80}$")


def _join_pair(buf: str, line: str) -> str:
    """Join two hard-wrapped lines: no space between CJK chars, one space
    whenever either side of the boundary is latin/digit."""
    if buf and line and _is_cjk(buf[-1]) and _is_cjk(line[0]):
        return buf + line
    return buf + " " + line


def join_intra_paragraph_lines(page_text: str) -> str:
    """Join hard line breaks within a paragraph.

    The first line of a page is the title and stays independent. For the
    remaining lines, if a line does NOT end with a sentence-ending
    punctuation mark, it is joined with the next line (no space between CJK
    chars, one space at CJK/latin boundaries). Blank lines are paragraph
    boundaries and preserved, and heading-like lines (short numbered lines)
    are kept standalone instead of being glued into the body.
    """
    lines = page_text.split("\n")
    if len(lines) <= 1:
        return page_text

    title = lines[0]
    body_lines = lines[1:]

    result: list[str] = [title]
    buf = ""
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            if buf:
                result.append(buf)
                buf = ""
            result.append("")
            continue
        if _HEADING_LINE_RE.match(stripped):
            if buf:
                result.append(buf)
                buf = ""
            result.append(stripped)
            continue
        if not buf:
            buf = stripped
        else:
            buf = _join_pair(buf, stripped)
        if _SENTENCE_END_RE.search(stripped):
            result.append(buf)
            buf = ""
    if buf:
        result.append(buf)

    return "\n".join(result)
