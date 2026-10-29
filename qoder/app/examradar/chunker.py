"""Document chunking: Markdown, PDF (slides/paper/exam), plain text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .cleaner import clean_extracted_text, normalize_text, strip_footer_page_number, join_intra_paragraph_lines, join_exam_lines


@dataclass
class Chunk:
    content: str
    heading: Optional[str] = None
    page: Optional[int] = None
    question_no: Optional[int] = None
    points: Optional[float] = None
    chunk_index: int = 0


@dataclass
class ChunkResult:
    chunks: list[Chunk] = field(default_factory=list)
    file_type: str = ""
    page_count: int = 0


def chunk_markdown(text: str, max_chars: int = 1000) -> list[Chunk]:
    """Split Markdown by heading hierarchy, preserving heading path.
    Long sections are further split by paragraphs if they exceed max_chars."""
    lines = text.split("\n")
    sections: list[tuple[list[tuple[int, str]], list[str]]] = []

    current_path: list[tuple[int, str]] = []
    current_lines: list[str] = []

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if current_lines or current_path:
                sections.append((list(current_path), current_lines))
            while current_path and current_path[-1][0] >= level:
                current_path.pop()
            current_path.append((level, title))
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines or current_path:
        sections.append((list(current_path), current_lines))

    chunks: list[Chunk] = []
    idx = 0
    for path, sec_lines in sections:
        heading_str = " > ".join(t for _, t in path) if path else None
        content = "\n".join(sec_lines).strip()
        if not content:
            continue

        if len(content) <= max_chars:
            chunks.append(Chunk(content=content, heading=heading_str, chunk_index=idx))
            idx += 1
        else:
            paragraphs = re.split(r"\n\n+", content)
            buf = ""
            for para in paragraphs:
                if buf and len(buf) + len(para) + 2 > max_chars:
                    chunks.append(Chunk(content=buf.strip(), heading=heading_str, chunk_index=idx))
                    idx += 1
                    buf = para
                else:
                    buf = buf + "\n\n" + para if buf else para
            if buf.strip():
                chunks.append(Chunk(content=buf.strip(), heading=heading_str, chunk_index=idx))
                idx += 1

    return chunks


def chunk_text(text: str, max_chars: int = 800) -> list[Chunk]:
    """Split plain text by paragraphs."""
    paragraphs = re.split(r"\n\n+", text.strip())
    chunks: list[Chunk] = []
    idx = 0
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if buf and len(buf) + len(para) + 2 > max_chars:
            chunks.append(Chunk(content=buf, chunk_index=idx))
            idx += 1
            buf = para
        else:
            buf = buf + "\n\n" + para if buf else para
    if buf.strip():
        chunks.append(Chunk(content=buf, chunk_index=idx))
    return chunks


_EXAM_Q_RE = re.compile(
    r"(\d+)\s*[.、．]\s*[（(]\s*(\d+(?:\.\d+)?)\s*分\s*[）)]"
)


def chunk_exam_pdf(raw_text: str, page_texts: list[str]) -> list[Chunk]:
    """Split an exam PDF by question number. Each question becomes one chunk
    with question_no and points extracted."""
    full_text = "\n".join(page_texts)
    full_text = clean_extracted_text(full_text)
    full_text = join_exam_lines(full_text)

    matches = list(_EXAM_Q_RE.finditer(full_text))
    if not matches:
        return chunk_text(full_text)

    chunks: list[Chunk] = []
    for i, m in enumerate(matches):
        q_no = int(m.group(1))
        pts = float(m.group(2))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()

        page_num = None
        offset = 0
        for pi, pt in enumerate(page_texts):
            offset += len(pt)
            if start < offset:
                page_num = pi + 1
                break

        chunks.append(Chunk(
            content=content,
            heading=f"第{q_no}题",
            page=page_num,
            question_no=q_no,
            points=pts,
            chunk_index=len(chunks),
        ))

    return chunks


def _extract_pdf_pages(filepath: str) -> list[str]:
    """Extract cleaned text of every page with pypdfium2."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(filepath)
    try:
        page_texts = []
        for i in range(len(doc)):
            textpage = doc[i].get_textpage()
            raw = textpage.get_text_range()
            cleaned = clean_extracted_text(raw)
            page_texts.append(strip_footer_page_number(cleaned))
        return page_texts
    finally:
        doc.close()


def chunk_pdf(filepath: str, doc_kind: str = "slides") -> ChunkResult:
    """Chunk a PDF file. Behavior depends on doc_kind:
    - exam: split by question number with points
    - slides/paper: split by page, heading = first line of each page
    """
    result = ChunkResult(file_type="pdf")
    page_texts = _extract_pdf_pages(filepath)
    result.page_count = len(page_texts)

    if doc_kind == "exam":
        result.chunks = chunk_exam_pdf("", page_texts)
        return result

    chunks: list[Chunk] = []
    for i, pt in enumerate(page_texts):
        if not pt.strip():
            continue
        joined = join_intra_paragraph_lines(pt)
        lines = joined.strip().split("\n")
        title = lines[0].strip() if lines else None
        content = joined.strip()
        chunks.append(Chunk(
            content=content,
            heading=title,
            page=i + 1,
            chunk_index=len(chunks),
        ))

    result.chunks = chunks
    return result


def chunk_file(filepath: str, doc_kind: str = "notes") -> ChunkResult:
    """Auto-detect file type and chunk accordingly."""
    p = Path(filepath)
    ext = p.suffix.lower()
    result = ChunkResult()

    if ext == ".md":
        text = p.read_text(encoding="utf-8")
        result.file_type = "md"
        result.chunks = chunk_markdown(text)
    elif ext == ".txt":
        text = p.read_text(encoding="utf-8")
        result.file_type = "txt"
        result.chunks = chunk_text(text)
    elif ext == ".pdf":
        result = chunk_pdf(filepath, doc_kind)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return result
