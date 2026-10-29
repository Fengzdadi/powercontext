"""Command-line interface for examradar."""
from __future__ import annotations

import sys
from pathlib import Path

from .seekdb import ensure_tables, delete_course, get_connection


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

    from .ingest import ingest_bytes, ValidationError

    files: list[Path] = []
    if p.is_dir():
        for ext in ("*.md", "*.txt", "*.pdf"):
            files.extend(sorted(p.rglob(ext)))
    else:
        files = [p]

    total_chunks = 0
    imported = 0
    for fp in files:
        if fp.name.startswith("."):
            continue
        try:
            result = ingest_bytes(fp.read_bytes(), fp.name, course,
                                  kind or _detect_kind(fp))
        except ValidationError as e:
            print(f"  skip {fp.name} ({e})")
            continue

        if result["skipped"]:
            print(f"  skip {fp.name} (already imported, {result['chunk_count']} chunks)")
        else:
            print(f"  ok   {fp.name} -> {result['chunk_count']} chunks")
            total_chunks += result["chunk_count"]
            imported += 1

    print(f"\nTotal: {imported} imported, {len(files) - imported} skipped, {total_chunks} new chunks")


def _format_cell(value) -> str:
    if value is None:
        return "NULL"
    return str(value)


def run_sql(sql: str):
    """Execute one read-only-style SQL statement and print rows as a table.

    Connection info comes from settings (.env), so no password ever
    appears on the command line.
    """
    conn = get_connection()
    try:
        import pymysql.cursors
        with conn.cursor(pymysql.cursors.Cursor) as cur:
            cur.execute(sql)
            if cur.description is None:
                print(f"Affected rows: {cur.rowcount}")
                return
            columns = [d[0] for d in cur.description]
            rows = [[_format_cell(v) for v in row] for row in cur.fetchall()]
    finally:
        conn.close()

    if not rows:
        print(f"({len(columns)} columns, 0 rows)")
        return

    widths = [len(c) for c in columns]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(fmt_row(columns))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt_row(row))
    print(f"\n({len(columns)} columns, {len(rows)} rows)")


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="examradar")
    sub = parser.add_subparsers(dest="command")

    imp = sub.add_parser("import", help="Import documents")
    imp.add_argument("path", help="File or directory to import")
    imp.add_argument("--course", required=True, help="Course ID")
    imp.add_argument("--kind", choices=["notes", "slides", "exam", "paper"],
                     help="Document kind (auto-detected from directory if omitted)")

    sql_cmd = sub.add_parser("sql", help="Run a SQL statement against seekdb and print a table")
    sql_cmd.add_argument("statement", help="SQL statement, e.g. \"SELECT ...\"")

    dc = sub.add_parser("delete-course", help="Delete all data of a course")
    dc.add_argument("course", help="Course ID")

    args = parser.parse_args()
    if args.command == "import":
        import_path(args.path, args.course, args.kind)
    elif args.command == "sql":
        run_sql(args.statement)
    elif args.command == "delete-course":
        counts = delete_course(args.course)
        print(f"Deleted course {args.course}: " +
              ", ".join(f"{t}={n}" for t, n in counts.items()))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
