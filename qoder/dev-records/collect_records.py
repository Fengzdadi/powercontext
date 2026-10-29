#!/usr/bin/env python3
"""Copy Qoder's own session files into dev-records/ and redact local secrets.

Usage:
    python3 dev-records/collect_records.py [--copy SESSION_ID ...]

--copy  copies ~/.qoder-cn/projects/<this project>/<SESSION_ID>.jsonl and its
        <SESSION_ID>/subagents/ folder (sub-agent transcripts) to dev-records/qoder-native/.
Always: replaces the values of secret-looking variables in qoder/.env and qoder/.env.ci
(…PASSWORD, …API_KEY, …TOKEN, …SECRET) with ***REDACTED*** in every file under
dev-records/sessions, dev-records/transcripts and dev-records/qoder-native,
and prints how many replacements it made per file. It never prints the values.
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
QODER_PROJECTS = Path.home() / ".qoder-cn" / "projects"
NATIVE = HERE / "qoder-native"
SECRET_KEY = re.compile(r"(PASSWORD|API_KEY|TOKEN|SECRET)$")
PLACEHOLDERS = {"", "change-me", "changeme", "sk-xxx", "your-key-here"}


def qoder_project_dir() -> Path:
    name = re.sub(r"[^A-Za-z0-9]", "-", str(PROJECT))
    return QODER_PROJECTS / name


def secrets_from_env() -> list[str]:
    # .env.ci holds the random password of the throwaway compose stack Qoder tests against.
    values = []
    for env in (PROJECT / ".env", PROJECT / ".env.ci"):
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if SECRET_KEY.search(key.strip()) and value not in PLACEHOLDERS and len(value) >= 6:
                values.append(value)
    return values


def copy_session(session_id: str) -> None:
    src_dir = qoder_project_dir()
    src_file = src_dir / f"{session_id}.jsonl"
    if not src_file.exists():
        raise SystemExit(f"not found: {src_file}")
    NATIVE.mkdir(exist_ok=True)
    shutil.copy2(src_file, NATIVE / src_file.name)
    # Only the conversation itself: sub-agent transcripts and their metadata.
    # state.json / compression-v2/ hold Qoder's opaque (encrypted) local state, not conversation.
    subagents = src_dir / session_id / "subagents"
    dst = NATIVE / session_id
    if dst.exists():
        shutil.rmtree(dst)
    if subagents.is_dir():
        shutil.copytree(subagents, dst / "subagents")
    print(f"copied {session_id}")


def redact(values: list[str]) -> None:
    roots = [HERE / "sessions", HERE / "transcripts", NATIVE]
    total = 0
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            count = sum(text.count(v) for v in values)
            if count:
                for v in values:
                    text = text.replace(v, "***REDACTED***")
                path.write_text(text, encoding="utf-8")
                print(f"redacted {count} in {path.relative_to(HERE)}")
                total += count
    print(f"redaction done: {total} replacement(s), {len(values)} secret value(s) checked")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", nargs="*", default=[], metavar="SESSION_ID")
    args = ap.parse_args()
    for sid in args.copy:
        copy_session(sid)
    redact(secrets_from_env())


if __name__ == "__main__":
    main()
