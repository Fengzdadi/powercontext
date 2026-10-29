"""运行业务工程的 pytest，保存日志（命令、退出码、代码版本）并解析 junit 结果。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .records import now_iso, write_text
from .workspace import tree_sha


@dataclass
class TestRun:
    __test__ = False

    label: str
    selection: list[str]
    command: str
    cwd: str
    exit_code: int
    code_version: str
    tree_sha: str
    started_at: str
    seconds: float
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    assertion_failures: int = 0
    failed_tests: list[str] = field(default_factory=list)
    other_problems: list[str] = field(default_factory=list)  # 非断言失败：导入错误、夹具错误、收集错误等
    log_path: str = ""
    junit_path: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    def summary(self) -> str:
        parts = [f"{self.passed} passed", f"{self.failed} failed"]
        if self.errors:
            parts.append(f"{self.errors} errors")
        if self.skipped:
            parts.append(f"{self.skipped} skipped")
        return f"{', '.join(parts)}，exit {self.exit_code}"

    def to_dict(self) -> dict:
        return asdict(self)


def run_pytest(tree: Path, selection: list[str], *, label: str, out_dir: Path, code_version: str, rel=str) -> TestRun:
    """在 tree 目录里运行 `python -m pytest`，selection 为文件或节点 ID 列表。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    junit = out_dir / f"{label}.junit.xml"
    log = out_dir / f"{label}.log"
    args = [sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", f"--junitxml={junit}", *selection]
    display = "python -m pytest -q -rfE -p no:cacheprovider --junitxml=" + rel(junit) + " " + " ".join(selection)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
    fingerprint = tree_sha(tree)
    started_at = now_iso()
    started = time.perf_counter()
    if junit.exists():
        junit.unlink()
    proc = subprocess.run(args, cwd=tree, env=env, capture_output=True, text=True, timeout=900)
    seconds = round(time.perf_counter() - started, 2)
    run = TestRun(
        label=label,
        selection=selection,
        command=display,
        cwd=rel(tree),
        exit_code=proc.returncode,
        code_version=code_version,
        tree_sha=fingerprint,
        started_at=started_at,
        seconds=seconds,
        log_path=rel(log),
        junit_path=rel(junit),
    )
    _parse_junit(junit, run, tree)
    header = "\n".join(
        [
            f"# label: {label}",
            f"# command: {display}",
            f"# cwd: {rel(tree)}",
            f"# code_version: {code_version}",
            f"# tree_sha256: {fingerprint}",
            f"# started_at: {started_at}",
            f"# seconds: {seconds}",
            f"# exit_code: {proc.returncode}",
            f"# result: {run.summary()}；断言失败 {run.assertion_failures}，其他问题 {len(run.other_problems)}",
            "",
        ]
    )
    write_text(log, header + proc.stdout + (("\n# stderr\n" + proc.stderr) if proc.stderr.strip() else ""))
    return run


BEHAVIOR_FAILURES = ("assert", "AssertionError", "Failed: DID NOT RAISE")


def _node_id(tree: Path, classname: str, name: str) -> str:
    """junit 的 classname（tests.test_x 或 tests.test_x.TestY）还原成 pytest 节点 ID。"""
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = "/".join(parts[:cut]) + ".py"
        if (tree / candidate).is_file():
            return "::".join([candidate, *parts[cut:], name])
    return f"{classname}::{name}"


def _parse_junit(path: Path, run: TestRun, tree: Path) -> None:
    """统计结果，并区分“断言失败”（行为不符合预期）和其他问题（导入、夹具、收集等环境错误）。"""
    if not path.exists():
        run.other_problems.append("pytest 没有生成 junit 报告（可能没有启动）")
        return
    root = ET.parse(path).getroot()
    for case in root.iter("testcase"):
        node = _node_id(tree, case.get("classname", ""), case.get("name", ""))
        outcome = "passed"
        for child in case:
            if child.tag not in ("failure", "error", "skipped"):
                continue
            outcome = child.tag
            message = (child.get("message") or "").strip()
            if child.tag == "failure" and message.startswith(BEHAVIOR_FAILURES):
                run.assertion_failures += 1
            elif child.tag in ("failure", "error"):
                run.other_problems.append(f"{node}: {message.splitlines()[0][:200] if message else child.tag}")
        if outcome == "passed":
            run.passed += 1
        elif outcome == "skipped":
            run.skipped += 1
        else:
            run.failed_tests.append(node)
            if outcome == "failure":
                run.failed += 1
            else:
                run.errors += 1
    collection_errors = sum(int(s.get("errors") or 0) for s in root.iter("testsuite"))
    if collection_errors > run.errors:
        run.other_problems.append(f"测试收集阶段出错 {collection_errors - run.errors} 处")
