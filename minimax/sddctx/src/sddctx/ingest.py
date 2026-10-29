"""把业务工程的规格、代码和测试切成可检索的片段（chunk），并抽取追溯关系。

- 规格：每个 `### <ID> <标题>` 需求条目一个片段，元数据来自条目下的 `状态/接口/关联` 列表；
  没有需求条目的 Markdown（如 specs/README.md）按二级标题切成 doc 片段。
- 代码：用 ast 切到模块头部、顶层函数和类；docstring 里的 `实现: ID` 记为 implements。
- 测试：每个测试函数一个片段；`@pytest.mark.spec(...)`（含模块级、类级 pytestmark）记为 verifies。
"""

from __future__ import annotations

import ast
import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

SPEC_ID = re.compile(r"\b[A-Z]{2,5}-\d{3}\b")
ENTRY_HEADING = re.compile(r"^###\s+([A-Z]{2,5}-\d{3})\s+(.+?)\s*$")
META_LINE = re.compile(r"^-\s*(状态|接口|关联)\s*[：:]\s*(.*)$")
IMPLEMENTS = re.compile(r"实现\s*[:：]\s*([A-Z0-9\-,，、\s]+)")
BACKTICK = re.compile(r"`([^`\n]{1,80})`")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

DEFAULT_MANIFEST = {
    "project": {"id": "project", "name": "project"},
    "sources": {"specs": ["specs/*.md"], "code": ["src/**/*.py"], "tests": ["tests/test_*.py"]},
    "rules": {"read_only": ["specs/**", "tests/**"]},
}


@dataclass
class Chunk:
    chunk_id: str
    kind: str  # spec | doc | code | test | testmod
    path: str
    symbol: str
    title: str
    content: str
    start_line: int
    end_line: int
    status: str = ""
    group: str = ""
    keywords: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (rel, target)

    @property
    def content_sha(self) -> str:
        payload = "\x1f".join([self.kind, self.title, self.status, self.group, self.content])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def targets(self, rel: str) -> list[str]:
        return [target for r, target in self.links if r == rel]


def load_manifest(project_dir: Path) -> dict:
    manifest = {key: dict(value) for key, value in DEFAULT_MANIFEST.items()}
    path = project_dir / "sdd.toml"
    if path.exists():
        for key, value in tomllib.loads(path.read_text(encoding="utf-8")).items():
            manifest.setdefault(key, {}).update(value)
    return manifest


def collect(project_dir: Path) -> tuple[dict, list[Chunk]]:
    """按清单遍历工程，返回 (manifest, chunks)。chunk_id 在一个工程内唯一。"""
    manifest = load_manifest(project_dir)
    sources = manifest["sources"]
    chunks: list[Chunk] = []
    for rel in _glob(project_dir, sources.get("specs", [])):
        chunks += parse_markdown(rel, (project_dir / rel).read_text(encoding="utf-8"))
    for rel in _glob(project_dir, sources.get("code", [])):
        chunks += parse_python(rel, (project_dir / rel).read_text(encoding="utf-8"))
    for rel in _glob(project_dir, sources.get("tests", [])):
        chunks += parse_tests(rel, (project_dir / rel).read_text(encoding="utf-8"))
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_id in seen:
            raise ValueError(f"重复的片段标识：{chunk.chunk_id}（同一个规格 ID 只能定义一次）")
        seen.add(chunk.chunk_id)
    return manifest, chunks


def _glob(root: Path, patterns: list[str]) -> list[str]:
    found: set[str] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and "__pycache__" not in path.parts:
                found.add(path.relative_to(root).as_posix())
    return sorted(found)


def _span(lines: list[str], start: int, end: int) -> tuple[int, int, str]:
    """去掉片段末尾的空行，返回 (start, end, 原文)。行号从 1 开始。"""
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end, "\n".join(lines[start - 1 : end])


# ---------------------------------------------------------------- 规格


def parse_markdown(rel_path: str, text: str) -> list[Chunk]:
    lines = text.splitlines()
    doc_title, group = "", ""
    entries: list[tuple[str, str, int, str]] = []  # (spec_id, title, start, group)
    sections: list[tuple[str, int]] = []  # 没有需求条目时按二级标题切分
    for number, line in enumerate(lines, 1):
        if line.startswith("# "):
            doc_title = line[2:].strip()
        elif line.startswith("## "):
            group = line[3:].strip()
            sections.append((group, number))
        elif match := ENTRY_HEADING.match(line):
            entries.append((match.group(1), match.group(2), number, group))
    if entries:
        return [_spec_chunk(rel_path, lines, doc_title, entry, _next_heading(lines, entry[2])) for entry in entries]
    return _doc_chunks(rel_path, lines, doc_title, sections)


def _next_heading(lines: list[str], start: int) -> int:
    """条目结束于下一个一到三级标题之前。"""
    for number in range(start + 1, len(lines) + 1):
        if re.match(r"^#{1,3}\s", lines[number - 1]):
            return number - 1
    return len(lines)


def _spec_chunk(rel_path: str, lines: list[str], doc_title: str, entry: tuple, end: int) -> Chunk:
    spec_id, title, start, group = entry
    start, end, content = _span(lines, start, end)
    meta: dict[str, str] = {}
    for line in content.splitlines()[1:]:
        if match := META_LINE.match(line.strip()):
            meta[match.group(1)] = match.group(2).strip()
    references = sorted(set(SPEC_ID.findall(content)) - {spec_id})
    keywords = [doc_title, group, meta.get("接口", "")]
    keywords += [token for token in BACKTICK.findall(content)]
    return Chunk(
        chunk_id=f"spec:{spec_id}",
        kind="spec",
        path=rel_path,
        symbol=spec_id,
        title=f"{spec_id} {title}",
        content=content,
        start_line=start,
        end_line=end,
        status=meta.get("状态", ""),
        group=group or doc_title,
        keywords=" ".join(k for k in keywords if k),
        links=[("references", ref) for ref in references],
    )


def _doc_chunks(rel_path: str, lines: list[str], doc_title: str, sections: list[tuple[str, int]]) -> list[Chunk]:
    if not sections or (sections[0][1] > 1 and "\n".join(lines[1 : sections[0][1] - 1]).strip()):
        sections = [(doc_title or rel_path, 1)] + sections
    chunks = []
    for index, (title, start) in enumerate(sections):
        end = sections[index + 1][1] - 1 if index + 1 < len(sections) else len(lines)
        start, end, content = _span(lines, start, end)
        chunks.append(
            Chunk(
                chunk_id=f"doc:{rel_path}#{title}",
                kind="doc",
                path=rel_path,
                symbol=title,
                title=f"{doc_title} / {title}" if doc_title and doc_title != title else title,
                content=content,
                start_line=start,
                end_line=end,
                group=doc_title,
                keywords=" ".join(BACKTICK.findall(content)),
                links=[("references", ref) for ref in sorted(set(SPEC_ID.findall(content)))],
            )
        )
    return chunks


# ---------------------------------------------------------------- 代码


def _implements(doc: str | None) -> list[str]:
    found: list[str] = []
    for match in IMPLEMENTS.finditer(doc or ""):
        for spec_id in SPEC_ID.findall(match.group(1)):
            if spec_id not in found:
                found.append(spec_id)
    return found


def _signature(lines: list[str], node: ast.AST) -> str:
    start = node.lineno
    text = lines[start - 1].strip()
    number = start
    while not text.rstrip().endswith(":") and number < len(lines) and number < start + 12:
        text += " " + lines[number].strip()
        number += 1
    return re.sub(r"\s+", " ", text.rstrip(":"))


def _identifiers(node: ast.AST) -> tuple[list[str], list[str]]:
    """返回 (调用的函数名, 其他关键词)。关键词含参数名、属性名和较短的字符串常量。"""
    calls: list[str] = []
    words: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name and name not in calls:
                calls.append(name)
        elif isinstance(child, ast.arg):
            words.append(child.arg)
        elif isinstance(child, ast.Attribute):
            words.append(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str) and len(child.value) <= 80:
            words.append(child.value)
    return calls, words


def _module_name(rel_path: str) -> str:
    name = rel_path[:-3].replace("/", ".")
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def _first_definition_line(tree: ast.Module, total: int) -> int:
    starts = [
        min([node.lineno] + [d.lineno for d in node.decorator_list])
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    return min(starts, default=total + 1)


def parse_python(rel_path: str, text: str) -> list[Chunk]:
    tree = ast.parse(text, filename=rel_path)
    lines = text.splitlines()
    module = _module_name(rel_path)
    chunks: list[Chunk] = []

    header_end = _first_definition_line(tree, len(lines)) - 1
    if header_end >= 1:
        start, end, content = _span(lines, 1, header_end)
        if content.strip():
            calls, words = _identifiers(ast.Module(body=[n for n in tree.body if n.lineno <= header_end], type_ignores=[]))
            chunks.append(
                Chunk(
                    chunk_id=f"code:{rel_path}",
                    kind="code",
                    path=rel_path,
                    symbol=module,
                    title=f"module {module}",
                    content=content,
                    start_line=start,
                    end_line=end,
                    group=module,
                    keywords=" ".join([rel_path, module] + words),
                    links=[("implements", s) for s in _implements(ast.get_docstring(tree))]
                    + [("calls", c) for c in calls],
                )
            )

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        start, end, content = _span(lines, start, node.end_lineno or node.lineno)
        docs = [ast.get_docstring(node)]
        if isinstance(node, ast.ClassDef):
            docs += [ast.get_docstring(n) for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        implements: list[str] = []
        for doc in docs:
            implements += [s for s in _implements(doc) if s not in implements]
        calls, words = _identifiers(node)
        chunks.append(
            Chunk(
                chunk_id=f"code:{rel_path}::{node.name}",
                kind="code",
                path=rel_path,
                symbol=node.name,
                title=_signature(lines, node),
                content=content,
                start_line=start,
                end_line=end,
                group=module,
                keywords=" ".join([rel_path, module, node.name] + words),
                links=[("implements", s) for s in implements] + [("calls", c) for c in calls if c != node.name],
            )
        )
    return chunks


# ---------------------------------------------------------------- 测试


def _spec_marks(decorators: list[ast.expr]) -> list[str]:
    """从 `pytest.mark.spec("A", "B")` 这类表达式里取规格 ID。"""
    found: list[str] = []
    for deco in decorators:
        items = deco.elts if isinstance(deco, (ast.List, ast.Tuple)) else [deco]
        for item in items:
            if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == "spec":
                for arg in item.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value not in found:
                        found.append(arg.value)
    return found


def _pytestmark(body: list[ast.stmt]) -> list[str]:
    for stmt in body:
        if isinstance(stmt, ast.Assign) and any(getattr(t, "id", "") == "pytestmark" for t in stmt.targets):
            return _spec_marks([stmt.value])
    return []


def _case_count(decorators: list[ast.expr]) -> int:
    count = 1
    for deco in decorators:
        if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and deco.func.attr == "parametrize":
            if len(deco.args) >= 2 and isinstance(deco.args[1], (ast.List, ast.Tuple)):
                count *= max(1, len(deco.args[1].elts))
    return count


def parse_tests(rel_path: str, text: str) -> list[Chunk]:
    tree = ast.parse(text, filename=rel_path)
    lines = text.splitlines()
    module_marks = _pytestmark(tree.body)
    chunks: list[Chunk] = []

    def add_test(node: ast.FunctionDef, prefix: str, inherited: list[str]) -> None:
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        start, end, content = _span(lines, start, node.end_lineno or node.lineno)
        verifies = list(dict.fromkeys(inherited + _spec_marks(node.decorator_list)))
        cases = _case_count(node.decorator_list)
        doc = (ast.get_docstring(node) or "").strip().splitlines()
        calls, words = _identifiers(node)
        node_id = f"{rel_path}::{prefix}{node.name}"
        title = node.name + (f" [{cases} 个参数化用例]" if cases > 1 else "") + (f"：{doc[0]}" if doc else "")
        chunks.append(
            Chunk(
                chunk_id=f"test:{node_id}",
                kind="test",
                path=rel_path,
                symbol=f"{prefix}{node.name}",
                title=title,
                content=content,
                start_line=start,
                end_line=end,
                group=rel_path,
                keywords=" ".join([rel_path, node.name] + words + calls),
                links=[("verifies", s) for s in verifies] + [("calls", c) for c in calls],
            )
        )

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            add_test(node, "", module_marks)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            class_marks = module_marks + _spec_marks(node.decorator_list) + _pytestmark(node.body)
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("test"):
                    add_test(item, f"{node.name}::", class_marks)

    header_end = _first_definition_line(tree, len(lines)) - 1
    if header_end >= 1:
        start, end, content = _span(lines, 1, header_end)
        chunks.append(
            Chunk(
                chunk_id=f"testmod:{rel_path}",
                kind="testmod",
                path=rel_path,
                symbol=_module_name(rel_path),
                title=f"test module {rel_path}",
                content=content,
                start_line=start,
                end_line=end,
                group=rel_path,
                keywords=rel_path,
                links=[("verifies", s) for s in module_marks],
            )
        )
    return chunks
