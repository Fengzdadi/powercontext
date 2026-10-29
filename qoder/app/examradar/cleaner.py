"""Unicode text cleaning for Chinese PDF extraction."""
from __future__ import annotations

import re
import unicodedata


_KANGXI_RE = re.compile(r"[\u2f00-\u2fd5]")


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0xF900 <= cp <= 0xFAFF
    )


def normalize_text(text: str) -> str:
    """NFKC normalize to convert Kangxi radicals and compatibility chars to standard CJK."""
    return unicodedata.normalize("NFKC", text)


def clean_extracted_text(text: str) -> str:
    """Clean text extracted from PDF:
    - NFKC normalize (Kangxi radicals -> standard CJK)
    - Remove spaces between adjacent Chinese characters
    - Fix line breaks within paragraphs
    - Collapse multiple blank lines
    """
    text = normalize_text(text)

    lines = text.split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            cleaned_lines.append("")
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    text = re.sub(r"([\u4e00-\u9fff\u3400-\u4dbf])\s+([\u4e00-\u9fff\u3400-\u4dbf])", r"\1\2", text)
    for _ in range(3):
        text = re.sub(r"([\u4e00-\u9fff\u3400-\u4dbf])\s+([\u4e00-\u9fff\u3400-\u4dbf])", r"\1\2", text)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def validate_cjk_chars(text: str) -> list[str]:
    """Return a list of suspicious CJK characters that are not standard CJK
    even after NFKC normalization (e.g. remaining compatibility chars)."""
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
