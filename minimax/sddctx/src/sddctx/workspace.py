"""工作区：复制工程、计算目录指纹（代码版本）、生成与应用统一 diff，以及只读路径保护。"""

from __future__ import annotations

import difflib
import hashlib
import re
import shutil
from functools import lru_cache
from pathlib import Path

IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".git", ".venv"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def iter_files(root: Path) -> list[str]:
    files = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_file() and not (set(rel.parts) & IGNORED_PARTS) and path.suffix not in IGNORED_SUFFIXES:
            files.append(rel.as_posix())
    return sorted(files)


@lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out)


def glob_match(rel_path: str, pattern: str) -> bool:
    """与 sdd.toml 里的 glob 一致：`**/` 匹配零或多层目录，`*` 不跨目录。"""
    return _glob_regex(pattern).fullmatch(rel_path) is not None


def matches_any(rel_path: str, patterns: list[str]) -> bool:
    return any(glob_match(rel_path, pattern) for pattern in patterns)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha(root: Path, patterns: list[str] | None = None) -> str:
    """目录指纹：按路径排序后对 (相对路径, 文件 sha256) 求 sha256。patterns 用于只看部分文件。"""
    digest = hashlib.sha256()
    for rel in iter_files(root):
        if patterns and not matches_any(rel, patterns):
            continue
        digest.update(f"{rel}\0{file_sha(root / rel)}\n".encode())
    return digest.hexdigest()


def copy_tree(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORED_PARTS, "*.pyc", "*.pyo"))
    return dst


def is_read_only(rel_path: str, read_only: list[str]) -> bool:
    return matches_any(rel_path, read_only)


def diff_trees(before: Path, after: Path) -> str:
    """git 风格的统一 diff（a/ b/ 前缀），可直接用 `git apply` 或 `patch -p1` 应用。"""
    old_files, new_files = set(iter_files(before)), set(iter_files(after))
    chunks: list[str] = []
    for rel in sorted(old_files | new_files):
        old = (before / rel).read_text(encoding="utf-8").splitlines(keepends=True) if rel in old_files else []
        new = (after / rel).read_text(encoding="utf-8").splitlines(keepends=True) if rel in new_files else []
        if old == new:
            continue
        header = [f"diff --git a/{rel} b/{rel}\n"]
        if rel not in old_files:
            header.append("new file mode 100644\n")
        elif rel not in new_files:
            header.append("deleted file mode 100644\n")
        body = difflib.unified_diff(
            old,
            new,
            fromfile=f"a/{rel}" if rel in old_files else "/dev/null",
            tofile=f"b/{rel}" if rel in new_files else "/dev/null",
        )
        lines = []
        for line in body:
            lines.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
        chunks.append("".join(header + lines))
    return "".join(chunks)


def changed_files(before: Path, after: Path) -> list[str]:
    old_files, new_files = set(iter_files(before)), set(iter_files(after))
    return [
        rel
        for rel in sorted(old_files | new_files)
        if rel not in old_files or rel not in new_files or file_sha(before / rel) != file_sha(after / rel)
    ]


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
