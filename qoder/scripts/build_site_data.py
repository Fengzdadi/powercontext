#!/usr/bin/env python3
"""Parse dev-records/CREDITS.md into site/data/qoder-sessions.json.

Standard library only. Run from the qoder/ directory:

    python3 scripts/build_site_data.py

The site renders the session table and totals from the generated JSON, so
re-running this script after CREDITS.md gains rows is all that is needed to
update the website.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

QODER_DIR = Path(__file__).resolve().parent.parent
CREDITS_MD = QODER_DIR / "dev-records" / "CREDITS.md"
OUT_JSON = QODER_DIR / "site" / "data" / "qoder-sessions.json"

EXPECTED_HEADERS = ["#", "会话", "日期", "模型", "轮数", "耗时", "Credits", "累计"]


def parse_number(cell: str) -> int | float | None:
    text = cell.strip().replace(",", "")
    if not text or text == "—":
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if match is None:
        return None
    value = float(match.group(1))
    return int(value) if value.is_integer() else value


def parse_table(lines: list[str]) -> list[dict]:
    rows: list[dict] = []
    header_seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not header_seen:
            if cells[: len(EXPECTED_HEADERS)] == EXPECTED_HEADERS:
                header_seen = True
            continue
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        if len(cells) != len(EXPECTED_HEADERS):
            continue
        row_id, title, date, model, turns, duration, _credits, _cumulative = cells
        rows.append(
            {
                "id": row_id,
                "title": title,
                "date": date,
                "model": model,
                "turns": parse_number(turns),
                "duration": duration,
            }
        )
    if not header_seen:
        raise SystemExit("CREDITS.md: session table header not found")
    return rows


def main() -> None:
    lines = CREDITS_MD.read_text(encoding="utf-8").splitlines()
    rows = parse_table(lines)
    total_turns = sum(r["turns"] or 0 for r in rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "dev-records/CREDITS.md",
        "rows": rows,
        "totals": {
            "rows": len(rows),
            "turns": total_turns,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT_JSON.relative_to(QODER_DIR)}: {len(rows)} rows, "
          f"{total_turns} turns")


if __name__ == "__main__":
    sys.exit(main())
