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
import hashlib
import io
import re
from collections import Counter

import pytest
from pypdf import PdfReader, PdfWriter

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    SourceDefinitionRegistry,
    SourceMaterialization,
    project_source_for_transport,
)
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    PDFPageInput,
    parse_pdf_document,
)


def text_pdf(*pages: str) -> bytes:
    """Build a minimal PDF that draws each line of each page with a standard font."""

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        operations = [b"BT /F1 12 Tf 14 TL 72 720 Td"]
        for line in text.splitlines():
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            operations.append(b"(%s) Tj T*" % escaped.encode("latin-1"))
        stream = b"\n".join([*operations, b"ET"])
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
            b"/Contents %d 0 R >>" % len(objects)
        )
        kids.append(b"%d 0 R" % len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))
    document = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(document)
    document += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    document += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    document += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(document)


def encrypted_pdf(content: bytes, *, user_password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(content)))
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm="AES-128")  # noqa: S106
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_parse_pdf_document_returns_every_physical_page_in_order() -> None:
    content = text_pdf("ACME Corp annual report\nFiscal 2022", "", "Net income (loss)   1,234\nTotal revenue 9,876")

    pages = parse_pdf_document(PDFDocumentInput(document_id="acme-2022", content=content))

    digest = hashlib.sha256(content).hexdigest()
    assert pages == (
        PDFPageInput(
            document_id="acme-2022",
            document_sha256=digest,
            page_number=1,
            text="ACME Corp annual report\nFiscal 2022",
        ),
        PDFPageInput(document_id="acme-2022", document_sha256=digest, page_number=2, text=""),
        PDFPageInput(
            document_id="acme-2022",
            document_sha256=digest,
            page_number=3,
            text="Net income (loss) 1,234\nTotal revenue 9,876",
        ),
    )


def test_parse_pdf_document_fits_a_long_page_into_one_memory_entry_without_losing_words() -> None:
    long_page = "\n".join(f"(Exhibit 10.{index}*), filed (see note)." for index in range(260))
    content = text_pdf(long_page, "Net income (loss) 1,234")

    pages = parse_pdf_document(PDFDocumentInput(document_id="exhibits", content=content))

    def words(text: str) -> Counter[str]:
        return Counter(re.findall(r"[a-z]+|\d+", text.lower()))

    assert len(long_page.encode()) > 8192
    assert len(f"exhibits\n{pages[0].text}".encode()) <= 8192
    assert words(pages[0].text) == words(long_page)
    assert pages[1].text == "Net income (loss) 1,234"


def test_parse_pdf_document_reads_documents_without_a_user_password() -> None:
    content = encrypted_pdf(text_pdf("Owner permissions only"), user_password="")

    pages = parse_pdf_document(PDFDocumentInput(document_id="permissions", content=content))

    assert [(page.page_number, page.text) for page in pages] == [(1, "Owner permissions only")]
    assert pages[0].document_sha256 == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"%PDF-1.7\nnot a document", id="not-a-pdf"),
        pytest.param(text_pdf("Truncated report")[:200], id="truncated"),
        pytest.param(text_pdf("Damaged report").replace(b"4 0 obj", b"9 0 obj", 1), id="missing-page-content"),
        pytest.param(encrypted_pdf(text_pdf("Private report"), user_password="secret"), id="user-password"),  # noqa: S106
    ],
)
def test_parse_pdf_document_rejects_documents_it_cannot_read_completely(content: bytes) -> None:
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id="invalid", content=content))


def test_parse_pdf_document_requires_a_document_identity() -> None:
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id=" \t", content=text_pdf("Untitled report")))


def test_pdf_page_source_reads_back_and_projects_exact_page_evidence() -> None:
    async def scenario() -> None:
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        page = PDFPageInput(document_id="acme-2022", document_sha256="a" * 64, page_number=3, text="Net income 1,234")

        source = await registry.resolve(page)
        observation = project_source_for_transport(registry, source)

        assert source.materialization is SourceMaterialization.CAPTURED
        assert (await registry.resolve(page)).name == source.name
        assert await registry.read(source) == page
        assert observation.projection(TEXT_EVIDENCE_PROJECTION_KEY) == {
            "source_type": "pdf-page",
            "source_id": source.name,
            "content": "acme-2022\nNet income 1,234",
            "metadata": {"document_id": "acme-2022", "document_sha256": "a" * 64, "page_number": 3},
        }

    asyncio.run(scenario())


def test_pdf_page_source_identity_distinguishes_documents_revisions_and_pages() -> None:
    async def scenario() -> None:
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        long_id = "annual-report-" * 30
        coordinates = [
            ("acme", "a" * 64, 1),
            ("acme", "a" * 64, 2),
            ("acme", "b" * 64, 1),
            ("acme-2023", "a" * 64, 1),
            ("a:b", "c", 1),
            ("a", "b:c", 1),
            (f"{long_id}1", "a" * 64, 1),
            (f"{long_id}2", "a" * 64, 1),
            (f"{long_id}1", "a" * 64, 12),
        ]

        names = [
            (
                await registry.resolve(
                    PDFPageInput(document_id=document_id, document_sha256=digest, page_number=page_number, text="")
                )
            ).name
            for document_id, digest, page_number in coordinates
        ]

        assert len(set(names)) == len(coordinates)
        assert all(len(name) <= MAX_SOURCE_ID_LENGTH for name in names)

    asyncio.run(scenario())
