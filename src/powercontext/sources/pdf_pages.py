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

"""Captured PDF pages with exact document digest and physical page provenance."""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from typing import TYPE_CHECKING, Protocol
from urllib.parse import quote, unquote

from pydantic import BaseModel, ConfigDict

from powercontext.artifacts.models import MemoryCitation
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.pdf_retrieval import (
    PageQuery,
    RankedPage,
    Statement,
    analyze_question,
    document_cue,
    match_documents,
    rank_pages,
)
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

if TYPE_CHECKING:
    from powercontext.builtin.runtime import (
        GetMemoryEntryRequest,
        MemoryEntryRecord,
        MemoryHit,
        MemorySearchPage,
        SearchMemoryRequest,
    )

PDF_PAGE_SOURCE_NAME = "pdf-page"

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SURROGATES = re.compile(r"[\ud800-\udfff]")
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")

# Memory stores each page as one entry whose normalized text is bounded in UTF-8 bytes.
_MEMORY_TEXT_BYTES = 8192
_SPACED_PUNCTUATION = re.compile(r"[\W_]*\s[\W_]*")
_ASCII_PUNCTUATION = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2022": "*",
})

# Candidate pool sizes for the scoped Memory searches issued per question. A report the
# question names is read back whole; reports rarely approach the page bound.
_QUESTION_CANDIDATES = 30
_DOCUMENT_PAGES = 2000
_EXPANSION_CANDIDATES = 20
_STATEMENT_CANDIDATES = 5
_MAX_FOCUSED_DOCUMENTS = 3

# Line items that fill each primary statement, used to retrieve statement pages.
_STATEMENT_QUERIES = {
    Statement.INCOME: "statements income operations earnings net revenues sales cost of sales gross profit "
    "operating expenses income before income taxes provision net income per share diluted",
    Statement.COMPREHENSIVE: "statements comprehensive income other comprehensive loss foreign currency "
    "translation net of tax",
    Statement.BALANCE: "balance sheets total assets current assets total liabilities current liabilities accounts "
    "payable inventories property plant equipment retained earnings equity",
    Statement.CASH_FLOW: "statements cash flows operating activities investing activities financing activities "
    "depreciation amortization net cash provided used dividends paid",
    Statement.EQUITY: "statements shareholders stockholders equity retained earnings treasury stock dividends "
    "declared common stock balance",
}


class PDFDocumentInput(BaseModel):
    """One complete original PDF file and the caller-stable document identity."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """Extractable text of one physical page, numbered from the first PDF page."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """A captured page bound to the exact digest of its original PDF revision."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Extract every physical page in order, or fail without returning partial pages.

    Page text keeps the words and table figures pypdf extracts from that page only;
    layout whitespace is compacted. A page without extractable text stays empty. A page
    too long for one Memory entry also drops punctuation next to whitespace and uses ASCII
    quotes and dashes, which keeps every word, figure and boundary between them.
    """

    if not value.document_id.strip():
        raise ValueError("PDF document_id must not be blank")  # noqa: TRY003
    if not value.content:
        raise ValueError("PDF content must not be empty")  # noqa: TRY003
    document_sha256 = hashlib.sha256(value.content).hexdigest()
    return tuple(
        PDFPageInput(
            document_id=value.document_id,
            document_sha256=document_sha256,
            page_number=page_number,
            text=_fit_memory_entry(value.document_id, text),
        )
        for page_number, text in enumerate(_extract_page_texts(value.content), start=1)
    )


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    """Return the stable Source name of one page of one exact PDF revision.

    Components are percent-encoded so they cannot run together. When the readable form
    would exceed a Source reference, the document identity and digest are replaced by
    their SHA-256 under a distinct prefix; the page number always stays last.
    """

    if not document_id.strip():
        raise ValueError("PDF document_id must not be blank")  # noqa: TRY003
    if page_number < 1:
        raise ValueError("PDF page numbers start at 1")  # noqa: TRY003
    readable = f"pdf:{quote(document_id, safe='')}:{quote(document_sha256, safe='')}:{page_number}"
    if len(readable) <= MAX_SOURCE_ID_LENGTH:
        return readable
    return f"pdf-sha256:{_digest(document_id)}:{_digest(document_sha256)}:{page_number}"


class PDFPageSourceAdapter:
    """Resolve captured page inputs and read them back unchanged."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        return PDFPageSource(
            name=pdf_page_source_id(value.document_id, value.document_sha256, value.page_number),
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose page text with the document identity and the coordinates to verify it."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_ADAPTER = PDFPageSourceAdapter()
PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDF_PAGE_SOURCE_ADAPTER,
    projections=(PDFPageTextEvidenceProjection(),),
)


def _extract_page_texts(content: bytes) -> tuple[str, ...]:
    from pypdf import PdfReader

    try:
        # Strict mode rejects damage that lenient reading would silently skip, such as
        # missing objects, instead of returning pages with partial text.
        reader = PdfReader(io.BytesIO(content), strict=True)
        texts = tuple(_normalize_page_text(page.extract_text()) for page in reader.pages)
    except MemoryError:
        raise
    except Exception as error:
        raise ValueError("PDF content cannot be parsed completely") from error  # noqa: TRY003
    if not texts:
        raise ValueError("PDF content contains no pages")  # noqa: TRY003
    return texts


def _normalize_page_text(value: str) -> str:
    # Memory stores NFC text, so citations compare equal only when the page is NFC too.
    text = _CONTROL_CHARACTERS.sub(" ", _SURROGATES.sub("�", value))
    lines = (_HORIZONTAL_SPACE.sub(" ", line).strip() for line in text.splitlines())
    return unicodedata.normalize("NFC", "\n".join(line for line in lines if line))


def _fit_memory_entry(document_id: str, text: str) -> str:
    entry = unicodedata.normalize("NFC", f"{document_id}\n{text}").strip()
    if len(entry.encode("utf-8")) <= _MEMORY_TEXT_BYTES:
        return text
    # Punctuation beside whitespace never separates two words, so removing it keeps the
    # words and figures intact; punctuation inside a figure such as "1,234" stays.
    compact = _SPACED_PUNCTUATION.sub(
        lambda match: "\n" if "\n" in match.group() else " ", text.translate(_ASCII_PUNCTUATION)
    )
    return compact.strip()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


class PDFPageMemory(Protocol):
    """The scoped Memory operations used to search captured PDF pages."""

    async def search(self, request: SearchMemoryRequest, /) -> MemorySearchPage: ...

    async def get(self, request: GetMemoryEntryRequest, /) -> MemoryEntryRecord: ...


async def search_pdf_pages(memory: PDFPageMemory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Return exact citations of up to ``limit`` distinct pages that answer ``question``.

    Candidates come only from scoped Memory full-text searches. The question itself finds
    the documents in scope; every page of the report the question names is then read
    back by its document identity line. When no report is named, searches with report
    vocabulary and the primary statements its metrics come from widen the pool instead.
    Candidates are reranked offline and each returned citation is read back to keep one
    entry per physical page.
    """

    if limit < 0:
        raise ValueError("limit must not be negative")  # noqa: TRY003
    if not question.strip():
        raise ValueError("question must not be blank")  # noqa: TRY003
    if limit == 0:
        return ()
    query = analyze_question(question)
    pool = list((await _gather_candidates(memory, query)).values())
    ranked = rank_pages(
        query,
        [RankedPage(index=index, document_id=candidate.document_id) for index, candidate in enumerate(pool)],
        [candidate.text for candidate in pool],
    )
    return await _distinct_page_citations(memory, [pool[page.index] for page in ranked], limit)


class _Candidate:
    __slots__ = ("citation", "document_id", "text")

    def __init__(self, hit: MemoryHit) -> None:
        self.citation = MemoryCitation(
            memory_ref=hit.memory_ref, entry_id=hit.entry_id, entry_version_id=hit.entry_version_id
        )
        self.document_id, _, self.text = hit.text.partition("\n")


_CandidateKey = tuple[str, int, str, str]


async def _gather_candidates(memory: PDFPageMemory, query: PageQuery) -> dict[_CandidateKey, _Candidate]:
    candidates: dict[_CandidateKey, _Candidate] = {}
    for text in query.search_texts:
        await _collect(memory, candidates, text, _QUESTION_CANDIDATES)
    weights = match_documents(query, {candidate.document_id for candidate in candidates.values()})
    focused = [document_id for document_id, weight in weights.items() if weight >= 1.0]
    if 0 < len(focused) <= _MAX_FOCUSED_DOCUMENTS:
        # A named report is reranked whole, so evidence pages need not share words with the question.
        for document_id in focused:
            await _collect(memory, candidates, _document_term(document_id), _DOCUMENT_PAGES)
        return candidates
    if query.expansion_texts:
        await _collect(memory, candidates, " ".join(query.expansion_texts), _EXPANSION_CANDIDATES)
    for kind, statement_query in _STATEMENT_QUERIES.items():
        if kind & query.statements:
            await _collect(memory, candidates, statement_query, _STATEMENT_CANDIDATES)
    return candidates


async def _collect(memory: PDFPageMemory, candidates: dict[_CandidateKey, _Candidate], text: str, limit: int) -> None:
    from powercontext.builtin.runtime import SearchMemoryRequest

    if not text.strip():
        return
    page = await memory.search(SearchMemoryRequest(query=text, mode="fts", limit=limit))
    for hit in page.hits:
        key = (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
        if key not in candidates:
            candidates[key] = _Candidate(hit)


async def _distinct_page_citations(
    memory: PDFPageMemory, ranked: list[_Candidate], limit: int
) -> tuple[MemoryCitation, ...]:
    from powercontext.builtin.runtime import GetMemoryEntryRequest

    citations: list[MemoryCitation] = []
    locations: set[tuple[str, str, int]] = set()
    for candidate in ranked:
        location = _page_location(await memory.get(GetMemoryEntryRequest(citation=candidate.citation)))
        if location is None or location in locations:
            continue
        locations.add(location)
        citations.append(candidate.citation)
        if len(citations) == limit:
            break
    return tuple(citations)


def _document_term(document_id: str) -> str:
    """Return the indexed term of a document identity line that best singles it out."""

    from powercontext.builtin.artifacts.search import analyze_text

    terms = analyze_text(document_id).split()
    company = document_cue(document_id).company
    naming = [term for term in terms if company and company in re.sub(r"[\W_]+", "", term)]
    return max(naming or terms, key=len, default="")


def _page_location(record: MemoryEntryRecord) -> tuple[str, str, int] | None:
    # Only an entry backed by exactly one page is an exact page citation. Revisions of a
    # document share a location, so a re-ingested report never fills two result slots.
    if len(record.entry.sources) != 1:
        return None
    reference = record.entry.sources[0]
    if reference.source_type != PDF_PAGE_SOURCE_NAME:
        return None
    scheme, _, rest = reference.source_id.partition(":")
    document, _, rest = rest.partition(":")
    _, _, page_number = rest.rpartition(":")
    if scheme not in {"pdf", "pdf-sha256"} or not page_number.isdigit():
        return None
    return scheme, unquote(document), int(page_number)
