# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Choose query-relevant literal spans of recalled text under an exact rendered-byte budget.

Each source text is split into sentence units. Units are scored against the query with a
sentence-level BM25 over the candidate set, and each source is weighted by how strongly it
matches. A greedy packer then covers units by value per rendered byte: growing a span pays only
for the added text, while starting a span also pays for its citation and offsets, so related
evidence is delivered as few contiguous spans. Bytes left over extend spans word by word.

Selection depends only on the query, the texts, and the rendered cost of each span.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from powercontext.builtin.artifacts.search import analyze_text

_K1 = 1.2
_B = 0.3
_STEM_MATCH_WEIGHT = 0.75
_STOPWORD_WEIGHT = 0.1
# Share of a unit's value that does not depend on the query. Text near strong matches in a
# well-matching source stays preferable to unrelated text without outranking matching units.
_CONTEXT_VALUE = 0.15
_SOURCE_WEIGHT_EXPONENT = 2.0
_COVERAGE_WEIGHT = 0.3
_MAX_UNIT_CHARS = 360
_MIN_PIECE_CHARS = 80
_MAX_BRIDGE_UNITS = 8
_MAX_WINDOW_UNITS = 16
_SEED_UNITS = 6
_MAX_SEEDS = 3

_LATIN_END = re.compile(r"[.!?…]+[\"'”’)\]]*(?=\s)")  # noqa: RUF001
_CJK_END = re.compile(r"[。！？；]+[\"'”’」』)\]）]*")  # noqa: RUF001
_CLAUSE_END = re.compile(r"[,;:，；：、](?=\s)|[，；：、]")  # noqa: RUF001
_WHITESPACE = re.compile(r"\s+")
_NON_SPACE = re.compile(r"\S")
_WORD_BEFORE = re.compile(r"([A-Za-z][A-Za-z.]*)$")
_JSON_SPECIAL = re.compile(r"[\"\\\x00-\x1f]")
_ABBREVIATIONS = frozenset([
    "al",
    "approx",
    "ca",
    "cf",
    "co",
    "corp",
    "dept",
    "dr",
    "e.g",
    "eq",
    "eqs",
    "etc",
    "fig",
    "figs",
    "i.e",
    "inc",
    "jr",
    "ltd",
    "mr",
    "mrs",
    "ms",
    "no",
    "nos",
    "ph.d",
    "prof",
    "ref",
    "refs",
    "resp",
    "sp",
    "spp",
    "sr",
    "st",
    "u.k",
    "u.s",
    "viz",
    "vol",
    "vs",
])
_STOPWORDS = frozenset([
    "a",
    "about",
    "after",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "being",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "during",
    "each",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "more",
    "most",
    "no",
    "not",
    "of",
    "on",
    "or",
    "other",
    "our",
    "over",
    "should",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "under",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "within",
    "without",
    "would",
    "you",
    "your",
])
_SUFFIXES = (
    "ational",
    "ization",
    "ations",
    "ation",
    "ments",
    "ities",
    "ingly",
    "ment",
    "ness",
    "ings",
    "ions",
    "ives",
    "ated",
    "ates",
    "ity",
    "ing",
    "ion",
    "ive",
    "ate",
    "ies",
    "ied",
    "ers",
    "ly",
    "er",
    "ed",
    "es",
    "s",
)


@dataclass(frozen=True)
class EvidenceSource:
    """One candidate text and the rendered bytes its item costs besides content and offsets."""

    text: str
    item_bytes: int


@dataclass(frozen=True)
class EvidenceSpan:
    """A selected half-open character range of one source text."""

    source: int
    start: int
    end: int


@dataclass
class _Unit:
    source: int
    index: int
    start: int
    end: int
    lead: int
    trail: int
    sentence: int
    terms: Counter[str]
    stems: Counter[str]
    value: float = 0.0


@dataclass
class _Fragment:
    source: int
    first: int
    last: int
    start: int
    end: int


class _Source:
    def __init__(self, source: EvidenceSource) -> None:
        self.text = source.text
        self.item_bytes = source.item_bytes
        self.units: list[_Unit] = []
        self.weight = 0.0
        self.escaped: list[int] | None = None
        if not self.text.isascii() or _JSON_SPECIAL.search(self.text) is not None:
            escaped = [0]
            for character in self.text:
                escaped.append(escaped[-1] + _escaped_bytes(character))
            self.escaped = escaped

    def item_cost(self, start: int, end: int) -> int:
        content = end - start if self.escaped is None else self.escaped[end] - self.escaped[start]
        return self.item_bytes + len(str(start)) + len(str(end)) + content

    def unit_cost(self, unit: _Unit) -> int:
        return self.item_cost(unit.lead, unit.trail)


def select_evidence(query: str, sources: Sequence[EvidenceSource], budget: int) -> tuple[EvidenceSpan, ...]:
    """Select spans whose rendered items, joined by one separator byte each, fit in ``budget`` bytes.

    One item costs ``item_bytes`` plus its decimal offsets and its JSON-escaped UTF-8 content.
    Spans are grouped by source, strongest source first, and ordered by position within a source.
    """

    prepared = [_Source(source) for source in sources]
    units = _segment(prepared)
    if not units or budget <= 0:
        return ()
    _score(query, prepared, units)
    candidates = sorted(
        (unit for unit in units if unit.value > 0),
        key=lambda unit: (-unit.value / prepared[unit.source].unit_cost(unit), unit.source, unit.index),
    )
    # Ratio-greedy packing can spend the budget on cheap context and then miss a second strong unit.
    # Each plan therefore starts from a few of the most valuable units; the most valuable plan wins.
    strongest = sorted(candidates, key=lambda unit: (-unit.value, unit.source, unit.index))[:_SEED_UNITS]
    best: _Packer | None = None
    for size in range(_MAX_SEEDS + 1):
        for seeds in combinations(strongest, size):
            packer = _Packer(prepared, budget)
            if not packer.seed(seeds):
                continue
            packer.cover_units(candidates)
            if best is None or packer.value > best.value + 1e-9:
                best = packer
    if best is None:
        return ()
    if not best.fragments:
        best.cover_window(query, units)
    best.extend_words()
    fragments = sorted(
        best.fragments,
        key=lambda fragment: (-prepared[fragment.source].weight, fragment.source, fragment.start),
    )
    return tuple(EvidenceSpan(fragment.source, fragment.start, fragment.end) for fragment in fragments)


def _escaped_bytes(character: str) -> int:
    point = ord(character)
    if character in '"\\':
        return 2
    if point < 0x20:
        return 2 if character in "\b\f\n\r\t" else 6
    if point < 0x80:
        return 1
    if point < 0x800:
        return 2
    return 3 if point < 0x10000 else 4


def _segment(sources: list[_Source]) -> list[_Unit]:
    units: list[_Unit] = []
    sentence = 0
    for source_index, source in enumerate(sources):
        spans: list[tuple[int, int, int]] = []
        for start, end in _sentence_spans(source.text):
            spans.extend(
                (piece_start, piece_end, sentence) for piece_start, piece_end in _pieces(source.text, start, end)
            )
            sentence += 1
        for index, (start, end, sentence_id) in enumerate(spans):
            terms = Counter(analyze_text(source.text[start:end]).split())
            stems: Counter[str] = Counter()
            for term, count in terms.items():
                stems[_stem(term)] += count
            unit = _Unit(
                source=source_index,
                index=index,
                start=start,
                end=end,
                # Fragments include the surrounding whitespace, so they cover whole sentences however
                # an observer delimits them.
                lead=spans[index - 1][1] if index else 0,
                trail=spans[index + 1][0] if index + 1 < len(spans) else len(source.text),
                sentence=sentence_id,
                terms=terms,
                stems=stems,
            )
            source.units.append(unit)
            units.append(unit)
    return units


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    cuts = {len(text)}
    for match in _LATIN_END.finditer(text):
        following = _NON_SPACE.search(text, match.end())
        if following is None or text[following.start()].islower():
            continue
        if match.group().startswith("."):
            word = _WORD_BEFORE.search(text, max(0, match.start() - 16), match.start())
            if word is not None:
                token = word.group(1)
                if token.lower() in _ABBREVIATIONS or (len(token) == 1 and token.isupper()):
                    continue
        cuts.add(match.end())
    cuts.update(match.end() for match in _CJK_END.finditer(text))
    cuts.update(position for position, character in enumerate(text) if character == "\n")
    spans = []
    start = 0
    for cut in sorted(cuts):
        segment = text[start:cut]
        stripped = segment.strip()
        if stripped:
            offset = start + len(segment) - len(segment.lstrip())
            spans.append((offset, offset + len(stripped)))
        start = cut
    return spans


def _pieces(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split one long sentence at clause, then word, boundaries into pieces of bounded length."""

    pieces = []
    while end - start > _MAX_UNIT_CHARS:
        limit = start + _MAX_UNIT_CHARS
        cut = None
        for match in _CLAUSE_END.finditer(text, start + _MIN_PIECE_CHARS, limit):
            cut = match.end()
        if cut is None:
            for match in _WHITESPACE.finditer(text, start + _MIN_PIECE_CHARS, limit):
                cut = match.start()
        if cut is None:
            cut = limit
        piece_end = cut
        while piece_end > start and text[piece_end - 1].isspace():
            piece_end -= 1
        pieces.append((start, piece_end))
        following = _NON_SPACE.search(text, cut, end)
        if following is None:
            return pieces
        start = following.start()
    pieces.append((start, end))
    return pieces


def _stem(term: str) -> str:
    """Conflate common English inflections and derivations; other terms are returned unchanged."""

    if len(term) < 5 or not term.isascii() or not term.isalpha():
        return term
    stem = term
    for suffix in _SUFFIXES:
        if not term.endswith(suffix) or len(term) - len(suffix) < 3:
            continue
        stem = term[: -len(suffix)]
        if suffix in {"ies", "ied"}:
            stem += "y"
        elif suffix == "es" and not stem.endswith(("s", "x", "z", "ch", "sh")):
            stem = term[:-1]
        elif suffix == "s" and stem.endswith(("s", "u", "i")):
            stem = term
        break
    if len(stem) > 4 and stem.endswith("e"):
        stem = stem[:-1]
    if len(stem) > 4 and stem.endswith("ct"):
        stem = stem[:-1]
    return stem


def _score(query: str, sources: list[_Source], units: list[_Unit]) -> None:
    query_terms = list(dict.fromkeys(analyze_text(query).split()))
    weights = {term: (_STOPWORD_WEIGHT if term in _STOPWORDS else 1.0) for term in query_terms}
    if weights and max(weights.values()) < 1.0:
        weights = dict.fromkeys(weights, 1.0)
    query_stems = {term: _stem(term) for term in query_terms}

    frequency: Counter[str] = Counter()
    for unit in units:
        frequency.update(term for term in query_terms if unit.stems[query_stems[term]])
    total = len(units)
    term_weights = {
        term: weights[term] * math.log(1.0 + (total - frequency[term] + 0.5) / (frequency[term] + 0.5))
        for term in query_terms
    }
    scores = _sentence_scores(units, query_stems, term_weights)
    best = max(scores.values(), default=0.0)
    _weigh_sources(sources, query_stems, term_weights, scores)
    for unit in units:
        relevance = scores[unit.sentence] / best if best > 0 else 0.0
        unit.value = (
            sources[unit.source].weight
            * max(unit.terms.total(), 1)
            * (_CONTEXT_VALUE + (1.0 - _CONTEXT_VALUE) * relevance * relevance)
        )


def _sentence_scores(
    units: list[_Unit], query_stems: dict[str, str], term_weights: dict[str, float]
) -> dict[int, float]:
    """BM25 score of each sentence over all units, with stem-only matches discounted."""

    average_length = sum(unit.terms.total() for unit in units) / len(units) or 1.0
    scores: dict[int, float] = {}
    for unit in units:
        norm = 1.0 - _B + _B * unit.terms.total() / average_length
        score = 0.0
        for term, stem in query_stems.items():
            exact = unit.terms[term]
            matched = exact + _STEM_MATCH_WEIGHT * (unit.stems[stem] - exact)
            if matched > 0:
                score += term_weights[term] * matched * (_K1 + 1.0) / (matched + _K1 * norm)
        # A long sentence split into pieces is scored as a whole: its pieces share its relevance.
        scores[unit.sentence] = scores.get(unit.sentence, 0.0) + score
    return scores


def _weigh_sources(
    sources: list[_Source], query_stems: dict[str, str], term_weights: dict[str, float], scores: dict[int, float]
) -> None:
    """Weight each source by its strongest sentence and the query terms it covers; recall order breaks a no-match."""

    if max(scores.values(), default=0.0) <= 0:
        for rank, source in enumerate(sources):
            source.weight = 1.0 / (1.0 + rank)
        return
    for source in sources:
        coverage = sum(
            weight
            for term, weight in term_weights.items()
            if any(unit.stems[query_stems[term]] for unit in source.units)
        )
        strongest = max((scores[unit.sentence] for unit in source.units), default=0.0)
        source.weight = strongest + _COVERAGE_WEIGHT * coverage
    heaviest = max((source.weight for source in sources), default=0.0)
    if heaviest > 0:
        for source in sources:
            source.weight = (source.weight / heaviest) ** _SOURCE_WEIGHT_EXPONENT


class _Packer:
    """Greedy cover of units by value per rendered byte, with exact byte accounting."""

    def __init__(self, sources: list[_Source], budget: int) -> None:
        self.sources = sources
        self.remaining = budget
        self.value = 0.0
        self.fragments: list[_Fragment] = []
        self.covered: set[tuple[int, int]] = set()

    def seed(self, units: Sequence[_Unit]) -> bool:
        """Cover ``units`` first, as their own spans; report whether they fit the budget together."""

        for unit in units:
            if (unit.source, unit.index) in self.covered:
                continue
            fragment = next(
                (
                    fragment
                    for fragment in self.fragments
                    if fragment.source == unit.source and fragment.first - 1 <= unit.index <= fragment.last + 1
                ),
                None,
            )
            if fragment is None:
                cost = self._cost(unit.source, unit.index, unit.index) + (1 if self.fragments else 0)
            else:
                cost = self._growth_cost(fragment, min(fragment.first, unit.index), max(fragment.last, unit.index))
            if cost > self.remaining:
                return False
            self._cover(unit.source, unit.index, unit.index)
            self.remaining -= cost
        return True

    def cover_units(self, candidates: list[_Unit]) -> None:
        """Repeatedly take the best value per byte: a new span or the growth of an existing one.

        ``candidates`` is ordered by standalone value per byte, which only changes by the shared
        separator byte, so the best affordable new span is the first uncovered affordable one.
        Remaining bytes only shrink, so a skipped candidate never becomes affordable again.
        """

        position = 0
        while True:
            best = self._best_extension()
            while position < len(candidates):
                unit = candidates[position]
                cost = self._cost(unit.source, unit.index, unit.index) + (1 if self.fragments else 0)
                if (unit.source, unit.index) in self.covered or cost > self.remaining:
                    position += 1
                    continue
                if best is None or unit.value / cost > best[0]:
                    best = (unit.value / cost, cost, unit.source, unit.index, unit.index)
                break
            if best is None:
                return
            _ratio, cost, source, first, last = best
            self._cover(source, first, last)
            self.remaining -= cost

    def cover_window(self, query: str, units: list[_Unit]) -> None:
        """Deliver the best-matching window of one unit when no whole unit fits the budget."""

        terms = set(analyze_text(query).split())
        ranked = sorted(units, key=lambda unit: (-unit.value, unit.source, unit.index))
        for unit in ranked[:_MAX_WINDOW_UNITS]:
            source = self.sources[unit.source]
            starts = _word_starts(source.text, unit.start, unit.end)
            ends = _word_ends(source.text, unit.start, unit.end)
            best: tuple[int, int, int, int] | None = None
            last = -1
            for start in starts:
                # A later start never shortens the longest affordable window, so ``last`` only advances.
                while last + 1 < len(ends) and source.item_cost(start, ends[last + 1]) <= self.remaining:
                    last += 1
                if last < 0 or ends[last] <= start:
                    continue
                end = ends[last]
                matched = len(terms.intersection(analyze_text(source.text[start:end]).split()))
                if best is None or (matched, end - start) > (best[0], best[1]):
                    best = (matched, end - start, start, end)
            if best is not None:
                _matched, _length, start, end = best
                self.remaining -= source.item_cost(start, end)
                self.fragments.append(_Fragment(unit.source, unit.index, unit.index, start, end))
                self.covered.add((unit.source, unit.index))
                return

    def extend_words(self) -> None:
        """Spend the bytes left over on whole words next to the delivered spans."""

        open_edges = {(id(fragment), direction) for fragment in self.fragments for direction in (-1, 1)}
        while open_edges:
            best = None
            for fragment in self.fragments:
                for direction in (-1, 1):
                    if (id(fragment), direction) not in open_edges:
                        continue
                    extension = self._word_extension(fragment, direction)
                    if extension is None:
                        open_edges.discard((id(fragment), direction))
                    elif best is None or extension[0] > best[0]:
                        best = (*extension, fragment, direction)
            if best is None:
                return
            _gain, start, end, cost, fragment, direction = best
            fragment.start, fragment.end = start, end
            self.remaining -= cost
            open_edges.discard((id(fragment), direction))
            # The partly delivered neighbor is closed to the span on its other side, so spans stay disjoint.
            self.covered.add((fragment.source, fragment.first - 1 if direction < 0 else fragment.last + 1))

    def _word_extension(self, fragment: _Fragment, direction: int) -> tuple[float, int, int, int] | None:
        """Gain, bounds and byte cost of the most words that fit from the unit next to ``fragment``."""

        source = self.sources[fragment.source]
        neighbor = fragment.first - 1 if direction < 0 else fragment.last + 1
        if not 0 <= neighbor < len(source.units) or (fragment.source, neighbor) in self.covered:
            return None
        unit = source.units[neighbor]
        if direction > 0:
            boundaries = [(fragment.start, end) for end in _word_ends(source.text, fragment.end, unit.end)]
        else:
            starts = _word_starts(source.text, unit.start, fragment.start)
            boundaries = [(start, fragment.end) for start in reversed(starts)]
        current = source.item_cost(fragment.start, fragment.end)
        extension = None
        for start, end in boundaries:
            cost = source.item_cost(start, end) - current
            if cost > self.remaining:
                break
            extension = (start, end, cost)
        if extension is None:
            return None
        start, end, cost = extension
        added = fragment.start - start + end - fragment.end
        return unit.value * added / max(unit.end - unit.start, 1), start, end, cost

    def _best_extension(self) -> tuple[float, int, int, int, int] | None:
        best = None
        for fragment in self.fragments:
            units = self.sources[fragment.source].units
            for direction in (-1, 1):
                gain = 0.0
                for distance in range(1, _MAX_BRIDGE_UNITS + 1):
                    index = fragment.first - distance if direction < 0 else fragment.last + distance
                    if not 0 <= index < len(units) or (fragment.source, index) in self.covered:
                        break
                    gain += units[index].value
                    first, last = (index, fragment.last) if direction < 0 else (fragment.first, index)
                    cost = self._growth_cost(fragment, first, last)
                    if gain <= 0 or cost > self.remaining:
                        continue
                    ratio = gain / max(cost, 1)
                    if best is None or ratio > best[0]:
                        best = (ratio, cost, fragment.source, first, last)
        return best

    def _growth_cost(self, fragment: _Fragment, first: int, last: int) -> int:
        """Exact byte change of growing ``fragment`` to units ``first..last``, merging what it reaches."""

        before = self._cost(fragment.source, fragment.first, fragment.last)
        for other in self.fragments:
            if (
                other is not fragment
                and other.source == fragment.source
                and other.last >= first - 1
                and other.first <= last + 1
            ):
                before += self._cost(other.source, other.first, other.last) + 1
                first = min(first, other.first)
                last = max(last, other.last)
        return self._cost(fragment.source, first, last) - before

    def _cover(self, source_index: int, first: int, last: int) -> None:
        kept = []
        for fragment in self.fragments:
            if fragment.source == source_index and fragment.last >= first - 1 and fragment.first <= last + 1:
                first = min(first, fragment.first)
                last = max(last, fragment.last)
            else:
                kept.append(fragment)
        units = self.sources[source_index].units
        kept.append(_Fragment(source_index, first, last, units[first].lead, units[last].trail))
        self.fragments = kept
        for index in range(first, last + 1):
            if (source_index, index) not in self.covered:
                self.covered.add((source_index, index))
                self.value += units[index].value

    def _cost(self, source_index: int, first: int, last: int) -> int:
        source = self.sources[source_index]
        return source.item_cost(source.units[first].lead, source.units[last].trail)


def _word_ends(text: str, start: int, limit: int) -> list[int]:
    """Positions just after each word, or CJK character, ending in ``(start, limit]``."""

    ends = []
    for position in range(start + 1, limit + 1):
        if text[position - 1].isspace():
            continue
        if position == limit or text[position].isspace() or _is_cjk(text[position - 1]) or _is_cjk(text[position]):
            ends.append(position)
    return ends


def _word_starts(text: str, start: int, limit: int) -> list[int]:
    """Positions where a word, or CJK character, starts in ``[start, limit)``."""

    starts = []
    for position in range(start, limit):
        if text[position].isspace():
            continue
        if position == start or text[position - 1].isspace() or _is_cjk(text[position]) or _is_cjk(text[position - 1]):
            starts.append(position)
    return starts


def _is_cjk(character: str) -> bool:
    point = ord(character)
    return 0x3040 <= point <= 0x30FF or 0x3400 <= point <= 0x4DBF or 0x4E00 <= point <= 0x9FFF or point >= 0x20000


__all__ = ["EvidenceSource", "EvidenceSpan", "select_evidence"]
