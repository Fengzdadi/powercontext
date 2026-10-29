"""Parse exam scope (syllabus) text into a list of topics."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Topic:
    topic_id: str
    name: str
    keywords: list[str] = field(default_factory=list)

    @property
    def search_query(self) -> str:
        parts = [self.name]
        if self.keywords:
            parts.extend(self.keywords)
        return " ".join(parts)


_KW_PAREN_RE = re.compile(r"[（(]([^）)]+)[）)]")
_NUM_LINE_RE = re.compile(r"^\s*(\d+)\s*[.、．]\s*(.+)$")
_TITLE_RE = re.compile(r"考试范围|期末考试|期末考试范围| syllabus", re.IGNORECASE)


def parse_syllabus(text: str) -> list[Topic]:
    """Parse syllabus text into a list of Topic objects.

    Skips title lines (containing '考试范围' etc.) and blank lines.
    Each numbered line becomes a topic with a stable ID (t01, t02, ...).
    Parenthesized terms are extracted as keywords/aliases.
    """
    topics: list[Topic] = []
    idx = 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _TITLE_RE.search(line) and not _NUM_LINE_RE.match(line):
            continue
        m = _NUM_LINE_RE.match(line)
        if not m:
            continue
        idx += 1
        name = m.group(2).strip()
        keywords = _extract_keywords(name)
        topic_id = f"t{idx:02d}"
        topics.append(Topic(topic_id=topic_id, name=name, keywords=keywords))
    return topics


def _extract_keywords(name: str) -> list[str]:
    """Extract parenthesized terms as keywords."""
    keywords: list[str] = []
    for m in _KW_PAREN_RE.finditer(name):
        inner = m.group(1)
        for part in re.split(r"[、,，/]", inner):
            part = part.strip()
            if part:
                keywords.append(part)
    return keywords
