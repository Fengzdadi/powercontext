"""技术使用记录：每次 seekdb 查询、PowerContext 调用和 MiniMax 请求都追加写入 JSONL。

写盘前统一脱敏：环境里的 MINIMAX_API_KEY 原值和形如 sk-… 的密钥都替换成 <redacted>。
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def scrub(text: str) -> str:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if key:
        text = text.replace(key, "<redacted>")
    return _SECRET_PATTERN.sub("<redacted>", text)


def dumps(obj: object, indent: int | None = None) -> str:
    return scrub(json.dumps(obj, ensure_ascii=False, indent=indent, default=str))


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scrub(text), encoding="utf-8")
    return path


def write_json(path: Path, obj: object) -> Path:
    return write_text(path, dumps(obj, indent=2) + "\n")


class Recorder:
    """追加式 JSONL 记录器。context 字段（当前命令、任务）会写进每一行。"""

    def __init__(self, path: Path, **context: str) -> None:
        self.path = path
        self.context = context

    def write(self, record: dict) -> None:
        line = dumps({"ts": now_iso(), **self.context, **record})
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
