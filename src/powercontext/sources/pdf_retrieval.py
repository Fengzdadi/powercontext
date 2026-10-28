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

"""Offline query analysis and page ranking for questions about financial reports.

Questions are expanded with report vocabulary (a question about capex must find the
"purchases of property, plant and equipment" line), matched to the document they name,
and the primary financial statements a metric is computed from are recognized from
page structure. Nothing here depends on a particular document or question.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Flag, auto
from functools import lru_cache
from itertools import pairwise

_TOKEN = re.compile(r"[a-z]+|\d+")
_WORD = re.compile(r"[a-z0-9&]+")


class Statement(Flag):
    """Primary financial statements recognized from page structure."""

    NONE = 0
    INCOME = auto()
    COMPREHENSIVE = auto()
    BALANCE = auto()
    CASH_FLOW = auto()
    EQUITY = auto()


_STATEMENT_KINDS = (
    Statement.INCOME,
    Statement.COMPREHENSIVE,
    Statement.BALANCE,
    Statement.CASH_FLOW,
    Statement.EQUITY,
)

_STOPWORD_TEXT = """
    a about above according account after again against all also am an and any approach approximate approximately
    are as assume assuming at based basing be been before being below between both but by can could did do does
    doing done during each either else etc ever every few following for from further give given had has have
    having he her here hers herself him his how however i if in into is it its itself just less like main mainly
    many may me might more most much must my need needed no nor not now of off on once one only or other our ours
    out over own per please provide provided rather really respect same say says she should so some such than that
    the their theirs them then there these they this those through thus to too under until up upon us use used
    using utilize utilizing very via was we were what whatever when where whether which while who whom whose why
    will with within without would yes yet you your yours
    answer answers question questions respond response round rounded decimal places place unit units percent
    percents percentage calculate calculated calculating calculation compute computed computing define defined
    definition formula metric metrics ratio report reported reporting state stated explain explained
    detail details information info shown show outline outlined clearly plainly primarily mostly primary
    perspective standpoint analyst analysts banker bankers judgment judgments judgement judgements conclusion
    conclusions drawing draw relying rely abilities ability best help resource resources reasonable reasonably
    exact possible approximation consider considering taking take regarding regard relevant useful meaningful
    conventional company companies business usd million millions billion billions thousand thousands fy fiscal
    year years period periods quarter quarters q1 q2 q3 q4 roughly overall total full number amount value values
    data figure figures term terms financial financials statement statements
"""
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())

# Persona and formatting instructions carry no evidence terms of their own.
_BOILERPLATE = re.compile(
    r"(?:equity research|public equities|investment banking|investment|financial|equity) (?:analyst|banker)s?"
    r"|lost (?:the )?internet connection|financial metric providers|access to financial metric"
    r"|round(?:ed)? (?:your )?(?:answer )?to (?:\w+ )?decimal places?"
    r"|in (?:units of )?(?:usd )?(?:millions|billions|thousands|percents?)"
)

_YEAR = re.compile(r"(?<![a-z0-9])(?:fy|fiscal year |fiscal )?'?((?:19|20)\d{2}|\d{2})(?![0-9])")
_QUARTER = re.compile(r"(?<![a-z0-9])q([1-4])(?![0-9])|(?<![a-z0-9])(first|second|third|fourth) (?:fiscal )?quarter")
_ORDINAL_QUARTERS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_DOCUMENT_YEAR = re.compile(r"^((?:19|20)\d{2})(?:q([1-4]))?$")

_STATEMENT_MENTIONS = (
    (re.compile(r"cash ?flows? statements?|statements? of (?:consolidated )?cash ?flows?"), Statement.CASH_FLOW),
    (
        re.compile(
            r"income statements?|statements? of (?:consolidated )?(?:income|operations|earnings)"
            r"|\bp ?& ?l\b|profit (?:and|&) loss"
        ),
        Statement.INCOME,
    ),
    (
        re.compile(r"balance sheets?|statements? of (?:consolidated )?financial (?:position|condition)"),
        Statement.BALANCE,
    ),
    (re.compile(r"statements? of (?:changes in )?(?:(?:share|stock)holders'? )?equity"), Statement.EQUITY),
    (re.compile(r"statements? of comprehensive"), Statement.COMPREHENSIVE),
)


@dataclass(frozen=True)
class _Concept:
    pattern: re.Pattern[str]
    phrases: tuple[str, ...]
    statements: Statement = Statement.NONE


def _concept(pattern: str, phrases: str, statements: Statement = Statement.NONE) -> _Concept:
    return _Concept(re.compile(pattern), tuple(phrase.strip() for phrase in phrases.split(",")), statements)


_INCOME = Statement.INCOME
_BALANCE = Statement.BALANCE
_CASH = Statement.CASH_FLOW

# Report vocabulary for concepts that questions name differently from the filings.
_CONCEPTS = (
    _concept(
        r"\bcapex\b|capital expenditure|capital spending|purchases? of (?:property|pp ?& ?e|fixed assets)",
        "capital expenditures, capital spending, purchases of property plant and equipment, "
        "additions to property plant and equipment, payments for property and equipment",
        _CASH,
    ),
    _concept(
        r"\bd ?& ?a\b|depreciation|amortization", "depreciation and amortization, depreciation, amortization", _CASH
    ),
    _concept(
        r"\bebitda\b|\bebit\b", "operating income, operating profit, depreciation and amortization", _INCOME | _CASH
    ),
    _concept(
        r"free cash ?flow|\bfcf\b",
        "net cash provided by operating activities, capital expenditures, capital spending",
        _CASH,
    ),
    _concept(
        r"cash (?:flows? )?from operations|operating cash ?flows?|cash flows? from operating|operating activities",
        "net cash provided by operating activities, operating activities",
        _CASH,
    ),
    _concept(
        r"\bcash ?flows?\b|investing activities|financing activities",
        "operating activities, investing activities, financing activities, net cash provided by",
        _CASH,
    ),
    _concept(
        r"\bcogs\b|cost of (?:goods|sales|revenues?|products)",
        "cost of sales, cost of goods sold, cost of revenue, cost of products sold",
        _INCOME,
    ),
    _concept(r"gross (?:margin|profit)", "gross profit, gross margin, cost of sales", _INCOME),
    _concept(
        r"operating (?:margin|income|profit)|income from operations",
        "operating income, operating profit, income from operations, operating margin",
        _INCOME,
    ),
    _concept(r"\brevenues?\b|\bsales\b|top ?line", "net revenue, net sales, total revenues, revenues", _INCOME),
    _concept(
        r"net (?:income|earnings|profit|loss)|bottom ?line|profit margin",
        "net income, net earnings, net income attributable",
        _INCOME,
    ),
    _concept(r"\beps\b|earnings per share", "earnings per share, net income per share, diluted", _INCOME),
    _concept(
        r"effective tax|tax rate|income tax",
        "effective tax rate, provision for income taxes, income tax expense, income before income taxes",
        _INCOME,
    ),
    _concept(r"interest (?:coverage|expense)", "interest expense, operating income", _INCOME),
    _concept(r"inventor(?:y|ies)|\bdio\b", "inventories, inventory", _BALANCE),
    _concept(r"inventory turnover|days inventory|\bdio\b", "cost of sales, inventories", _INCOME | _BALANCE),
    _concept(r"days payables?|\bdpo\b|accounts payable|payables", "accounts payable, cost of sales", _BALANCE),
    _concept(
        r"days sales outstanding|\bdso\b|receivables?|\bnet ar\b",
        "accounts receivable, receivables, trade receivables",
        _BALANCE,
    ),
    _concept(
        r"cash conversion cycle|\bccc\b",
        "inventories, accounts receivable, accounts payable, cost of sales",
        _BALANCE | _INCOME,
    ),
    _concept(r"\broa\b|return on (?:total )?assets", "net income, total assets", _INCOME | _BALANCE),
    _concept(
        r"\broe\b|return on (?:shareholders |stockholders )?equity",
        "net income, total equity, shareholders equity",
        _INCOME | _BALANCE,
    ),
    _concept(r"asset turnover", "total assets, property plant and equipment net, net revenue", _INCOME | _BALANCE),
    _concept(
        r"pp ?& ?e|\bppne\b|property,? plant|fixed assets?",
        "property plant and equipment net, property and equipment",
        _BALANCE,
    ),
    _concept(r"total assets", "total assets", _BALANCE),
    _concept(
        r"working capital|current ratio|current assets|current liabilities",
        "total current assets, total current liabilities",
        _BALANCE,
    ),
    _concept(
        r"quick ratio|acid test|liquidity",
        "cash and cash equivalents, short term investments, accounts receivable, total current liabilities, liquidity",
        _BALANCE,
    ),
    _concept(
        r"\bdebts?\b|borrowings?|leverage|indebtedness",
        "long term debt, short term borrowings, debt obligations, notes payable, total debt",
        _BALANCE,
    ),
    _concept(r"dividends?", "dividends paid, cash dividends, dividends declared", _CASH),
    _concept(r"payout ratio|retention ratio", "dividends paid, net income", _CASH | _INCOME),
    _concept(
        r"repurchas|buy ?backs?", "repurchases of common stock, share repurchases, treasury stock, repurchase program"
    ),
    _concept(r"restructuring", "restructuring, restructuring charges, impairment charges, severance", _INCOME),
    _concept(
        r"legal|litigation|lawsuits?|court|proceedings",
        "legal proceedings, litigation, lawsuits, claims, contingencies, settlement, class action, complaint",
    ),
    _concept(
        r"geograph|\bregions?\b|countries|international|\bwhere\b",
        "segments, geographic, regions, international, north america, europe, latin america, asia pacific, africa, "
        "middle east",
    ),
    _concept(
        r"registered|national securities exchange|trading symbol|listed on",
        "securities registered pursuant to section 12 b of the act, title of each class, trading symbol, "
        "name of each exchange on which registered, notes due, stock exchange",
    ),
    _concept(r"products?|services?|offerings?|brands?|portfolio", "products, services, segments, brands, offerings"),
    _concept(r"customers?|clients?", "customers, customer, significant customer, major customers"),
    _concept(
        r"concentration|(?:major|significant|largest|key) customers?",
        "customer accounted for, customers accounted for, accounted for, concentration, major customers",
    ),
    _concept(
        r"liquidat|bankrupt|book value",
        "book value per share, tangible book value per share, tbvps, total stockholders equity, shares outstanding",
        _BALANCE,
    ),
    _concept(
        r"acquisitions?|acquired|acquire|\bm ?& ?a\b|mergers?",
        "acquisition, acquired, business combinations, purchase price, divestitures, organic",
    ),
    _concept(r"industry|sector|line of business", "industry, business, segments"),
    _concept(
        r"capital[- ]intensive|capital intensity",
        "capital expenditures, property plant and equipment, depreciation, total assets, net sales",
        _BALANCE | _CASH | _INCOME,
    ),
    _concept(r"cyclical", "cyclical, cyclicality, economic conditions, demand"),
    _concept(r"guidance|outlook|forecast", "guidance, outlook, expects, forecast"),
    _concept(r"segments?", "segment, business segment, segment results, reportable segments, operating segments"),
    _concept(r"\bgrowth\b|\bgrow\b|growing", "growth, increase, increased"),
    _concept(
        r"\bdr(?:ove|iven|ivers?)\b|reasons?|\bwhy\b|due to", "primarily due to, driven by, reflecting, offset by"
    ),
)

# Phrases that open a primary statement and the line items that fill it.
_STATEMENT_TITLES = {
    Statement.INCOME: re.compile(
        r"statements? of (?:consolidated )?(?:net )?(?:income|operations|earnings|(?:profit|income) (?:and|or) loss)"
        r"(?! and comprehensive)|income statements?"
    ),
    Statement.COMPREHENSIVE: re.compile(r"statements? of (?:consolidated )?comprehensive (?:income|loss|earnings)"),
    Statement.BALANCE: re.compile(
        r"balance sheets?|statements? of (?:consolidated )?financial (?:position|condition)|statements? of condition"
    ),
    Statement.CASH_FLOW: re.compile(r"statements? of (?:consolidated )?cash flows?"),
    Statement.EQUITY: re.compile(
        r"statements? of (?:consolidated )?(?:changes in )?(?:(?:share|stock)holders|shareowners|share ?owners|"
        r"shareholders|stockholders)['\u2019]? (?:equity|deficit)|statements? of (?:changes in )?equity"
    ),
}
_STATEMENT_LINES = {
    Statement.INCOME: re.compile(
        r"net (?:revenues?|sales)|total (?:net )?revenues?|cost of (?:sales|goods sold|revenues?|products sold)"
        r"|gross (?:profit|margin)|operating (?:income|profit|expenses)|income before (?:income )?taxes"
        r"|(?:provision for|benefit from) income taxes|net (?:income|earnings|loss)|per (?:common )?share"
    ),
    Statement.COMPREHENSIVE: re.compile(
        r"other comprehensive|comprehensive income|foreign currency translation|net of tax|net income"
    ),
    Statement.BALANCE: re.compile(
        r"total assets|total current assets|total liabilities|total current liabilities|accounts payable"
        r"|retained earnings|cash and cash equivalents|inventories|goodwill|property,? plant and equipment"
        r"|total (?:shareholders|stockholders|share ?owners)['\u2019]? equity|total equity"
    ),
    Statement.CASH_FLOW: re.compile(
        r"operating activities|investing activities|financing activities|depreciation|net cash"
        r"|capital (?:expenditures|spending)|purchases? of property|dividends paid|end of (?:the )?(?:year|period)"
    ),
    Statement.EQUITY: re.compile(
        r"retained earnings|treasury stock|dividends declared|balance,? (?:at |beginning|end)|common stock"
        r"|accumulated other comprehensive|stock-based compensation|share-based compensation"
    ),
}
_STATEMENT_HEAD_CHARACTERS = 400
_CONSOLIDATED = re.compile(r"\bconsolidated\b")


@dataclass(frozen=True)
class DocumentCue:
    """Company and period parsed from a document identity such as ``ACME_2022_10K``."""

    document_id: str
    company: str
    company_words: tuple[str, ...]
    year: int | None
    quarter: int | None


@dataclass
class PageQuery:
    """Weighted evidence terms and structural hints derived from one question."""

    question: str
    terms: dict[str, float]
    phrases: dict[tuple[str, ...], float]
    statements: Statement
    explicit_statements: Statement
    years: frozenset[int]
    quarter: int | None
    names: tuple[str, ...]
    search_texts: tuple[str, ...]
    expansion_texts: tuple[str, ...]


@dataclass
class RankedPage:
    """One candidate page and the evidence that ordered it."""

    index: int
    document_id: str
    score: float = 0.0
    statement: Statement = Statement.NONE
    consolidated: bool = False
    tokens: list[str] = field(default_factory=list, repr=False)


def tokenize(text: str) -> list[str]:
    """Split compatibility-normalized text into lowercase letter and digit runs."""

    return _TOKEN.findall(unicodedata.normalize("NFKC", text).casefold())


@lru_cache(maxsize=65536)
def stem(token: str) -> str:
    """Fold common English plurals so singular and plural forms match."""

    if len(token) <= 3 or token.isdigit():
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith(("sses", "xes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def analyze_question(question: str) -> PageQuery:
    """Derive weighted terms, report-vocabulary expansions and statement hints."""

    normalized = unicodedata.normalize("NFKC", question).casefold()
    words = " ".join(_WORD.findall(normalized.replace("\u2019", "'")))
    content = _BOILERPLATE.sub(" ", words)
    explicit = Statement.NONE
    for pattern, statement in _STATEMENT_MENTIONS:
        if pattern.search(words):
            explicit |= statement
    implied = Statement.NONE
    expansions: dict[str, None] = {}
    for concept in _CONCEPTS:
        if concept.pattern.search(content):
            implied |= concept.statements
            expansions.update(dict.fromkeys(concept.phrases))
    tokens = tokenize(content)
    terms, phrases = _weighted_terms(tokens, expansions)
    search_text = " ".join(dict.fromkeys(token for token in tokens if _is_content(token) and not token.isdigit()))
    return PageQuery(
        question=question,
        terms=terms,
        phrases=phrases,
        statements=explicit | implied,
        explicit_statements=explicit,
        years=frozenset(_years(normalized)),
        quarter=_quarter(normalized),
        names=tuple(_candidate_names(question)),
        search_texts=(search_text,) if search_text else (),
        expansion_texts=tuple(expansions),
    )


def _weighted_terms(
    tokens: Sequence[str], expansions: Iterable[str]
) -> tuple[dict[str, float], dict[tuple[str, ...], float]]:
    terms = {stem(token): 1.0 for token in tokens if _is_content(token)}
    # Phrases keep their function words because pages are matched word for word: two
    # evidence words are a phrase when adjacent or joined by one word, as in "cost of sales".
    phrases: dict[tuple[str, ...], float] = {}
    positions = [index for index, token in enumerate(tokens) if _is_content(token)]
    for start, end in pairwise(positions):
        if end - start <= 2:
            phrases[tuple(stem(token) for token in tokens[start : end + 1])] = 1.0
    for expansion in expansions:
        words = tokenize(expansion)
        for word in words:
            if _is_content(word):
                terms.setdefault(stem(word), 0.4)
        if len(words) > 1:
            phrases.setdefault(tuple(stem(word) for word in words), 0.6)
    return terms, phrases


def document_cue(document_id: str) -> DocumentCue:
    """Parse a company and fiscal period from a FinanceBench-style document identity."""

    parts = [part for part in re.split(r"[^0-9a-z]+", unicodedata.normalize("NFKC", document_id).casefold()) if part]
    company_words: list[str] = []
    year = quarter = None
    for index, part in enumerate(parts):
        match = _DOCUMENT_YEAR.match(part)
        if match and index:
            year = int(match.group(1))
            quarter = int(match.group(2)) if match.group(2) else None
            break
        company_words.append(part)
    return DocumentCue(
        document_id=document_id,
        company="".join(company_words),
        company_words=tuple(company_words),
        year=year,
        quarter=quarter,
    )


def match_documents(query: PageQuery, documents: Iterable[str]) -> dict[str, float]:
    """Weight each document by how specifically the question names its company and period.

    The best match weighs 1.0. When the question names none of the companies, no document
    is preferred and the result is empty.
    """

    cues = [document_cue(document_id) for document_id in documents]
    if not cues:
        return {}
    question = re.sub(r"[^0-9a-z]+", "", unicodedata.normalize("NFKC", query.question).casefold())
    company_scores = {cue.document_id: _company_score(cue, question, query.names) for cue in cues}
    best_company = max(company_scores.values())
    if best_company <= 0:
        return {}
    weights: dict[str, float] = {}
    period_scores = {cue.document_id: _period_score(cue, query) for cue in cues}
    best_period = max(period_scores[cue.document_id] for cue in cues if company_scores[cue.document_id] == best_company)
    for cue in cues:
        if company_scores[cue.document_id] < best_company:
            weights[cue.document_id] = 0.05
        elif period_scores[cue.document_id] < best_period:
            weights[cue.document_id] = 0.3
        else:
            weights[cue.document_id] = 1.0
    return weights


def classify_statement(text: str) -> Statement:
    """Recognize a primary statement page from its opening title and line items."""

    flat = " ".join(text.casefold().split())
    head = flat[:_STATEMENT_HEAD_CHARACTERS]
    titled = [kind for kind in _STATEMENT_KINDS if _STATEMENT_TITLES[kind].search(head)]
    if not titled or len(titled) > 2:
        return Statement.NONE
    tokens = _TOKEN.findall(flat)
    if not tokens or sum(token.isdigit() for token in tokens) / len(tokens) < 0.2:
        return Statement.NONE
    result = Statement.NONE
    for kind in titled:
        if len(set(_STATEMENT_LINES[kind].findall(flat))) >= 2:
            result |= kind
    return result


def rank_pages(query: PageQuery, pages: Sequence[RankedPage], texts: Sequence[str]) -> list[RankedPage]:
    """Score candidate pages with BM25, phrase matches, document focus and statement structure."""

    if not pages:
        return []
    document_weights = match_documents(query, {page.document_id for page in pages})
    stems_per_page = [[stem(token) for token in tokenize(text)] for text in texts]
    frequencies = [Counter(tokens) for tokens in stems_per_page]
    lengths = [len(tokens) for tokens in stems_per_page]
    average = sum(lengths) / len(lengths) or 1.0
    document_frequency = Counter(term for counts in frequencies for term in counts if term in query.terms)
    total = len(pages)
    weights = {
        term: weight * math.log(1.0 + (total - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
        for term, weight in query.terms.items()
    }
    # A matched phrase earns its own weight times the mean weight of its evidence words.
    phrases: dict[str, tuple[float, float]] = {}
    for phrase, weight in query.phrases.items():
        strengths = [weights[term] for term in phrase if term in weights]
        if strengths:
            phrases[f" {' '.join(phrase)} "] = (weight, sum(strengths) / len(strengths))
    for page, text, tokens, counts, length in zip(pages, texts, stems_per_page, frequencies, lengths, strict=True):
        page.tokens = tokens
        score = 0.0
        for term, weight in weights.items():
            frequency = counts.get(term, 0)
            if frequency:
                score += weight * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
        if phrases:
            score += _phrase_score(phrases, tokens)
        page.statement = classify_statement(text)
        page.consolidated = bool(page.statement) and _CONSOLIDATED.search(_head(text)) is not None
        if page.statement & query.statements:
            score *= 1.5 if page.statement & query.explicit_statements else 1.25
        page.score = score * document_weights.get(page.document_id, 1.0)
    ranked = sorted(pages, key=lambda page: -page.score)
    return _promote_statements(query, ranked, document_weights)


def _promote_statements(
    query: PageQuery, ranked: list[RankedPage], document_weights: dict[str, float]
) -> list[RankedPage]:
    if not query.statements:
        return ranked
    promoted: list[RankedPage] = []
    for kind in _STATEMENT_KINDS:
        if not kind & query.statements:
            continue
        candidates = [
            page for page in ranked if page.statement & kind and document_weights.get(page.document_id, 1.0) >= 1.0
        ]
        # The consolidated statement itself outranks summaries that borrow its title.
        candidates.sort(key=lambda page: not page.consolidated)
        promoted.extend(page for page in candidates[:2] if all(page is not other for other in promoted))
    seen = {id(page) for page in promoted}
    return [*promoted, *(page for page in ranked if id(page) not in seen)]


def _phrase_score(phrases: dict[str, tuple[float, float]], tokens: list[str]) -> float:
    text = f" {' '.join(tokens)} "
    return sum(weight * strength for phrase, (weight, strength) in phrases.items() if phrase in text)


def _head(text: str) -> str:
    return " ".join(text[: _STATEMENT_HEAD_CHARACTERS * 2].casefold().split())[:_STATEMENT_HEAD_CHARACTERS]


def _is_content(token: str) -> bool:
    if token.isdigit():
        return len(token) == 4 and token[:2] in {"19", "20"}
    return len(token) > 1 and token not in _STOPWORDS


def _years(normalized: str) -> Iterable[int]:
    for match in _YEAR.finditer(normalized):
        value = match.group(1)
        if len(value) == 4:
            yield int(value)
        elif match.group(0)[0] in "f'":
            yield 2000 + int(value)


def _quarter(normalized: str) -> int | None:
    match = _QUARTER.search(normalized)
    if match is None:
        return None
    return int(match.group(1)) if match.group(1) else _ORDINAL_QUARTERS[match.group(2)]


def _candidate_names(question: str) -> Iterable[str]:
    for word in re.findall(r"[A-Za-z0-9&][A-Za-z0-9&.'\u2019-]*", unicodedata.normalize("NFKC", question)):
        if any(character.isupper() for character in word[1:]) or (word[0].isupper() or word[0].isdigit()):
            cleaned = re.sub(r"[^0-9a-z]+", "", re.sub(r"['\u2019]s?$", "", word).casefold())
            if len(cleaned) >= 2 and cleaned not in _STOPWORDS:
                yield cleaned


def _company_score(cue: DocumentCue, question: str, names: Sequence[str]) -> float:
    company = cue.company
    if not company:
        return 0.0
    if len(company) >= 2 and company in question:
        return 3.0
    significant = [word for word in cue.company_words if len(word) >= 3]
    if significant and all(word in question for word in significant):
        return 2.5
    best = 0.0
    for name in names:
        if len(name) >= 3 and (company.startswith(name) or name.startswith(company)):
            best = max(best, 2.0)
        elif len(name) >= 3 and name[0] == company[0] and _is_subsequence(name, company):
            best = max(best, 1.0)
    return best


def _period_score(cue: DocumentCue, query: PageQuery) -> float:
    score = 0.0
    if cue.year is not None and query.years:
        if cue.year == max(query.years):
            score += 2.0
        elif cue.year in query.years:
            score += 1.0
    if query.quarter is not None:
        score += 1.0 if cue.quarter == query.quarter else 0.0
    elif cue.quarter is None:
        score += 0.5
    return score


def _is_subsequence(needle: str, haystack: str) -> bool:
    characters = iter(haystack)
    return all(character in characters for character in needle)
