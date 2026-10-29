#!/usr/bin/env python3
"""Render a Qoder CLI `-o stream-json` transcript into readable Markdown.

Usage: python3 render_transcript.py sessions/01-plan.jsonl [prompts/01-plan.md] > transcripts/01-plan.md

The raw .jsonl files in sessions/ are the authoritative, complete record. This renderer only
reformats them: it keeps every assistant message, tool call and tool result, and shortens long
tool outputs (the full text stays in the .jsonl).
"""
import json
import sys
from pathlib import Path

MAX_RESULT_LINES = 40


def fence(text: str, lang: str = "") -> str:
    ticks = "````" if "```" in text else "```"
    return f"{ticks}{lang}\n{text.rstrip()}\n{ticks}"


def shorten(text: str, limit: int = MAX_RESULT_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    return "\n".join(lines[:limit]) + f"\n… （共 {len(lines)} 行，此处省略 {len(lines) - limit} 行，完整内容见 .jsonl）"


def tool_input_summary(name: str, data: dict) -> str:
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        path = data.get("file_path", "")
        extra = ""
        if name == "Write":
            extra = f"（写入 {len(data.get('content', ''))} 字符）"
        elif name == "Edit":
            extra = f"（替换 {len(data.get('old_string', ''))} → {len(data.get('new_string', ''))} 字符）"
        return f"`{path}`{extra}"
    if name == "Bash":
        return fence(data.get("command", ""), "bash")
    return fence(json.dumps(data, ensure_ascii=False, indent=1)[:1500], "json")


def result_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for item in content or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
        elif isinstance(item, dict):
            parts.append(f"[{item.get('type')}]")
    return "\n".join(parts)


def render(jsonl: Path, prompt: Path | None) -> str:
    events = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    stem = jsonl.with_suffix("")
    started = Path(f"{stem}.started")
    finished = Path(f"{stem}.finished")
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    credits = sum(
        float((e.get("message", {}).get("usage") or {}).get("credits") or 0)
        for e in events
        if e.get("type") == "assistant"
    )
    out = [f"# Qoder 会话记录：{jsonl.stem}", ""]
    out += [
        "| 项目 | 值 |",
        "| --- | --- |",
        f"| 会话 ID | `{init.get('session_id', '')}` |",
        f"| Qoder CLI | {init.get('qodercli_version', '')}，模型 {init.get('model', '')}，权限模式 {init.get('permissionMode', '')} |",
        f"| 工作目录 | `{init.get('cwd', '')}` |",
        f"| 开始 / 结束 | {started.read_text().strip() if started.exists() else '?'} / {finished.read_text().strip() if finished.exists() else '?'} |",
        f"| 轮数 / 耗时 | {result.get('num_turns', '?')} 轮 / {round((result.get('duration_ms') or 0) / 60000, 1)} 分钟 |",
        f"| Credits | {result.get('total_credits', round(credits, 2))}（逐条请求累加 {round(credits, 2)}） |",
        f"| 原始记录 | `sessions/{jsonl.name}`（完整 stream-json） |",
        "",
    ]
    if prompt and prompt.exists():
        out += ["## 产品负责人的指令", "", prompt.read_text(encoding="utf-8").strip(), ""]
    out += ["## 对话过程", ""]
    for e in events:
        kind = e.get("type")
        if kind == "assistant":
            for block in e.get("message", {}).get("content", []) or []:
                btype = block.get("type")
                if btype == "text" and block.get("text", "").strip():
                    out += [f"**Qoder：** {block['text'].strip()}", ""]
                elif btype == "thinking" and block.get("thinking", "").strip():
                    out += ["<details><summary>Qoder 思考</summary>", "", block["thinking"].strip(), "", "</details>", ""]
                elif btype == "tool_use":
                    out += [f"🔧 **{block.get('name')}** {tool_input_summary(block.get('name', ''), block.get('input') or {})}", ""]
        elif kind == "user":
            content = e.get("message", {}).get("content")
            if isinstance(content, str):
                out += [f"**指令：** {content}", ""]
                continue
            for block in content or []:
                if block.get("type") == "tool_result":
                    text = shorten(result_text(block.get("content")))
                    label = "结果（出错）" if block.get("is_error") else "结果"
                    out += [f"<details><summary>{label}</summary>", "", fence(text), "", "</details>", ""]
                elif block.get("type") == "text":
                    out += [f"**指令：** {block.get('text', '')}", ""]
        elif kind == "result":
            out += ["## 会话结果", "", str(e.get("result") or "").strip(), ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    src = Path(sys.argv[1])
    prompt_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    sys.stdout.write(render(src, prompt_path))
