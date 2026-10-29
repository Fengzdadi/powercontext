"""sddctx 命令行入口。

  sddctx import                          把 project/ 的规格、代码、测试导入 seekdb（增量，按内容指纹判断变化）
  sddctx context T-101                   生成任务上下文（Markdown 输出到终端，同时写 runs/T-101/context.md|json）
  sddctx run T-101 [--stop-after STEP]   按 PowerContext 中的进度执行剩余步骤：context → verify-before → develop → verify-after
  sddctx verify T-101 --phase before     单独执行修改前 / 修改后验证
  sddctx develop T-101 [--replay FILE]   把上下文交给 MiniMax 完成代码修改（或回放已有的开发记录）
  sddctx state T-101                     读取 PowerContext 中保存的任务状态
  sddctx check-context T-101             按 samples/T-101/expected.json 核对上下文必须包含的来源
  sddctx check-record T-101              核对 MiniMax 开发记录与代码差异是否对应
  sddctx spec-update-demo T-101          修改规格并重新导入，确认上下文使用新内容，然后恢复
  sddctx search "关键词" / db-inspect / info
"""

from __future__ import annotations

import argparse
import platform
import sys
from importlib import metadata
from pathlib import Path

import pymysql

from . import __version__
from .context import load_task
from .minimax import MiniMaxError
from .pipeline import (
    Runtime,
    StepError,
    do_check_context,
    do_check_record,
    do_context,
    do_develop,
    do_import,
    do_run,
    do_spec_update_demo,
    do_verify,
    say,
)
from .records import dumps
from .render import render_state
from .settings import Settings
from .state import STEPS, PowerContextError, todo_for


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sddctx", description="SDD 上下文模块：seekdb 检索工程资料，PowerContext 保存任务状态，MiniMax 完成代码修改")
    parser.add_argument("--version", action="version", version=f"sddctx {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("import", help="导入规格、代码和测试到 seekdb")

    p = sub.add_parser("context", help="生成任务上下文")
    p.add_argument("task", help="任务 ID（samples/<ID>/task.toml）或 task.toml 路径")
    p.add_argument("--json", action="store_true", help="输出 JSON 而不是 Markdown")
    p.add_argument("--quiet", action="store_true", help="只输出摘要，不打印完整上下文")
    p.add_argument("--no-record", action="store_true", help="只读：即使 PowerContext 中没有记录也不写入")

    p = sub.add_parser("run", help="按 PowerContext 中的进度执行剩余步骤")
    p.add_argument("task")
    p.add_argument("--stop-after", choices=STEPS, help="完成这一步后停止（用于演示重启后续跑）")
    p.add_argument("--replay", type=Path, help="develop 步骤回放这个 MiniMax 开发记录，而不是实时调用 MiniMax")
    p.add_argument("--model", help="MiniMax 模型（默认取 MINIMAX_MODEL）")
    p.add_argument("--max-turns", type=int, default=40)

    p = sub.add_parser("verify", help="修改前 / 修改后验证")
    p.add_argument("task")
    p.add_argument("--phase", choices=["before", "after"], required=True)

    p = sub.add_parser("develop", help="让 MiniMax 开发助手完成代码修改")
    p.add_argument("task")
    p.add_argument("--replay", type=Path, help="回放 MiniMax 开发记录（session.json）中的修改调用")
    p.add_argument("--force", action="store_true", help="即使 PowerContext 记录已完成也重新修改")
    p.add_argument("--model")
    p.add_argument("--max-turns", type=int, default=40)

    p = sub.add_parser("state", help="读取 PowerContext 中的任务状态")
    p.add_argument("task", help="任务 ID")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("check-context", help="核对上下文是否包含样例规定的来源")
    p.add_argument("task")

    p = sub.add_parser("check-record", help="核对 MiniMax 开发记录与代码差异")
    p.add_argument("task", help="任务 ID")
    p.add_argument("--session", type=Path, help="开发记录 session.json（默认取 PowerContext 中记录的位置）")
    p.add_argument("--patch", type=Path, help="要核对的代码差异（默认 runs/<任务>/change.patch）")

    p = sub.add_parser("spec-update-demo", help="修改规格→重新导入→确认上下文使用新内容→恢复")
    p.add_argument("task")

    p = sub.add_parser("search", help="在 seekdb 中做一次混合检索")
    p.add_argument("text")
    p.add_argument("--kind", default="spec,code,test", help="片段类型，逗号分隔：spec,doc,code,test,testmod")
    p.add_argument("--size", type=int, default=10)

    sub.add_parser("db-inspect", help="查看 seekdb 中保存的工程资料和索引")
    sub.add_parser("info", help="显示组件版本和连接配置")
    return parser


def _path(settings: Settings, value: Path | None) -> Path | None:
    if value is None:
        return None
    return value if value.is_absolute() else (settings.home / value).resolve()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.load()
    task_ref = getattr(args, "task", "")
    task_id = Path(task_ref).parent.name if task_ref.endswith(".toml") else task_ref
    rt = Runtime(settings, args.command, task_id)
    try:
        return _dispatch(rt, args)
    except (StepError, PowerContextError, MiniMaxError, FileNotFoundError, RuntimeError) as exc:
        say(f"错误：{exc}")
        return 1
    except pymysql.err.Error as exc:
        say(f"错误：seekdb（{settings.seekdb_host}:{settings.seekdb_port}）访问失败：{exc}")
        return 1


def _dispatch(rt: Runtime, args: argparse.Namespace) -> int:
    s = rt.settings
    if args.command == "import":
        do_import(rt)
        return 0
    if args.command == "context":
        task = load_task(s, args.task)
        ctx, md, path = do_context(rt, task, record=not args.no_record)
        if args.json:
            print(dumps(ctx, indent=2))
        elif not args.quiet:
            print(md)
        specs = ", ".join(x["id"] for x in ctx["specs"]["target"])
        code = ", ".join(f"{c['path']}::{c['symbol']}" for c in ctx["code"]["to_change"])
        say(f"上下文已保存：{rt.rel(path)}（以及 .json）；目标规格 {specs}；需要修改 {code}；目标测试函数 {len(ctx['tests']['target'])} 个")
        return 0
    if args.command == "run":
        task = load_task(s, args.task)
        return 0 if do_run(rt, task, stop_after=args.stop_after, replay=_path(s, args.replay), model=args.model, max_turns=args.max_turns) else 1
    if args.command == "verify":
        return 0 if do_verify(rt, load_task(s, args.task), args.phase) else 1
    if args.command == "develop":
        task = load_task(s, args.task)
        ok = do_develop(rt, task, replay=_path(s, args.replay), force=args.force, model=args.model, max_turns=args.max_turns)
        return 0 if ok else 1
    if args.command == "state":
        state = rt.state(args.task)
        data = state.to_dict()
        if args.json:
            print(dumps(data, indent=2))
            return 0
        print(render_state(data))
        if not state.empty:
            say("下一步：" + (next((step for step in STEPS if step not in state.steps_done), None) or "无，任务已完成"))
            remaining = todo_for(state.steps_done)
            if remaining:
                say("按步骤计算的待办：" + "；".join(remaining))
        return 0
    if args.command == "check-context":
        return 0 if do_check_context(rt, load_task(s, args.task)) else 1
    if args.command == "check-record":
        return 0 if do_check_record(rt, args.task, session_path=_path(s, args.session), patch_path=_path(s, args.patch)) else 1
    if args.command == "spec-update-demo":
        return 0 if do_spec_update_demo(rt, load_task(s, args.task)) else 1
    if args.command == "search":
        kinds = [k.strip() for k in args.kind.split(",") if k.strip()]
        hits = rt.store.hybrid_search(rt.project, kinds, args.text, size=args.size, purpose="search: command line")
        say(f"DBMS_HYBRID_SEARCH（IK 全文 + 向量，RRF）在 {kinds} 中检索“{args.text}”：{len(hits)} 条")
        say("| # | 片段 | RRF | 全文名次/分数 | 向量名次/分数 | 位置 |")
        say("|---|---|---|---|---|---|")
        for rank, h in enumerate(hits, 1):
            kw = f"{h.get('_keyword_rank') or '-'} / {round(h['_keyword_score'], 3) if h.get('_keyword_score') else '-'}"
            vec = f"{h.get('_semantic_rank') or '-'} / {round(h['_semantic_score'], 3) if h.get('_semantic_score') else '-'}"
            say(f"| {rank} | `{h['chunk_id']}` {h.get('title', '')[:40]} | {round(h.get('_score') or 0, 4)} | {kw} | {vec} | {h['path']}:{h['start_line']}-{h['end_line']} |")
        return 0
    if args.command == "db-inspect":
        return _db_inspect(rt)
    if args.command == "info":
        return _info(rt)
    raise AssertionError(args.command)


def _db_inspect(rt: Runtime) -> int:
    st = rt.store
    say(f"seekdb {st.version()}，数据库 `{rt.settings.seekdb_database}`，工程 `{rt.project}`")
    for row in st.q(
        "SELECT TABLE_NAME AS t, TABLE_ROWS AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME",
        (rt.settings.seekdb_database,),
        purpose="inspect: tables",
    ):
        say(f"  表 {row['t']}")
    say("片段（sdd_chunks）：")
    for row in st.counts(rt.project):
        say(f"  {row['kind']:<8} {row['n']:>4} 个，最大修订 r{row['max_revision']}")
    say("追溯关系（sdd_links）：")
    for row in st.q("SELECT rel, COUNT(*) AS n FROM sdd_links WHERE project = %s GROUP BY rel ORDER BY rel", (rt.project,), purpose="inspect: links"):
        say(f"  {row['rel']:<10} {row['n']:>4} 条")
    say("最近的导入批次（sdd_import_runs）：")
    for row in st.q(
        "SELECT run_id, LEFT(tree_sha, 12) AS tree, code_version, finished_at, added, updated, moved, removed, unchanged, total "
        "FROM sdd_import_runs WHERE project = %s ORDER BY run_id DESC LIMIT 5",
        (rt.project,),
        purpose="inspect: import runs",
    ):
        say(
            f"  #{row['run_id']} {row['finished_at']} 指纹 {row['tree']} 代码版本 {row['code_version']}：新增 {row['added']} 更新 {row['updated']} "
            f"移动 {row['moved']} 删除 {row['removed']} 未变 {row['unchanged']}，共 {row['total']}"
        )
    say("规格修订历史（sdd_chunk_revisions，修订号大于 1 的记录）：")
    rows = st.q(
        "SELECT chunk_id, revision, change_kind, LEFT(content_sha, 12) AS sha, import_run, created_at FROM sdd_chunk_revisions "
        "WHERE project = %s AND revision > 1 ORDER BY created_at DESC LIMIT 10",
        (rt.project,),
        purpose="inspect: revisions",
    )
    for row in rows:
        say(f"  {row['chunk_id']} r{row['revision']} {row['change_kind']} sha {row['sha']} 导入批次 #{row['import_run']} {row['created_at']}")
    if not rows:
        say("  （没有）")
    say("sdd_chunks 上的索引：")
    seen = set()
    for row in st.q("SHOW INDEX FROM sdd_chunks", purpose="inspect: indexes"):
        name = row.get("Key_name")
        if name in seen:
            continue
        seen.add(name)
        say(f"  {name}（{row.get('Index_type')}）列 {row.get('Column_name')}")
    return 0


def _info(rt: Runtime) -> int:
    s = rt.settings
    say(f"sddctx {__version__}，Python {platform.python_version()}，PyMySQL {metadata.version('PyMySQL')}，pytest {metadata.version('pytest')}")
    say(f"工程目录 {rt.rel(s.project_dir)}（{rt.project}），运行产物 {rt.rel(s.runs_dir)}，代码版本 {s.code_version}")
    try:
        say(f"seekdb {s.seekdb_host}:{s.seekdb_port}/{s.seekdb_database}：{rt.store.version()}")
    except pymysql.err.Error as exc:
        say(f"seekdb {s.seekdb_host}:{s.seekdb_port}：无法连接（{exc}）")
    try:
        say(f"PowerContext {s.powercontext_url}：{rt.pc.version()}")
    except PowerContextError as exc:
        say(f"PowerContext {s.powercontext_url}：{exc}")
    say(f"MiniMax：{s.minimax_base_url}，模型 {s.minimax_model}，密钥{'已配置' if s.minimax_api_key else '未配置（只能用 --replay 回放开发记录）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
