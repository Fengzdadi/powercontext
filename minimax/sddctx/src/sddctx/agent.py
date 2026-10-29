"""MiniMax 开发助手：把任务和上下文交给 MiniMax，通过工具调用读代码、改代码、跑测试。

代码修改全部由模型发起的 edit_file / write_file 工具调用完成，本模块只负责执行工具、拦截对只读路径
（specs/、tests/ 等）的写入，并把每一轮请求、响应和工具结果写进开发记录（session.json）。
回放（replay）时按记录里成功的修改调用逐条重放，得到与记录一致的代码差异。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .minimax import MiniMaxClient
from .records import now_iso, write_json
from .workspace import diff_trees, is_read_only, matches_any, sha_text

SYSTEM_PROMPT = """你是一名严谨的软件工程师，正在一个采用规格驱动开发（SDD）的 Python 工程里完成一项开发任务。

工作方式：
1. 先读用户消息里的“任务上下文”。它由上下文模块从 seekdb 检索生成，列出了本次要实现的规格条目、必须遵守的约束、需要修改的代码、目标测试和回归测试，以及 PowerContext 中保存的任务状态。
2. 需要时用 read_file、list_dir、search 查看工程文件，确认现有实现后再修改。
3. 只修改实现代码（library/ 下的 .py 文件）。specs/、tests/、sdd.toml、pyproject.toml 是只读的：规格和测试由维护者负责，不允许修改、删除或跳过测试，也不要为了让测试通过而写针对测试数据的特殊分支。
4. 改动保持最小、聚焦：沿用现有的代码风格和错误处理方式（参数错误抛 InvalidParameter），优先复用已有的参数解析函数；在实现了新条目的函数 docstring 里补上 `实现:` 标注。
5. 修改后先运行目标测试（run_tests，suite=target），再运行回归测试（suite=regression）。有失败就分析原因继续修改，直到全部通过。
6. 全部通过后调用 finish，用中文简要说明改了哪些文件、实现了哪些条目、测试结果。"""

TOOLS = [
    {
        "name": "list_dir",
        "description": "列出工程中某个目录下的文件和子目录。路径相对工程根目录。",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "目录，默认为 ."}}},
    },
    {
        "name": "read_file",
        "description": "读取工程中的文本文件，返回带行号的内容。可以用 start_line/end_line 只读一段。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search",
        "description": "在工程文件中按正则表达式搜索，返回匹配的文件、行号和内容（最多 60 条）。",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "path": {"type": "string", "description": "限定目录，默认 ."}},
            "required": ["pattern"],
        },
    },
    {
        "name": "edit_file",
        "description": "把文件中唯一出现的一段文本 old_text 替换为 new_text。old_text 必须与文件内容逐字一致（包括缩进和换行），并且在文件中只出现一次；可以多带几行上下文来保证唯一。",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "write_file",
        "description": "创建新文件，或用 content 整体覆盖已有文件。只能写实现代码。",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_tests",
        "description": "运行测试。suite=target：目标测试；suite=regression：全部非目标测试；suite=all：全部测试。返回通过/失败统计和失败详情。",
        "input_schema": {
            "type": "object",
            "properties": {"suite": {"type": "string", "enum": ["target", "regression", "all"]}},
            "required": ["suite"],
        },
    },
    {
        "name": "finish",
        "description": "任务完成时调用。summary 用中文说明修改了哪些文件、实现了哪些规格条目、测试结果。",
        "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
    },
]

WRITE_TOOLS = {"edit_file", "write_file"}
MAX_TOOL_OUTPUT = 12000


@dataclass
class AgentResult:
    status: str  # finished | stopped | error
    summary: str
    turns: int
    session_path: Path
    diff: str
    diff_sha: str
    changed_files: list[str]
    edits: int
    read_only_violations: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    last_tests: dict = field(default_factory=dict)


class Workspace:
    """工具执行环境：所有路径都限制在工作区内；只能写 writable（sdd.toml 的 code 范围），只读路径拒绝写入。"""

    def __init__(self, root: Path, read_only: list[str], writable: list[str], test_runner) -> None:
        self.root = root.resolve()
        self.read_only = read_only
        self.writable = writable
        self.test_runner = test_runner

    def _resolve(self, path: str) -> tuple[Path, str]:
        target = (self.root / (path or ".")).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"路径越界：{path}")
        return target, target.relative_to(self.root).as_posix() if target != self.root else "."

    def execute(self, name: str, args: dict) -> tuple[bool, str, dict]:
        try:
            handler = getattr(self, f"tool_{name}")
        except AttributeError:
            return False, f"未知工具：{name}", {}
        try:
            return handler(**args)
        except TypeError as exc:
            return False, f"参数错误：{exc}", {}
        except (ValueError, OSError, UnicodeDecodeError, re.error) as exc:
            return False, f"{type(exc).__name__}: {exc}", {}

    def tool_list_dir(self, path: str = ".") -> tuple[bool, str, dict]:
        target, rel = self._resolve(path)
        if not target.is_dir():
            return False, f"不是目录：{rel}", {}
        entries = []
        for child in sorted(target.iterdir()):
            if child.name in {"__pycache__", ".pytest_cache"}:
                continue
            entries.append(child.name + ("/" if child.is_dir() else ""))
        return True, "\n".join(entries) or "（空目录）", {}

    def tool_read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> tuple[bool, str, dict]:
        target, rel = self._resolve(path)
        if not target.is_file():
            return False, f"文件不存在：{rel}", {}
        lines = target.read_text(encoding="utf-8").splitlines()
        start = max(1, start_line or 1)
        end = min(len(lines), end_line or len(lines), start + 499)
        body = "\n".join(f"{n:>4}| {lines[n - 1]}" for n in range(start, end + 1))
        more = f"\n…（共 {len(lines)} 行，只显示到第 {end} 行）" if end < len(lines) else ""
        return True, f"{rel}（第 {start}-{end} 行，共 {len(lines)} 行）\n{body}{more}", {}

    def tool_search(self, pattern: str, path: str = ".") -> tuple[bool, str, dict]:
        target, _ = self._resolve(path)
        regex = re.compile(pattern)
        matches = []
        files = [target] if target.is_file() else sorted(p for p in target.rglob("*") if p.is_file())
        for file in files:
            if "__pycache__" in file.parts or file.suffix in {".pyc", ".json"} and file.stat().st_size > 200_000:
                continue
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(lines, 1):
                if regex.search(line):
                    matches.append(f"{file.relative_to(self.root).as_posix()}:{number}: {line.strip()[:200]}")
                    if len(matches) >= 60:
                        return True, "\n".join(matches) + "\n…（只显示前 60 条）", {}
        return True, "\n".join(matches) or "没有匹配", {}

    def _guard(self, rel: str) -> str | None:
        if is_read_only(rel, self.read_only):
            return f"拒绝写入只读路径 {rel}：规格和测试由维护者负责，只能修改实现代码"
        if self.writable and not matches_any(rel, self.writable):
            return f"拒绝写入 {rel}：只能修改实现代码（{', '.join(self.writable)}）"
        return None

    def tool_edit_file(self, path: str, old_text: str, new_text: str) -> tuple[bool, str, dict]:
        target, rel = self._resolve(path)
        if message := self._guard(rel):
            return False, message, {"rejected": "read_only"}
        if not target.is_file():
            return False, f"文件不存在：{rel}", {}
        text = target.read_text(encoding="utf-8")
        count = text.count(old_text)
        if count != 1:
            hint = "没有找到 old_text（注意缩进和换行需要逐字一致，可以先 read_file 确认）" if count == 0 else f"old_text 出现了 {count} 次，请多带几行上下文"
            return False, f"修改 {rel} 失败：{hint}", {}
        before_sha = sha_text(text)
        new = text.replace(old_text, new_text, 1)
        target.write_text(new, encoding="utf-8")
        line = text[: text.index(old_text)].count("\n") + 1
        return True, f"已修改 {rel}（从第 {line} 行开始，替换 {old_text.count(chr(10)) + 1} 行为 {new_text.count(chr(10)) + 1} 行）", {
            "path": rel,
            "before_sha": before_sha,
            "after_sha": sha_text(new),
        }

    def tool_write_file(self, path: str, content: str) -> tuple[bool, str, dict]:
        target, rel = self._resolve(path)
        if message := self._guard(rel):
            return False, message, {"rejected": "read_only"}
        before = target.read_text(encoding="utf-8") if target.is_file() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True, f"已写入 {rel}（{content.count(chr(10)) + 1} 行）", {
            "path": rel,
            "before_sha": sha_text(before) if before is not None else None,
            "after_sha": sha_text(content),
        }

    def tool_run_tests(self, suite: str) -> tuple[bool, str, dict]:
        if suite not in {"target", "regression", "all"}:
            return False, "suite 只能是 target、regression 或 all", {}
        run = self.test_runner(suite)
        failures = _failure_excerpt(Path(run.log_path)) if run.failed or run.errors else ""
        text = f"{suite} 测试：{run.summary()}"
        if run.failed_tests:
            text += "\n失败的测试：\n" + "\n".join(f"- {t}" for t in run.failed_tests[:40])
        if failures:
            text += "\n\n失败详情（节选）：\n" + failures
        return True, text, {"suite": suite, "passed": run.passed, "failed": run.failed, "errors": run.errors, "exit_code": run.exit_code, "log": run.log_path}

    def tool_finish(self, summary: str) -> tuple[bool, str, dict]:
        return True, "已记录完成说明。", {"summary": summary}


def _failure_excerpt(log: Path, limit: int = 6000) -> str:
    try:
        text = log.read_text(encoding="utf-8") if log.is_absolute() else ""
    except OSError:
        return ""
    start = text.find("= FAILURES =")
    excerpt = text[start:] if start >= 0 else text[-limit:]
    return excerpt[:limit]


def _record_content(blocks: list[dict]) -> list[dict]:
    """开发记录里保留文本、工具调用和思考摘要；思考块的签名不保存。"""
    out = []
    for block in blocks:
        if block.get("type") == "thinking":
            thinking = block.get("thinking", "")
            out.append({"type": "thinking", "thinking": thinking[:4000] + ("…" if len(thinking) > 4000 else "")})
        else:
            out.append(block)
    return out


def build_prompt(task, context_md: str, target_tests: list[str]) -> str:
    keep = "\n".join(f"- {k}" for k in task.keep) or "- （见上下文）"
    return "\n".join(
        [
            f"# 开发任务 {task.id}：{task.title}",
            "",
            task.description,
            "",
            "必须保持的原有行为：",
            keep,
            "",
            "工具里的路径都相对工程根目录（例如 library/catalog.py）。目标测试：",
            *[f"- {t}" for t in target_tests],
            "",
            "下面是上下文模块为本任务生成的上下文。",
            "",
            "---",
            "",
            context_md,
        ]
    )


def run_agent(*, client: MiniMaxClient, task, context_md: str, baseline: Path, workspace: Workspace,
              target_tests: list[str], session_path: Path, meta: dict, max_turns: int = 40,
              max_seconds: int = 1800, on_turn=None) -> AgentResult:  # fmt: skip
    prompt = build_prompt(task, context_md, target_tests)
    session = {
        "schema": "sddctx.minimax-session.v1",
        "task": task.to_dict(),
        "assistant": "sddctx MiniMax 开发助手（Anthropic 兼容 Messages API + 工具调用）",
        "model": client.model,
        "endpoint": client.url,
        "started_at": now_iso(),
        **meta,
        "context_sha256": sha_text(context_md),
        "system": SYSTEM_PROMPT,
        "tools": TOOLS,
        "initial_user_message": prompt,
        "turns": [],
    }
    messages: list[dict] = [{"role": "user", "content": prompt}]
    usage_total: dict[str, int] = {}
    status, summary = "stopped", ""
    last_tests: dict = {}
    started = time.monotonic()
    turn = 0
    while turn < max_turns and time.monotonic() - started < max_seconds:
        turn += 1
        response, seconds, attempts = client.create(system=SYSTEM_PROMPT, messages=messages, tools=TOOLS)
        content = response.get("content", [])
        messages.append({"role": "assistant", "content": content})
        for key, value in (response.get("usage") or {}).items():
            if isinstance(value, int):
                usage_total[key] = usage_total.get(key, 0) + value
        record = {
            "turn": turn,
            "at": now_iso(),
            "seconds": seconds,
            "attempts": attempts,
            "response_id": response.get("id"),
            "model": response.get("model"),
            "stop_reason": response.get("stop_reason"),
            "usage": response.get("usage"),
            "assistant": _record_content(content),
            "tool_results": [],
        }
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        results = []
        finished = False
        for use in tool_uses:
            ok, output, meta = workspace.execute(use["name"], use.get("input") or {})
            if len(output) > MAX_TOOL_OUTPUT:
                output = output[:MAX_TOOL_OUTPUT] + "\n…（输出过长已截断）"
            results.append({"type": "tool_result", "tool_use_id": use["id"], "content": output, "is_error": not ok})
            record["tool_results"].append(
                {"tool_use_id": use["id"], "name": use["name"], "input": use.get("input"), "ok": ok, "output": output, "meta": meta}
            )
            if use["name"] == "run_tests" and ok:
                last_tests[meta["suite"]] = meta
            if use["name"] == "finish":
                finished, summary = True, (use.get("input") or {}).get("summary", "")
        session["turns"].append(record)
        write_json(session_path, session)
        if on_turn:
            on_turn(record)
        if finished:
            status = "finished"
            break
        if not tool_uses:
            status = "finished" if response.get("stop_reason") == "end_turn" else "stopped"
            summary = "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            break
        messages.append({"role": "user", "content": results})

    diff = diff_trees(baseline, workspace.root)
    changed = sorted(set(re.findall(r"^diff --git a/(\S+) b/", diff, re.M)))
    violations = [path for path in changed if is_read_only(path, workspace.read_only)]
    edits = sum(1 for t in session["turns"] for r in t["tool_results"] if r["name"] in WRITE_TOOLS and r["ok"])
    session.update(
        {
            "finished_at": now_iso(),
            "status": status,
            "turn_count": turn,
            "final_summary": summary,
            "usage_total": usage_total,
            "successful_edits": edits,
            "changed_files": changed,
            "read_only_violations": violations,
            "final_diff": diff,
            "final_diff_sha256": sha_text(diff),
            "last_self_tests": last_tests,
        }
    )
    write_json(session_path, session)
    return AgentResult(
        status=status,
        summary=summary,
        turns=turn,
        session_path=session_path,
        diff=diff,
        diff_sha=sha_text(diff),
        changed_files=changed,
        edits=edits,
        read_only_violations=violations,
        usage=usage_total,
        last_tests=last_tests,
    )


def replay_session(session: dict, workspace: Workspace) -> list[dict]:
    """按顺序重放记录中成功的 edit_file / write_file 调用，返回重放日志。"""
    log = []
    for turn in session.get("turns", []):
        for result in turn.get("tool_results", []):
            if result["name"] not in WRITE_TOOLS or not result["ok"]:
                continue
            ok, output, meta = workspace.execute(result["name"], result["input"])
            expected = (result.get("meta") or {}).get("after_sha")
            log.append(
                {
                    "turn": turn["turn"],
                    "tool": result["name"],
                    "path": (result["input"] or {}).get("path"),
                    "ok": ok,
                    "after_sha_matches": ok and expected == meta.get("after_sha"),
                    "output": output,
                }
            )
            if not ok:
                raise RuntimeError(f"重放第 {turn['turn']} 轮的 {result['name']} 失败：{output}")
    return log
