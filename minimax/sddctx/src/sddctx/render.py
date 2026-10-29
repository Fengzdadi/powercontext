"""把上下文、状态等结构化结果渲染成 Markdown（给评审阅读，也作为 MiniMax 开发助手的输入）。"""

from __future__ import annotations

import difflib
import json
import re

ROLE_TITLES = {
    "target": "1.1 本次要实现的条目",
    "constraint": "1.2 必须遵守的约束（被目标条目引用或被任务检索命中）",
    "sibling": "1.3 同一接口的已实现条目（行为必须保持，属于回归范围）",
}


def _loc(item: dict) -> str:
    return f"{item['path']}:{item['start_line']}-{item['end_line']}"


def _fence(text: str, lang: str = "") -> str:
    longest = max((len(run) for run in re.findall(r"`{3,}", text)), default=2)
    fence = "`" * (longest + 1)
    return f"{fence}{lang}\n{text}\n{fence}"


def render_context(ctx: dict) -> str:
    task = ctx["task"]
    run = ctx["import_run"]
    check = ctx["source_verification"]
    out = [
        f"# 任务上下文：{task['id']} {task['title']}",
        "",
        f"> 工程 `{ctx['project']}`；资料来自 seekdb 导入批次 #{run['run_id']}（{run['total']} 个片段，"
        f"工程目录指纹 `{run['tree_sha'][:12]}`，代码版本 `{run['code_version']}`）。"
        f"引用的来源 {check['checked']} 处，逐行核对一致 {check['ok']} 处。",
        "",
        "## 0. 任务",
        "",
        task["description"],
        "",
    ]
    if task["keep"]:
        out += ["必须保持的原有行为：", ""] + [f"- {k}" for k in task["keep"]] + [""]
    if check["problems"]:
        out += ["**来源核对发现问题：**", ""] + [f"- {p}" for p in check["problems"]] + [""]

    out += ["## 1. 适用规格", ""]
    for role in ("target", "constraint", "sibling"):
        items = ctx["specs"][role]
        if not items:
            continue
        out += [f"### {ROLE_TITLES[role]}", ""]
        for spec in items:
            why = "；".join(spec["reasons"])
            if role == "sibling":
                out.append(f"- **{spec['title']}**（{spec['status']}）— `{_loc(spec)}`，修订 r{spec['revision']}。{why}")
                continue
            out += [
                f"#### {spec['title']}（{spec['status']}）",
                "",
                f"来源 `{_loc(spec)}`，修订 r{spec['revision']}，内容 sha256 `{spec['content_sha'][:12]}`。选择依据：{why}。",
                "",
                _fence(spec["content"], "markdown"),
                "",
            ]
        if role == "sibling":
            out.append("")

    code = ctx["code"]
    out += ["## 2. 代码", "", "### 2.1 需要修改的符号", ""]
    for item in code["to_change"]:
        out += [
            f"#### `{item['path']}::{item['symbol']}`（第 {item['start_line']}-{item['end_line']} 行）",
            "",
            f"选择依据：{'；'.join(item['reasons'])}。",
            "",
            _fence(item["content"], "python"),
            "",
        ]
    if code["related"]:
        out += ["### 2.2 相关代码（可复用，通常不需要修改）", ""]
        for item in code["related"]:
            out.append(f"- `{item['path']}::{item['symbol']}`（第 {item['start_line']}-{item['end_line']} 行）`{item['signature']}` — {'；'.join(item['reasons'])}")
        out.append("")

    tests = ctx["tests"]
    target_ids = sorted({v for t in tests["target"] for v in t["verifies"]} & {s["id"] for s in ctx["specs"]["target"]})
    out += [
        "## 3. 测试",
        "",
        f"### 3.1 目标测试（验证 {', '.join(target_ids)}；修改前应因功能未实现而失败，修改后必须全部通过）",
        "",
    ]
    for t in tests["target"]:
        out.append(f"- `{t['node_id']}`（第 {t['start_line']}-{t['end_line']} 行）验证 {', '.join(t['verifies'])}")
    out += ["", f"运行：`{tests['commands']['target']}`", ""]
    for t in tests["target"]:
        out += [_fence(t["content"], "python"), ""]
    by_file: dict[str, list[dict]] = {}
    for t in tests["regression"]:
        by_file.setdefault(t["path"], []).append(t)
    out += ["### 3.2 相关回归测试（必须保持通过）", ""]
    for path, items in by_file.items():
        specs = sorted({v for t in items for v in t["verifies"]})
        out.append(f"- `{path}`：{len(items)} 个测试函数，验证 {', '.join(specs)}")
    out += [
        "",
        f"相关回归：`{tests['commands']['related_regression']}`；完整回归（全部非目标测试）：`python -m pytest -q` 并排除目标测试。",
        "",
    ]

    out += ["## 4. 任务状态（PowerContext）", ""]
    out += render_state_lines(ctx["state"])
    if ctx["conventions"]:
        out += ["## 5. 工程约定", ""]
        for doc in ctx["conventions"]:
            out += [f"来源 `{_loc(doc)}`：", "", _fence(doc["content"], "markdown"), ""]

    out += ["## 附：seekdb 检索结果", "", "| 检索 | 片段 | RRF | 全文名次 | 向量名次 |", "|---|---|---|---|---|"]
    for label, key in (("规格", "spec_hits"), ("代码", "code_hits")):
        for hit in ctx["retrieval"][key]:
            out.append(f"| {label} | `{hit['chunk_id']}` | {hit['score']} | {hit['keyword_rank'] or '-'} | {hit['semantic_rank'] or '-'} |")
    out.append("")
    return "\n".join(out)


def render_state_lines(state: dict) -> list[str]:
    if not state.get("available"):
        return [f"- {state.get('note', '未读取')}", ""]
    out = [f"- Scope：`{state['scope_title']}`（{state['scope_id'] or '尚未创建'}），已有记录 {state['records']} 条"]
    if state["empty"]:
        out.append("- PowerContext 中还没有该任务的记录：从空状态开始。")
    else:
        out.append(f"- 最近一次记录：{state['latest_status']} — {state['latest_summary']}")
        out.append("- 已完成：")
        out += [f"  - {d}" for d in state["done"]] or ["  - （无）"]
        out.append("- 已有验证结果：")
        out += [f"  - {c['name']}：**{c['status']}** — {c.get('details') or ''}" for c in state["checks"]] or ["  - （无）"]
    if state["spec_changes"]:
        out.append("- **规格变更**：" + "、".join(state["spec_changes"]) + " 自上次记录后内容已变化（对比 PowerContext 中保存的规格指纹）。")
    out.append("- 待办：")
    out += [f"  - {t}" for t in state["todo"]] or ["  - 无，任务已完成且验证通过。"]
    out.append(f"- 下一步：{state['next_step'] or '无'}")
    out.append("")
    return out


def render_state(state: dict) -> str:
    out = [f"# 任务状态：{state['task_id']}（工程 {state['project']}）", ""]
    out.append(f"- PowerContext Scope：`{state['scope_title']}` → {state['scope_id'] or '不存在'}")
    out.append(f"- 记录数：{state['records']}")
    if state["empty"]:
        out += ["", "PowerContext 中没有这个任务的记录（空状态）。", ""]
        return "\n".join(out)
    latest = state["latest_outcome"]
    if latest:
        out += [
            f"- 最新记录：#{latest['position']} `{latest['source_id']}`，状态 **{latest['status']}**",
            f"- 摘要：{latest['summary']}",
            "",
            "## 已完成",
            "",
        ]
        out += [f"- {d}" for d in latest["done"]] + ["", "## 验证结果", ""]
        out += [f"- {c['name']}：**{c['status']}** — {c.get('details') or ''}" for c in latest["checks"]] + ["", "## 待办", ""]
        out += [f"- {t}" for t in latest["todo"]] or ["- 无"]
        out.append("")
    if state["contract"]:
        c = state["contract"]
        out += ["## Work Contract", "", f"- 目标：{' '.join(c['objective'].split())}", "- 修改范围："]
        out += [f"  - {s}" for s in c["in_scope"]]
        out.append("- 完成标准：")
        out += [f"  - {s}" for s in c["completion_criteria"]]
        out.append("")
    out += ["## 记录历史（PowerContext Sources，按日志位置）", "", "| 位置 | source_id | 步骤 | 状态 | 摘要 |", "|---|---|---|---|---|"]
    out += [f"| {h['position']} | `{h['source_id']}` | {h['step']} | {h['status']} | {h['summary']} |" for h in state["history"]]
    out.append("")
    return "\n".join(out)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f"…（共 {len(text)} 字符）"


def _tool_call(name: str, args: dict) -> list[str]:
    if name == "edit_file":
        old = (args.get("old_text") or "").splitlines()
        new = (args.get("new_text") or "").splitlines()
        body = "\n".join(difflib.unified_diff(old, new, "old_text", "new_text", lineterm="", n=2))
        return [f"- 调用 `edit_file`：`{args.get('path')}`", "", _fence(body, "diff"), ""]
    if name == "write_file":
        return [f"- 调用 `write_file`：`{args.get('path')}`", "", _fence(_clip(args.get("content") or "", 3000), "python"), ""]
    if name == "finish":
        return [f"- 调用 `finish`：{args.get('summary', '')}", ""]
    shown = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())
    return [f"- 调用 `{name}`（{shown}）"]


def render_session(session: dict) -> str:
    """MiniMax 开发记录（session.json）的可读版本：任务、上下文、每一轮的思考摘要、工具调用和结果、最终差异。"""
    task = session["task"]
    usage = session.get("usage_total") or {}
    out = [
        f"# MiniMax 开发记录：{task['id']} {task['title']}",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        f"| 助手 | {session.get('assistant')} |",
        f"| 模型 / 接口 | `{session.get('model')}` / `{session.get('endpoint')}` |",
        f"| 开始 / 结束 | {session.get('started_at')} / {session.get('finished_at')} |",
        f"| 结果 | {session.get('status')}，{session.get('turn_count')} 轮，成功修改 {session.get('successful_edits')} 次 |",
        f"| Token 用量 | 输入 {usage.get('input_tokens', '-')}（另有缓存命中 {usage.get('cache_read_input_tokens', 0)}），输出 {usage.get('output_tokens', '-')} |",
        f"| 修改的文件 | {', '.join(f'`{p}`' for p in session.get('changed_files', [])) or '无'} |",
        f"| 最终差异 sha256 | `{session.get('final_diff_sha256')}` |",
        f"| 代码版本 | `{session.get('code_version')}` |",
        "",
        "## 任务与上下文",
        "",
        f"任务：{task['description']}",
        "",
        f"提供给 MiniMax 的上下文：`{session.get('context_path')}`（sha256 `{session.get('context_sha256', '')[:12]}`），"
        f"由 seekdb 检索结果和 PowerContext 任务状态生成（PowerContext 记录 `{session.get('powercontext_state')}`）。"
        "首条用户消息（任务说明 + 完整上下文）见文末附录。",
        "",
        "## 修改过程",
        "",
    ]
    for turn in session.get("turns", []):
        u = turn.get("usage") or {}
        out += [
            f"### 第 {turn['turn']} 轮",
            "",
            f"响应 `{turn.get('response_id')}`，模型 `{turn.get('model')}`，{turn.get('seconds')}s，stop_reason `{turn.get('stop_reason')}`，"
            f"输入 {u.get('input_tokens', '-')} / 输出 {u.get('output_tokens', '-')} tokens。",
            "",
        ]
        for block in turn.get("assistant", []):
            if block.get("type") == "thinking" and block.get("thinking", "").strip():
                out += ["> 思考摘要：" + _clip(block["thinking"], 400).replace("\n", " "), ""]
            elif block.get("type") == "text" and block.get("text", "").strip():
                out += [block["text"].strip(), ""]
            elif block.get("type") == "tool_use":
                out += _tool_call(block.get("name", ""), block.get("input") or {})
        for result in turn.get("tool_results", []):
            if result["name"] == "finish":
                continue
            flag = "成功" if result["ok"] else "失败"
            out += [f"  - `{result['name']}` 结果（{flag}）：", "", _fence(_clip(result.get("output", ""), 1200)), ""]
    out += [
        "## 最终结果",
        "",
        f"MiniMax 的完成说明：{session.get('final_summary') or '（无）'}",
        "",
        "助手最后一次自测："
        + ("；".join(f"{k} {v.get('passed')} passed / {v.get('failed')} failed" for k, v in (session.get("last_self_tests") or {}).items()) or "无"),
        "",
        "最终代码差异（相对修改前的工程）：",
        "",
        _fence(session.get("final_diff") or "", "diff"),
        "",
        "## 附录：发给 MiniMax 的首条消息",
        "",
        "<details><summary>展开（任务说明 + 上下文模块输出）</summary>",
        "",
        _fence(session.get("initial_user_message", ""), "markdown"),
        "",
        "</details>",
        "",
    ]
    return "\n".join(out)
