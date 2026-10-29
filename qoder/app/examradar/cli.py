"""Command-line interface for examradar."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from .config import get_settings
from .seekdb import ensure_tables, insert_document, insert_chunk, find_document_by_sha256, insert_usage_event
from .chunker import chunk_file
from .embedding import get_embedding_model


_KIND_MAP = {
    "notes": "notes",
    "slides": "slides",
    "exams": "exam",
    "exam": "exam",
    "papers": "paper",
    "paper": "paper",
}


def _detect_kind(filepath: Path) -> str:
    parent = filepath.parent.name.lower()
    for key, kind in _KIND_MAP.items():
        if key in parent:
            return kind
    return "notes"


def import_path(path: str, course: str, kind: str | None = None):
    ensure_tables()
    p = Path(path)
    if not p.exists():
        print(f"Error: {path} does not exist", file=sys.stderr)
        sys.exit(1)

    model = get_embedding_model()
    files: list[Path] = []
    if p.is_dir():
        for ext in ("*.md", "*.txt", "*.pdf"):
            files.extend(sorted(p.rglob(ext)))
    else:
        files = [p]

    total_chunks = 0
    for fp in files:
        if fp.name.startswith("."):
            continue
        content = fp.read_bytes()
        sha = hashlib.sha256(content).hexdigest()

        existing = find_document_by_sha256(sha)
        if existing:
            print(f"  skip {fp.name} (already imported, {existing['chunk_count']} chunks)")
            continue

        doc_kind = kind or _detect_kind(fp)
        result = chunk_file(str(fp), doc_kind)
        doc_id = insert_document(course, fp.name, doc_kind,
                                 result.file_type or fp.suffix.lstrip("."),
                                 sha, len(result.chunks))

        texts = [c.content for c in result.chunks]
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = model.embed(batch)
            for j, emb in enumerate(embeddings):
                ci = i + j
                c = result.chunks[ci]
                insert_chunk(
                    document_id=doc_id, course_id=course, doc_kind=doc_kind,
                    content=c.content, heading=c.heading, page=c.page,
                    question_no=c.question_no, points=c.points,
                    chunk_index=c.chunk_index, embedding=emb,
                )

        insert_usage_event(course, "real", "import", {
            "document_id": doc_id, "doc_kind": doc_kind,
            "chunk_count": len(result.chunks), "filename": fp.name,
        })
        print(f"  ok   {fp.name} -> {len(result.chunks)} chunks")
        total_chunks += len(result.chunks)

    print(f"\nTotal: {len(files)} files, {total_chunks} new chunks")


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="examradar")
    sub = parser.add_subparsers(dest="command")

    imp = sub.add_parser("import", help="Import documents")
    imp.add_argument("path", help="File or directory to import")
    imp.add_argument("--course", required=True, help="Course ID")
    imp.add_argument("--kind", choices=["notes", "slides", "exam", "paper"],
                     help="Document kind (auto-detected from directory if omitted)")

    args = parser.parse_args()
    if args.command == "import":
        import_path(args.path, args.course, args.kind)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
