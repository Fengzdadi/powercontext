"""流程编排：import → context → verify-before → develop → verify-after。

每一步开始前都从 PowerContext 读回任务状态（已完成的步骤、目标测试、验证结果），结束时写入一条 Task Outcome。
因此任何一步之后重启模块（或重启 PowerContext 容器），`run` 都会从记录里的下一步继续，`verify` 用的目标测试
也来自 PowerContext 中保存的上下文结论。

运行产物都在 runs/<任务>/ 下：
  context.md / context.json          最近一次生成的上下文
  snapshots/before/                  修改前的工程快照（verify-before 时从 project/ 复制）
  snapshots/after/                   MiniMax 的工作区，开发结束后即修改后的快照
  tests/before|after/                修改前后的目标测试、回归测试日志和 junit 报告
  develop/                           发给 MiniMax 的上下文、开发记录（session-*.json/.md）和助手自测日志
  change.patch                       修改前后快照的差异
"""

from __future__ import annotations

import itertools
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from . import ingest
from .agent import AgentResult, Workspace, replay_session, run_agent
from .context import ContextBuilder, Task
from .minimax import MiniMaxClient
from .records import Recorder, write_json, write_text
from .render import render_context, render_session
from .settings import Settings
from .state import STEPS, PowerContext, TaskState, load_state, todo_for, write_contract, write_outcome
from .store import Store
from .testrun import TestRun, run_pytest
from .workspace import copy_tree, diff_trees, matches_any, sha_text, tree_sha


MINIMAX_HOSTS = {"api.minimax.cn", "api.minimax.io"}


class StepError(RuntimeError):
    """某一步不能继续：缺少前置步骤、验证没有通过等。"""


def say(text: str = "") -> None:
    print(text, flush=True)


class Runtime:
    """一次命令调用的运行环境：配置、seekdb 连接、PowerContext 客户端和技术使用记录。"""

    def __init__(self, settings: Settings, command: str, task_id: str = "") -> None:
        self.settings = settings
        self.command = command
        self.task_id = task_id
        self.manifest = ingest.load_manifest(settings.project_dir)
        self.project = self.manifest["project"]["id"]
        self._store: Store | None = None
        self._pc: PowerContext | None = None

    def recorder(self, name: str) -> Recorder:
        return Recorder(self.settings.runs_dir / "records" / f"{name}.jsonl", command=self.command, task=self.task_id)

    @property
    def store(self) -> Store:
        if self._store is None:
            self._store = Store(self.settings, self.recorder("seekdb-queries"))
        return self._store

    @property
    def pc(self) -> PowerContext:
        if self._pc is None:
            self._pc = PowerContext(self.settings.powercontext_url, self.recorder("powercontext-calls"))
        return self._pc

    @property
    def read_only(self) -> list[str]:
        return list(self.manifest["rules"].get("read_only", []))

    @property
    def writable(self) -> list[str]:
        return list(self.manifest["rules"].get("writable") or self.manifest["sources"].get("code", []))

    def task_dir(self, task_id: str) -> Path:
        return self.settings.runs_dir / task_id

    def rel(self, path: Path | str) -> str:
        return self.settings.rel(Path(path))

    def state(self, task_id: str) -> TaskState:
        return load_state(self.pc, self.project, task_id)

    def run_tests(self, tree: Path, selection: list[str], *, label: str, out_dir: Path) -> TestRun:
        return run_pytest(tree, selection, label=label, out_dir=out_dir, code_version=self.settings.code_version, rel=self.rel)


def deselect(tests: list[str]) -> list[str]:
    return [arg for node in tests for arg in ("--deselect", node)]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _merge_checks(old: list[dict], new: list[dict]) -> list[dict]:
    names = {c["name"] for c in new}
    return [c for c in old if c["name"] not in names] + new


def _test_summary(run: TestRun) -> dict:
    return {
        "exit_code": run.exit_code,
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "errors": run.errors,
        "skipped": run.skipped,
        "assertion_failures": run.assertion_failures,
        "other_problems": run.other_problems[:10],
        "code_version": run.code_version,
        "tree_sha": run.tree_sha,
        "log": run.log_path,
    }


def _diff_stat(diff: str) -> tuple[int, int]:
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    return added, removed


def _progress(state: TaskState) -> tuple[list[str], list[dict], dict]:
    latest = state.latest
    if latest is None:
        return [], [], {}
    return list(latest.observations), list(latest.checks), dict(latest.machine)


# ------------------------------------------------------------------ import


def do_import(rt: Runtime) -> dict:
    project_dir = rt.settings.project_dir
    manifest, chunks = ingest.collect(project_dir)
    fingerprint = tree_sha(project_dir)
    report = rt.store.import_chunks(rt.project, rt.rel(project_dir), fingerprint, rt.settings.code_version, chunks)
    kinds = Counter(c.kind for c in chunks)
    s = rt.settings
    say(f"导入工程 {rt.project}（{manifest['project'].get('name', '')}）→ seekdb {s.seekdb_host}:{s.seekdb_port}/{s.seekdb_database}，导入批次 #{report.run_id}")
    say(
        f"  片段 {report.total} 个：规格条目 {kinds['spec']}、规格说明 {kinds['doc']}、代码 {kinds['code']}、"
        f"测试函数 {kinds['test']}、测试模块 {kinds['testmod']}；追溯关系 {report.links} 条"
    )
    say(
        f"  与上一批次相比：新增 {len(report.added)}、内容更新 {len(report.updated)}、位置移动 {len(report.moved)}、"
        f"删除 {len(report.removed)}、未变化 {report.unchanged}；耗时 {report.seconds}s"
    )
    changed = report.updated + report.moved
    if changed:
        rows = rt.store.chunks(rt.project, changed, purpose="import: show changed chunks")
        for cid in changed:
            row = rows.get(cid, {})
            kind = "更新" if cid in report.updated else "移动"
            say(f"  {kind} {cid} → 修订 r{row.get('revision')}（{row.get('path')}:{row.get('start_line')}-{row.get('end_line')}）")
    for cid in report.removed:
        say(f"  删除 {cid}")
    return {
        "run_id": report.run_id,
        "total": report.total,
        "added": report.added,
        "updated": report.updated,
        "moved": report.moved,
        "removed": report.removed,
        "unchanged": report.unchanged,
        "links": report.links,
        "tree_sha": fingerprint,
    }


# ------------------------------------------------------------------ context


def build_context(rt: Runtime, task: Task, state: TaskState | None) -> tuple[dict, str]:
    ctx = ContextBuilder(rt.store, rt.project, rt.settings.project_dir).build(task, state)
    return ctx, render_context(ctx)


def context_facts(ctx: dict) -> dict:
    specs, code, tests = ctx["specs"], ctx["code"], ctx["tests"]
    return {
        "target_specs": [s["id"] for s in specs["target"]],
        "constraint_specs": [s["id"] for s in specs["constraint"]],
        "sibling_specs": [s["id"] for s in specs["sibling"]],
        "spec_revisions": ctx["state"]["spec_revisions"],
        "to_change": [f"{c['path']}::{c['symbol']}" for c in code["to_change"]],
        "target_tests": [t["node_id"] for t in tests["target"]],
        "regression_files": sorted({t["path"] for t in tests["regression"]}),
        "import_run": ctx["import_run"]["run_id"],
    }


def _context_done(ctx: dict, md: str) -> str:
    f = context_facts(ctx)
    return (
        f"生成任务上下文（seekdb 导入批次 #{f['import_run']}，上下文 sha256 {sha_text(md)[:12]}）：目标规格 {', '.join(f['target_specs'])}；"
        f"约束 {', '.join(f['constraint_specs']) or '无'}；需要修改 {', '.join(f['to_change'])}；"
        f"目标测试 {len(f['target_tests'])} 个测试函数；相关回归测试文件 {len(f['regression_files'])} 个"
    )


def _source_check(ctx: dict) -> dict:
    v = ctx["source_verification"]
    return {
        "name": "上下文来源核对",
        "status": "passed" if not v["problems"] else "failed",
        "details": f"上下文引用的 {v['checked']} 处来源与工程文件逐行比对，一致 {v['ok']} 处" + (f"；问题：{'；'.join(v['problems'][:5])}" if v["problems"] else ""),
    }


def save_context(rt: Runtime, task: Task, ctx: dict, md: str, name: str = "context") -> Path:
    directory = rt.task_dir(task.id)
    write_json(directory / f"{name}.json", ctx)
    return write_text(directory / f"{name}.md", md)


def record_context(rt: Runtime, task: Task, state: TaskState, ctx: dict, md: str, *, note: str | None = None) -> None:
    """第一次生成上下文时写 Work Contract 和第一条 Task Outcome；规格变更后重新生成时只写 Outcome 并重置后续步骤。"""
    f = context_facts(ctx)
    objective = f"{task.id} {task.title}"
    if not state.contracts:
        targets = [f"{s['title']}（{s['status']}，{s['path']}:{s['start_line']}-{s['end_line']}，修订 r{s['revision']}）" for s in ctx["specs"]["target"]]
        write_contract(
            rt.pc,
            state,
            objective=f"{objective}：{task.description}",
            facts=[f"目标规格：{t}" for t in targets]
            + [f"必须遵守的约束：{', '.join(f['constraint_specs'])}", f"需要修改：{', '.join(f['to_change'])}"]
            + [f"目标测试：{len(f['target_tests'])} 个测试函数（{', '.join(ctx['tests']['target_files'])}）"]
            + [f"必须保持：{k}" for k in task.keep],
            in_scope=[f"修改 {x}" for x in f["to_change"]] + [f"只允许修改实现代码：{', '.join(rt.writable)}"],
            exclusions=[f"不修改只读路径 {p}" for p in rt.read_only] + ["不删除断言、不跳过测试、不修改测试预期"],
            criteria=[
                "修改前：目标测试因功能未实现而失败（断言失败，不是导入错误、夹具错误等环境问题），回归测试全部通过",
                "修改后：同一组目标测试全部通过",
                "修改后：回归测试（全部非目标测试）全部通过，规格和测试文件没有被修改",
            ],
            notes=[
                f"代码修改由 MiniMax 开发助手完成（{rt.settings.minimax_model}，{rt.settings.minimax_base_url}）；"
                "sddctx 只负责提供上下文、执行助手发起的工具调用和运行测试"
            ],
        )
    done, checks, _ = _progress(state)
    if note:
        done.append(note)
    done.append(_context_done(ctx, md))
    write_outcome(
        rt.pc,
        state,
        step="context",
        status="partial",
        summary=f"已生成任务上下文：目标 {', '.join(f['target_specs'])}；需要修改 {', '.join(f['to_change'])}；目标测试 {len(f['target_tests'])} 个",
        objective=objective,
        done=done,
        checks=_merge_checks(checks, [_source_check(ctx)]),
        todo=todo_for(["context"]),
        machine={"steps_done": ["context"], **f, "context_sha256": sha_text(md)},
    )


def do_context(rt: Runtime, task: Task, *, record: bool = True) -> tuple[dict, str, Path]:
    state = rt.state(task.id)
    ctx, md = build_context(rt, task, state)
    if record and state.empty:
        record_context(rt, task, state, ctx, md)
        # 状态段改为写入之后的内容，保证输出与 PowerContext 一致
        ctx["state"] = ContextBuilder._state_section(state, ctx["specs"], ctx["import_run"])
        md = render_context(ctx)
    path = save_context(rt, task, ctx, md)
    return ctx, md, path


def spec_changes(rt: Runtime, state: TaskState) -> list[str]:
    """对比 PowerContext 中记录的规格指纹和 seekdb 中的当前内容。"""
    recorded = state.machine.get("spec_revisions") or {}
    if not recorded:
        return []
    rows = rt.store.chunks(rt.project, [f"spec:{s}" for s in recorded], purpose="run: compare recorded spec revisions")
    changed = []
    for spec_id, sha in sorted(recorded.items()):
        row = rows.get(f"spec:{spec_id}")
        if row is None or row["content_sha"][:12] != sha:
            changed.append(spec_id)
    return changed


# ------------------------------------------------------------------ verify


def do_verify(rt: Runtime, task: Task, phase: str) -> bool:
    state = rt.state(task.id)
    done, checks, machine = _progress(state)
    targets = machine.get("target_tests")
    if not targets:
        raise StepError("PowerContext 中没有这个任务的上下文记录（目标测试列表），请先运行 context")
    directory = rt.task_dir(task.id)
    before_dir = directory / "snapshots" / "before"
    if phase == "before":
        tree = copy_tree(rt.settings.project_dir, before_dir)
    else:
        if "develop" not in state.steps_done:
            raise StepError("PowerContext 记录显示开发步骤还没有完成，请先运行 develop")
        tree = directory / "snapshots" / "after"
        if not tree.is_dir() or not before_dir.is_dir():
            raise StepError(f"找不到修改前后的工程快照（{rt.rel(directory / 'snapshots')}），请重新运行 develop")
    out_dir = directory / "tests" / phase
    say(f"[verify {phase}] 目标测试函数 {len(targets)} 个（来自 PowerContext 记录 {state.latest.source_id}），工程 {rt.rel(tree)}")
    target = rt.run_tests(tree, list(targets), label="target", out_dir=out_dir)
    say(f"  目标测试：{target.summary()}；断言失败 {target.assertion_failures}，其他问题 {len(target.other_problems)}；日志 {target.log_path}")
    regression = rt.run_tests(tree, deselect(list(targets)), label="regression", out_dir=out_dir)
    say(f"  回归测试（全部非目标测试）：{regression.summary()}；日志 {regression.log_path}")

    new_checks: list[dict] = []

    def check(name: str, ok: bool, details: str) -> None:
        new_checks.append({"name": name, "status": "passed" if ok else "failed", "details": details})
        say(f"  [{'通过' if ok else '未通过'}] {name}：{details}")

    if phase == "before":
        env_ok = target.errors == 0 and not target.other_problems
        check(
            "修改前目标测试因功能未实现而失败",
            target.total > 0 and target.passed == 0 and target.failed == target.total and target.assertion_failures == target.failed and env_ok,
            f"{target.total} 个用例中失败 {target.failed} 个，其中断言失败 {target.assertion_failures} 个；"
            f"环境类问题（导入、夹具、收集错误）{target.errors + len(target.other_problems)} 个；退出码 {target.exit_code}；日志 {target.log_path}",
        )
        check(
            "修改前回归测试全部通过",
            regression.exit_code == 0 and regression.failed == 0 and regression.errors == 0 and regression.passed > 0,
            f"{regression.summary()}；日志 {regression.log_path}",
        )
    else:
        before = machine.get("verify_before", {})
        before_target, before_regression = before.get("target", {}), before.get("regression", {})
        check(
            "修改后目标测试全部通过",
            target.exit_code == 0 and target.failed == 0 and target.errors == 0 and target.skipped == 0
            and target.passed == target.total == before_target.get("total", target.total),
            f"{target.summary()}（修改前同一组 {before_target.get('total', '?')} 个用例全部失败）；日志 {target.log_path}",
        )  # fmt: skip
        check(
            "修改后回归测试全部通过",
            regression.exit_code == 0 and regression.failed == 0 and regression.errors == 0
            and regression.passed == before_regression.get("passed", regression.passed)
            and regression.skipped == before_regression.get("skipped", regression.skipped),
            f"{regression.summary()}（修改前 {before_regression.get('passed', '?')} passed）；日志 {regression.log_path}",
        )  # fmt: skip
        guarded = rt.read_only
        same = tree_sha(tree, guarded) == tree_sha(before_dir, guarded)
        check("规格和测试没有被修改", same, f"只读路径 {', '.join(guarded)} 修改前后的指纹{'一致' if same else '不一致'}")
        diff = diff_trees(before_dir, tree)
        changed = sorted(set(re.findall(r"^diff --git a/(\S+) b/", diff, re.M)))
        outside = [p for p in changed if not matches_any(p, rt.writable)]
        check("修改只涉及实现代码", bool(changed) and not outside, f"修改的文件：{', '.join(changed) or '无'}" + (f"；范围外：{', '.join(outside)}" if outside else ""))
        recorded = machine.get("develop", {}).get("diff_sha256")
        check(
            "被测代码就是 MiniMax 开发记录中的修改",
            recorded == sha_text(diff),
            f"快照差异 sha256 {sha_text(diff)[:12]}，开发记录 {str(recorded)[:12]}（{machine.get('develop', {}).get('session')}）",
        )

    passed = all(c["status"] == "passed" for c in new_checks)
    summary_dict = {"tree_sha": target.tree_sha, "target": _test_summary(target), "regression": _test_summary(regression)}
    step = f"verify-{phase}"
    steps_done = [s for s in state.steps_done if s != step] + ([step] if passed else [])
    if phase == "before":
        line = (
            f"修改前验证（工程指纹 {target.tree_sha[:12]}）：目标测试 {target.total} 个用例失败 {target.failed} 个（断言失败 {target.assertion_failures}）；"
            f"回归测试 {regression.passed} passed"
        )
        status = "partial" if passed else "blocked"
        extra = [] if passed else ["修改前验证没有通过：目标测试必须因功能未实现而失败，回归测试必须通过；检查工程和测试后重新运行 verify --phase before"]
    else:
        line = (
            f"修改后验证（工程指纹 {target.tree_sha[:12]}）：目标测试 {target.passed}/{target.total} passed；回归测试 {regression.passed} passed；"
            "规格和测试未被修改"
        )
        status = "succeeded" if passed else "failed"
        extra = [] if passed else ["修改后验证没有通过：用 develop --force 重新让 MiniMax 修改，然后再次验证"]
    write_outcome(
        rt.pc,
        state,
        step=step,
        status=status,
        summary=("任务完成：" if phase == "after" and passed else "") + line,
        objective=f"{task.id} {task.title}",
        done=done + [line],
        checks=_merge_checks(checks, new_checks),
        todo=todo_for(steps_done, extra),
        machine={**machine, "steps_done": steps_done, f"verify_{phase}": summary_dict},
    )
    say(f"  已写入 PowerContext：{state.latest.source_id}（状态 {status}）")
    return passed


# ------------------------------------------------------------------ develop


def _turn_printer(record: dict) -> None:
    for result in record["tool_results"]:
        args = result.get("input") or {}
        target = args.get("path") or args.get("suite") or args.get("pattern") or ""
        first = (result.get("output") or "").splitlines()[0] if result.get("output") else ""
        say(f"  第 {record['turn']:>2} 轮 {result['name']}({target}) → {'' if result['ok'] else '失败：'}{first[:120]}")
    if not record["tool_results"]:
        say(f"  第 {record['turn']:>2} 轮：没有工具调用（stop_reason {record.get('stop_reason')}）")


def do_develop(rt: Runtime, task: Task, *, replay: Path | None = None, force: bool = False, model: str | None = None,
               max_turns: int = 40) -> bool:  # fmt: skip
    state = rt.state(task.id)
    done, checks, machine = _progress(state)
    targets = machine.get("target_tests")
    if not targets:
        raise StepError("PowerContext 中没有这个任务的上下文记录，请先运行 context")
    if "develop" in state.steps_done and not force:
        say(f"[develop] PowerContext 记录 {state.latest_for('develop').source_id} 显示代码修改已经完成，跳过（--force 可重新修改）")
        return True
    directory = rt.task_dir(task.id)
    before = directory / "snapshots" / "before"
    if not before.is_dir():
        copy_tree(rt.settings.project_dir, before)
    after = copy_tree(before, directory / "snapshots" / "after")
    stamp = _stamp()
    dev_dir = directory / "develop"

    # 上下文现场重新生成：seekdb 检索 + PowerContext 中截至目前的进展和验证结果
    ctx, md = build_context(rt, task, state)
    context_path = write_text(dev_dir / f"context-{stamp}.md", md)
    write_json(dev_dir / f"context-{stamp}.json", ctx)
    counter = itertools.count(1)

    def runner(suite: str) -> TestRun:
        selection = list(targets) if suite == "target" else deselect(list(targets)) if suite == "regression" else []
        return rt.run_tests(after, selection, label=f"{next(counter):02d}-{suite}", out_dir=dev_dir / f"tests-{stamp}")

    workspace = Workspace(after, rt.read_only, rt.writable, runner)
    if replay is not None:
        session_path = replay
        session = json.loads(replay.read_text(encoding="utf-8"))
        say(f"[develop] 回放 MiniMax 开发记录 {rt.rel(replay)}（模型 {session.get('model')}，{session.get('turn_count')} 轮）中的修改调用")
        log = replay_session(session, workspace)
        diff = diff_trees(before, after)
        write_json(dev_dir / f"replay-{stamp}.json", {"session": rt.rel(replay), "edits": log, "diff_sha256": sha_text(diff)})
        if sha_text(diff) != session.get("final_diff_sha256"):
            raise StepError("回放得到的差异与开发记录中的最终差异不一致：开发记录可能来自不同的工程版本")
        changed = sorted(set(re.findall(r"^diff --git a/(\S+) b/", diff, re.M)))
        result = AgentResult(
            status="replayed", summary=session.get("final_summary", ""), turns=session.get("turn_count", 0), session_path=replay,
            diff=diff, diff_sha=sha_text(diff), changed_files=changed, edits=len(log), usage=session.get("usage_total", {}),
            last_tests=session.get("last_self_tests", {}),
        )  # fmt: skip
        mode, used_model = "replay", session.get("model")
    else:
        client = MiniMaxClient(rt.settings.minimax_api_key, rt.settings.minimax_base_url, model or rt.settings.minimax_model)
        session_path = dev_dir / f"session-{stamp}.json"
        say(f"[develop] 把任务和上下文（{len(md)} 字符，{rt.rel(context_path)}）交给 MiniMax {client.model}（{client.url}）")
        result = run_agent(
            client=client,
            task=task,
            context_md=md,
            baseline=before,
            workspace=workspace,
            target_tests=list(targets),
            session_path=session_path,
            meta={
                "project": rt.project,
                "code_version": rt.settings.code_version,
                "baseline": rt.rel(before),
                "workspace": rt.rel(after),
                "context_path": rt.rel(context_path),
                "powercontext_state": state.latest.source_id if state.latest else None,
            },
            max_turns=max_turns,
            on_turn=_turn_printer,
        )
        write_text(session_path.with_suffix(".md"), render_session(json.loads(session_path.read_text(encoding="utf-8"))))
        mode, used_model = "live", client.model
    patch = write_text(directory / "change.patch", result.diff)
    added, removed = _diff_stat(result.diff)
    tests = "；".join(f"{k} {v.get('passed')} passed / {v.get('failed')} failed" for k, v in result.last_tests.items()) or "无"
    say(f"  MiniMax 结果：{result.status}，{result.turns} 轮，成功修改 {result.edits} 次；修改的文件 {', '.join(result.changed_files) or '无'}（+{added} −{removed}）")
    say(f"  助手最后一次自测：{tests}；差异已写入 {rt.rel(patch)}；开发记录 {rt.rel(session_path)}")

    ok = result.status in ("finished", "replayed") and bool(result.diff) and not result.read_only_violations
    steps_done = [s for s in state.steps_done if s not in ("develop", "verify-after")] + (["develop"] if ok else [])
    line = (
        f"MiniMax 开发助手（{used_model}，{'实时调用' if mode == 'live' else '回放开发记录'}）用 {result.turns} 轮工具调用完成修改："
        f"{', '.join(result.changed_files) or '无'}（+{added} −{removed} 行，差异 sha256 {result.diff_sha[:12]}）；助手自测 {tests}"
    )
    extra = [] if ok else [f"MiniMax 没有完成修改（状态 {result.status}，只读违规 {len(result.read_only_violations)}）：运行 develop --force 重试"]
    write_outcome(
        rt.pc,
        state,
        step="develop",
        status="partial" if ok else "failed",
        summary=line,
        objective=f"{task.id} {task.title}",
        done=done + [line],
        checks=checks,
        todo=todo_for(steps_done, extra),
        machine={
            **machine,
            "steps_done": steps_done,
            "develop": {
                "mode": mode,
                "model": used_model,
                "endpoint": rt.settings.minimax_base_url,
                "session": rt.rel(session_path),
                "context": rt.rel(context_path),
                "context_sha256": sha_text(md),
                "turns": result.turns,
                "edits": result.edits,
                "status": result.status,
                "changed_files": result.changed_files,
                "diff_sha256": result.diff_sha,
                "patch": rt.rel(patch),
                "usage": result.usage,
            },
        },
    )
    say(f"  已写入 PowerContext：{state.latest.source_id}（状态 {'partial' if ok else 'failed'}）")
    return ok


# ------------------------------------------------------------------ run


def do_run(rt: Runtime, task: Task, *, stop_after: str | None = None, replay: Path | None = None, model: str | None = None,
           max_turns: int = 40) -> bool:  # fmt: skip
    state = rt.state(task.id)
    if state.empty:
        say(f"PowerContext 中没有任务 {task.id} 的记录（Scope {state.scope_title}）：从空状态开始")
    else:
        latest = state.latest
        say(
            f"从 PowerContext 读回任务 {task.id}：Scope {state.scope_id}，{len(state.contracts) + len(state.outcomes)} 条记录；"
            f"最新 {latest.source_id if latest else '无'}（{latest.status if latest else '-'}）；已完成步骤 {', '.join(state.steps_done) or '无'}"
        )
        changed = spec_changes(rt, state)
        if changed:
            say(f"规格 {', '.join(changed)} 在上次记录之后被修改并重新导入：按新规格重新生成上下文，后续步骤重新执行")
            ctx, md = build_context(rt, task, state)
            record_context(rt, task, state, ctx, md, note=f"检测到规格变更：{', '.join(changed)}，按新内容重新生成上下文，之前的验证结果作废")
            save_context(rt, task, ctx, md)
    for step in STEPS:
        state = rt.state(task.id)
        if step in state.steps_done:
            say(f"[{step}] 跳过：PowerContext 记录 {state.latest_for(step).source_id} 显示已完成")
            continue
        if step == "context":
            ctx, md, path = do_context(rt, task)
            f = context_facts(ctx)
            say(f"[context] 目标规格 {', '.join(f['target_specs'])}；需要修改 {', '.join(f['to_change'])}；目标测试函数 {len(f['target_tests'])} 个；已保存 {rt.rel(path)}")
        elif step == "verify-before":
            do_verify(rt, task, "before")
        elif step == "develop":
            do_develop(rt, task, replay=replay, model=model, max_turns=max_turns)
        else:
            do_verify(rt, task, "after")
        state = rt.state(task.id)
        if step not in state.steps_done:
            say(f"[{step}] 没有完成，流程停止；结果已写入 PowerContext（{state.latest.source_id}），修正后重新运行 run 会从这一步继续")
            return False
        if step == stop_after:
            say(f"按 --stop-after {step} 停止。重新运行 run 时会从 PowerContext 读回进度，从下一步继续")
            return True
    state = rt.state(task.id)
    say(f"任务 {task.id} 全部步骤已完成：{state.latest.summary}")
    return True


# ------------------------------------------------------------------ checks


def do_check_context(rt: Runtime, task: Task) -> bool:
    expected_path = rt.settings.samples_dir / task.id / "expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    state = rt.state(task.id)
    ctx, md = build_context(rt, task, state)
    path = save_context(rt, task, ctx, md, name="context-check")
    specs = {s["id"]: role for role, items in ctx["specs"].items() for s in items}
    to_change = {f"{c['path']}::{c['symbol']}" for c in ctx["code"]["to_change"]}
    related = {f"{c['path']}::{c['symbol']}" for c in ctx["code"]["related"]}
    target_files = set(ctx["tests"]["target_files"])
    target_tests = {t["node_id"] for t in ctx["tests"]["target"]}
    regression_files = {t["path"] for t in ctx["tests"]["regression"]}
    results: list[tuple[str, bool, str]] = []
    for sid in expected["specs"]["target"]:
        results.append((f"目标规格 {sid}", specs.get(sid) == "target", f"实际角色：{specs.get(sid, '未包含')}"))
    for sid in expected["specs"].get("required", []):
        results.append((f"必须包含的规格 {sid}", sid in specs, f"实际角色：{specs.get(sid, '未包含')}"))
    for sym in expected["code"]["to_change"]:
        results.append((f"需要修改 {sym}", sym in to_change, "在“需要修改”中" if sym in to_change else "未列为需要修改"))
    for sym in expected["code"].get("required", []):
        where = "需要修改" if sym in to_change else "相关代码" if sym in related else None
        results.append((f"必须包含的代码 {sym}", where is not None, f"位置：{where or '未包含'}"))
    for file in expected["tests"]["target_files"]:
        results.append((f"目标测试文件 {file}", file in target_files, "已包含" if file in target_files else "未包含"))
    for node in expected["tests"].get("target_tests", []):
        results.append((f"目标测试 {node}", node in target_tests, "已包含" if node in target_tests else "未包含"))
    for file in expected["tests"].get("regression_files", []):
        results.append((f"回归测试文件 {file}", file in regression_files, "已包含" if file in regression_files else "未包含"))
    v = ctx["source_verification"]
    results.append(("引用的来源真实存在且内容一致", not v["problems"], f"{v['ok']}/{v['checked']} 处一致" + (f"；{v['problems'][:3]}" if v["problems"] else "")))
    results.append(("任务状态来自 PowerContext", ctx["state"].get("available", False), f"Scope {ctx['state'].get('scope_title')}，记录 {ctx['state'].get('records', 0)} 条"))
    say(f"按 {rt.rel(expected_path)} 核对上下文（导入批次 #{ctx['import_run']['run_id']}，输出 {rt.rel(path)}）：")
    for name, ok, detail in results:
        say(f"  [{'通过' if ok else '未通过'}] {name} — {detail}")
    passed = all(ok for _, ok, _ in results)
    say(f"结果：{sum(ok for _, ok, _ in results)}/{len(results)} 项通过" + ("" if passed else "，有未通过项"))
    return passed


def _initial_context(session: dict) -> str:
    message = session.get("initial_user_message", "")
    marker = "\n---\n\n"
    return message.split(marker, 1)[1] if marker in message else ""


def do_check_record(rt: Runtime, task_id: str, *, session_path: Path | None = None, patch_path: Path | None = None) -> bool:
    """核对 MiniMax 开发记录：包含任务和上下文、确有模型响应，并且重放其中的修改调用能得到提交的代码差异。"""
    if session_path is None:
        state = rt.state(task_id)
        recorded = state.machine.get("develop", {}).get("session")
        if not recorded:
            raise StepError("PowerContext 中没有开发记录的位置，请用 --session 指定 session.json")
        session_path = rt.settings.home / recorded
    patch_path = patch_path or rt.task_dir(task_id) / "change.patch"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    turns = session.get("turns", [])
    context_md = _initial_context(session)
    results: list[tuple[str, bool, str]] = [
        ("记录对应本任务", session.get("task", {}).get("id") == task_id, f"记录中的任务 {session.get('task', {}).get('id')}"),
        (
            "记录包含提供给 MiniMax 的上下文",
            bool(context_md) and sha_text(context_md) == session.get("context_sha256"),
            f"首条消息中的上下文 {len(context_md)} 字符，sha256 {sha_text(context_md)[:12]}，记录值 {str(session.get('context_sha256'))[:12]}",
        ),
        (
            "记录来自 MiniMax 接口",
            urlparse(str(session.get("endpoint"))).hostname in MINIMAX_HOSTS and str(session.get("model", "")).startswith("MiniMax"),
            f"接口 {session.get('endpoint')}，模型 {session.get('model')}",
        ),
        (
            "每一轮都有 MiniMax 的真实响应",
            bool(turns) and all(t.get("response_id") and t.get("usage") for t in turns),
            f"{len(turns)} 轮，模型 {session.get('model')}，接口 {session.get('endpoint')}，Token 用量 {session.get('usage_total')}",
        ),
        ("修改由 MiniMax 的工具调用完成", session.get("successful_edits", 0) > 0, f"成功的 edit_file/write_file 调用 {session.get('successful_edits', 0)} 次"),
        ("没有写入只读路径", not session.get("read_only_violations"), f"只读违规 {session.get('read_only_violations') or '无'}"),
    ]
    scratch = rt.task_dir(task_id) / "check-record"
    tree = copy_tree(rt.settings.project_dir, scratch / "replay")
    pristine = copy_tree(rt.settings.project_dir, scratch / "baseline")
    try:
        log = replay_session(session, Workspace(tree, rt.read_only, rt.writable, test_runner=None))
        diff = diff_trees(pristine, tree)
        replay_ok = sha_text(diff) == session.get("final_diff_sha256")
        results.append(("重放修改调用得到记录中的最终差异", replay_ok, f"重放 {len(log)} 次修改，差异 sha256 {sha_text(diff)[:12]}，记录 {str(session.get('final_diff_sha256'))[:12]}"))
    except RuntimeError as exc:
        results.append(("重放修改调用得到记录中的最终差异", False, str(exc)))
    if patch_path.is_file():
        patch = patch_path.read_text(encoding="utf-8")
        results.append(("提交的代码差异与开发记录一致", sha_text(patch) == session.get("final_diff_sha256"), f"{rt.rel(patch_path)} sha256 {sha_text(patch)[:12]}"))
    else:
        results.append(("提交的代码差异与开发记录一致", False, f"找不到 {rt.rel(patch_path)}"))
    shutil.rmtree(scratch, ignore_errors=True)
    say(f"核对 MiniMax 开发记录 {rt.rel(session_path)}：")
    for name, ok, detail in results:
        say(f"  [{'通过' if ok else '未通过'}] {name} — {detail}")
    passed = all(ok for _, ok, _ in results)
    say(f"结果：{sum(ok for _, ok, _ in results)}/{len(results)} 项通过")
    return passed


def do_spec_update_demo(rt: Runtime, task: Task) -> bool:
    """修改样例规格 → 重新导入 → 上下文使用新内容 → 恢复规格 → 重新导入 → 上下文恢复原内容。"""
    expected = json.loads((rt.settings.samples_dir / task.id / "expected.json").read_text(encoding="utf-8"))
    demo = expected["spec_update"]
    spec_file = rt.settings.project_dir / demo["file"]
    original = spec_file.read_text(encoding="utf-8")
    if demo["find"] not in original:
        raise StepError(f"{demo['file']} 中找不到要修改的位置：{demo['find']}")
    spec_id = demo["spec"]
    results: list[tuple[str, bool, str]] = []

    def context_spec(name: str) -> tuple[dict | None, dict, str]:
        ctx, md = build_context(rt, task, rt.state(task.id))
        save_context(rt, task, ctx, md, name=name)
        item = next((s for role in ("target", "constraint", "sibling") for s in ctx["specs"][role] if s["id"] == spec_id), None)
        return item, ctx, md

    recorded = (rt.state(task.id).machine.get("spec_revisions") or {}).get(spec_id)

    say(f"1) 修改 {demo['file']} 中的 {spec_id}：追加“{demo['added_text'].strip()}”")
    spec_file.write_text(original.replace(demo["find"], demo["find"] + demo["added_text"], 1), encoding="utf-8")
    try:
        say("2) 重新导入")
        report = do_import(rt)
        results.append((f"重新导入识别出 {spec_id} 的变更", f"spec:{spec_id}" in report["updated"], f"更新的片段：{report['updated']}"))
        say("3) 重新生成上下文（输出 runs/<任务>/context-spec-updated.md）")
        item, ctx, md = context_spec("context-spec-updated")
        has_new = bool(item) and demo["added_text"].strip() in item["content"] and demo["added_text"].strip() in md
        results.append((f"上下文中的 {spec_id} 使用更新后的内容", has_new, f"修订 r{item['revision'] if item else '?'}，包含新增文字：{has_new}"))
        if recorded:
            flagged = spec_id in ctx["state"].get("spec_changes", [])
            results.append(("状态段提示规格在上次记录后发生变化", flagged, f"PowerContext 记录的指纹 {recorded}，当前 {item['content_sha'][:12] if item else '?'}"))
    finally:
        say(f"4) 恢复 {demo['file']} 并重新导入")
        spec_file.write_text(original, encoding="utf-8")
        do_import(rt)
    item, ctx, md = context_spec("context-spec-restored")
    restored = bool(item) and demo["added_text"].strip() not in item["content"] and not ctx["state"].get("spec_changes")
    results.append((f"恢复后上下文中的 {spec_id} 回到原内容", restored, f"修订 r{item['revision'] if item else '?'}，不再包含新增文字，状态段没有规格变更提示：{restored}"))
    say("规格更新检查：")
    for name, ok, detail in results:
        say(f"  [{'通过' if ok else '未通过'}] {name} — {detail}")
    return all(ok for _, ok, _ in results)
