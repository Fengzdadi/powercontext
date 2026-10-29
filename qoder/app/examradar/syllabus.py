"""Parse exam scope (syllabus) text into topics and their key terms (考点词)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# Chars that separate key terms inside a topic name, e.g.
# "索引：B+树与哈希索引" -> [索引, B+树, 哈希索引]
_TERM_SEP_RE = re.compile(r"[：:、；;]|[与和及]")

_PAREN_GROUP_RE = re.compile(r"([（(][^）)]*[）)])")
_ALIAS_SEP_RE = re.compile(r"[、,，/]")

# Stripped from the edges of a token; a token made only of these is dropped
# (mirrors the stopword behaviour of `SELECT TOKENIZE(x, 'ik')` without the
# DB round-trip, keeping matching deterministic and unit-testable).
_TOKEN_STOP_CHARS = "的之与和及或等"

_NUM_LINE_RE = re.compile(r"^\s*(\d+)\s*[.、．]\s*(.+)$")
_TITLE_RE = re.compile(r"考试范围|期末考试|期末考试范围| syllabus", re.IGNORECASE)


def normalize_for_match(text: str) -> str:
    """Casefold, convert full-width ASCII to half-width, drop all whitespace.

    Matching is done on this normalized form so that ＳＱＬ/SQL,
    （２ＰＣ）/2PC and hard line wraps inside a phrase all compare equal.
    """
    out = []
    for ch in text.casefold():
        cp = ord(ch)
        if 0xFF01 <= cp <= 0xFF5E:
            out.append(chr(cp - 0xFEE0))
        elif ch == "\u3000" or ch.isspace():
            continue
        else:
            out.append(ch)
    return "".join(out)


def tokenize_term(text: str) -> list[str]:
    """Split a term into content tokens for in-paragraph matching.

    Whitespace-separated words each become a token (leading/trailing
    stopwords stripped); a run with no whitespace stays one token so that
    e.g. "查询处理" only matches contiguously, never as loose co-occurrence
    of 查询 and 处理.
    """
    tokens: list[str] = []
    for word in text.split():
        word = word.strip(_TOKEN_STOP_CHARS)
        if word:
            tokens.append(normalize_for_match(word))
    return tokens


@dataclass
class Term:
    """One key term of a topic, with parenthesized aliases.

    "范式（3NF、BCNF）" -> text=范式, aliases=[3NF, BCNF]; the term counts
    as found when the text or any alias appears.
    """
    text: str
    aliases: list[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        if self.aliases:
            return f"{self.text}（{'、'.join(self.aliases)}）"
        return self.text

    def variants(self) -> list[str]:
        return [self.text] + list(self.aliases)


@dataclass
class Topic:
    topic_id: str
    name: str
    terms: list[Term] = field(default_factory=list)

    @property
    def keywords(self) -> list[str]:
        """All aliases, kept for backward-compatible display."""
        return [a for t in self.terms for a in t.aliases]

    @property
    def search_query(self) -> str:
        parts = [self.name]
        parts.extend(t.text for t in self.terms)
        parts.extend(a for t in self.terms for a in t.aliases)
        return " ".join(dict.fromkeys(parts))


def parse_terms(name: str) -> list[Term]:
    """Split a topic name into key terms.

    Splits on ：、与/和/及; a parenthesized group attaches as aliases to the
    term right before it. "函数依赖与范式（3NF、BCNF）" ->
    [函数依赖, 范式(aliases 3NF, BCNF)].
    """
    terms: list[Term] = []
    for atom in _PAREN_GROUP_RE.split(name):
        if not atom:
            continue
        if _PAREN_GROUP_RE.fullmatch(atom):
            aliases = [p.strip() for p in _ALIAS_SEP_RE.split(atom[1:-1]) if p.strip()]
            if terms and aliases:
                terms[-1].aliases.extend(aliases)
            continue
        for part in _TERM_SEP_RE.split(atom):
            part = part.strip()
            if part:
                terms.append(Term(text=part))
    return terms


def parse_syllabus(text: str) -> list[Topic]:
    """Parse syllabus text into a list of Topic objects.

    Skips title lines (containing '考试范围' etc.) and blank lines.
    Each numbered line becomes a topic with a stable ID (t01, t02, ...).
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
        topics.append(Topic(topic_id=f"t{idx:02d}", name=name,
                            terms=parse_terms(name)))
    return topics
