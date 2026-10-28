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

from __future__ import annotations

import asyncio

from powercontext.builtin.artifacts.memory import MemoryCandidateRequest, MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import (
    BuiltinConfig,
    GetMemoryEntryRequest,
    SubmitSourceObservation,
    open_builtin_runtime,
)
from powercontext.builtin.scope import ScopeDraft
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    SourceDefinitionRegistry,
    SourceObservation,
    TextEvidence,
    manifest_for_definition,
    project_source_for_transport,
)
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    parse_pdf_document,
    search_pdf_pages,
)
from tests.test_pdf_pages import text_pdf


def _report(company: str, revenue: str, net_income: str, total_assets: str) -> tuple[str, ...]:
    return (
        f"{company} Corporation\nAnnual Report on Form 10-K\nFiscal year ended December 31, 2022",
        "",
        "Management's discussion and analysis\nNet revenues grew because demand for widgets was strong.\n"
        "Net income increased as cost of sales improved.",
        f"{company} Corporation\nConsolidated Statements of Operations\n(in millions, except per share data) 2022 2021\n"
        f"Net revenues {revenue} 8,765\nCost of sales 5,432 4,321\nGross profit 4,444 4,444\n"
        "Operating income 1,500 1,400\nIncome before income taxes 1,450 1,350\n"
        f"Provision for income taxes 216 200\nNet income {net_income} 1,150\nDiluted earnings per share 2.10 1.95",
        f"{company} Corporation\nConsolidated Balance Sheets\n(in millions) 2022 2021\n"
        "Cash and cash equivalents 500 450\nInventories 900 850\nTotal current assets 2,000 1,900\n"
        f"Total assets {total_assets} 11,500\nAccounts payable 700 650\nTotal current liabilities 1,500 1,400\n"
        "Total liabilities 7,000 6,900\nRetained earnings 3,000 2,800\nTotal equity 5,000 4,600",
    )


class _PageEvidencePipeline:
    async def extract(self, request: MemoryCandidateRequest, /) -> tuple[MemoryEntryInput, ...]:
        return tuple(
            MemoryEntryInput(
                kind="source-evidence",
                text=TextEvidence.model_validate(source.projection(TEXT_EVIDENCE_PROJECTION_KEY)).content,
                sources=(source,),
            )
            for source in request.sources
            if isinstance(source, SourceObservation)
        )


async def _remember_pages(
    config: BuiltinConfig, *documents: PDFDocumentInput
) -> tuple[str, dict[str, tuple[str, int]]]:
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    locations: dict[str, tuple[str, int]] = {}
    async with open_builtin_runtime(config, candidate_pipeline=_PageEvidencePipeline()) as runtime:
        assert runtime.scopes is not None
        scope = await runtime.scopes.create(
            ScopeDraft(title="Reports", summary="Annual reports", idempotency_key="reports")
        )
        await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
        for document in documents:
            for page in parse_pdf_document(document):
                source = await registry.resolve(page)
                locations[source.name] = (page.document_id, page.page_number)
                await runtime.ingestion.submit(
                    SubmitSourceObservation(
                        scope_id=scope.scope_id, observation=project_source_for_transport(registry, source)
                    )
                )
        memory = runtime.memory.for_scope(scope.scope_id)
        for _ in range(len(locations) + 1):
            if not (await memory.flush()).processed:
                break
    return scope.scope_id, locations


async def _cited_pages(memory, citations, locations) -> list[tuple[str, int]]:
    pages = []
    for citation in citations:
        entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
        assert len(entry.sources) == 1
        pages.append(locations[entry.sources[0].source_id])
    return pages


def test_search_cites_the_statement_page_of_the_report_a_question_names(tmp_path) -> None:
    async def scenario() -> None:
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'reports.db'}"))
        scope_id, locations = await _remember_pages(
            config,
            PDFDocumentInput(
                document_id="acme_2022_10k", content=text_pdf(*_report("ACME", "9,876", "1,234", "12,000"))
            ),
            PDFDocumentInput(
                document_id="globex_2022_10k", content=text_pdf(*_report("Globex", "7,654", "987", "15,500"))
            ),
        )

        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope_id)
            income = await search_pdf_pages(memory, "What is ACME's FY2022 net income in USD millions?", limit=3)
            assets = await search_pdf_pages(memory, "How much were Globex's total assets at the end of FY2022?")
            single = await search_pdf_pages(memory, "What is ACME's FY2022 net income in USD millions?", limit=1)
            none = await search_pdf_pages(memory, "What is ACME's FY2022 net income in USD millions?", limit=0)

            income_pages = await _cited_pages(memory, income, locations)
            asset_pages = await _cited_pages(memory, assets, locations)
            assert income_pages[0] == ("acme_2022_10k", 4)
            assert asset_pages[0] == ("globex_2022_10k", 5)
            assert len(income_pages) <= 3 and len(set(income_pages)) == len(income_pages)
            assert len(set(asset_pages)) == len(asset_pages)
            assert await _cited_pages(memory, single, locations) == [("acme_2022_10k", 4)]
            assert none == ()

    asyncio.run(scenario())


def test_search_returns_each_page_once_when_a_report_is_ingested_again(tmp_path) -> None:
    async def scenario() -> None:
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'revisions.db'}"))
        original = _report("ACME", "9,876", "1,234", "12,000")
        amended = (original[0].replace("Form 10-K", "Form 10-K/A"), *original[1:])
        scope_id, locations = await _remember_pages(
            config,
            PDFDocumentInput(document_id="acme_2022_10k", content=text_pdf(*original)),
            PDFDocumentInput(document_id="acme_2022_10k", content=text_pdf(*amended)),
        )

        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope_id)
            citations = await search_pdf_pages(memory, "ACME FY2022 net income and net revenues", limit=10)

            pages = await _cited_pages(memory, citations, locations)
            assert len(set(locations.values())) == 5
            assert pages[0] == ("acme_2022_10k", 4)
            assert len(set(pages)) == len(pages)

    asyncio.run(scenario())
