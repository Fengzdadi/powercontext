"""任务状态：保存在 PowerContext 里，模块重启后读回并用于后续上下文和流程续跑。

用法（PowerContext 1.4.1 HTTP API）：
- 每个任务一个 Scope：`POST /v1/scopes`，idempotency_key = 标题 = `sddctx/<工程>/<任务>`；
  只读时用 `GET /v1/scopes?query=<标题>&query_field=title` 查找，不会因为读取而创建 Scope。
- 任务开始时写一份 Work Contract：`POST /v1/work/contracts/create`（目标、规格依据、修改范围、完成标准）。
- 每完成一步写一份 Task Outcome：`POST /v1/work/outcomes/record`。observations 是累计的已完成事项，
  checks 是累计的验证结果，remaining_work 是待办；另有一条 `sddctx-state {...}` 观察记录机器可读的状态。
- 读取：`GET /v1/scopes/{scope_id}/sources` 按日志位置升序返回所有记录，最新的 Task Outcome 就是当前状态。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .records import Recorder, now_iso

CONTRACT_SCHEMA = "powercontext.work-contract.v1"
OUTCOME_SCHEMA = "powercontext.task-outcome.v1"
STATE_PREFIX = "sddctx-state "
STATE_PART = re.compile(r"(\d+)/(\d+) ")
STATE_PART_SIZE = 7000  # 单条观察记录最长 8192 字符，机器可读状态按段拆开保存
STEPS = ["context", "verify-before", "develop", "verify-after"]
STEP_TODO = {
    "context": "生成任务上下文：从 seekdb 检索适用规格、待修改代码和验证测试（sddctx context）",
    "verify-before": "修改前验证：目标测试应因功能未实现而失败，回归测试应全部通过（sddctx verify --phase before）",
    "develop": "把上下文交给 MiniMax 开发助手完成代码修改（sddctx develop）",
    "verify-after": "修改后验证：目标测试与回归测试应全部通过（sddctx verify --phase after）",
}


class PowerContextError(RuntimeError):
    pass


class PowerContext:
    def __init__(self, base_url: str, recorder: Recorder, timeout: float = 60) -> None:
        self.base_url = base_url
        self.recorder = recorder
        self.timeout = timeout

    def call(self, method: str, path: str, body: dict | None = None, *, purpose: str, ok: tuple = (200, 201, 202),
             brief=None) -> dict:  # fmt: skip
        """brief：把响应压缩成记录用的摘要（读取全部记录时只记 source_id、位置和内容摘要）。"""
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method, headers={"content-type": "application/json"}
        )
        started = time.perf_counter()
        status, payload = 0, None
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read()
                payload = json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = raw.decode("utf-8", "replace")[:2000]
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            self.recorder.write({"service": "powercontext", "purpose": purpose, "method": method, "path": path, "error": str(exc)})
            raise PowerContextError(f"无法连接 PowerContext（{self.base_url}）：{exc}") from exc
        self.recorder.write(
            {
                "service": "powercontext",
                "purpose": purpose,
                "method": method,
                "path": path,
                "request": body,
                "status": status,
                "response": brief(payload) if brief and status in ok else payload,
                "ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
        if status not in ok:
            raise PowerContextError(f"PowerContext {method} {path} 返回 {status}：{payload}")
        return payload or {}

    def ready(self) -> dict:
        return self.call("GET", "/health/ready", purpose="health")

    def version(self) -> str:
        info = self.call("GET", "/v1/server-info", purpose="server info")
        contract = info.get("api_contract_version") or {}
        return f"{info.get('package_version', '?')}（API 契约 {contract.get('major', '?')}.{contract.get('minor', '?')}）"

    def find_scope(self, title: str) -> str | None:
        query = urllib.parse.urlencode({"query": title, "query_field": "title", "limit": 100})
        page = self.call("GET", f"/v1/scopes?{query}", purpose="state: find task scope")
        for item in page.get("items", []):
            if item.get("title") == title:
                return item["scope_id"]
        return None

    def ensure_scope(self, title: str, summary: str) -> str:
        scope = self.call(
            "POST",
            "/v1/scopes",
            {"title": title, "summary": summary, "idempotency_key": title},
            purpose="state: create or reuse task scope",
        )
        return scope["scope_id"]

    def sources(self, scope_id: str) -> list[dict]:
        items: list[dict] = []
        cursor = None
        while True:
            query = {"limit": 100} | ({"cursor": cursor} if cursor else {})
            page = self.call(
                "GET",
                f"/v1/scopes/{scope_id}/sources?{urllib.parse.urlencode(query)}",
                purpose="state: read task records",
                brief=_brief_sources,
            )
            items += page.get("items", [])
            cursor = page.get("next_cursor")
            if not cursor:
                return items

    def record_contract(self, scope_id: str, source_id: str, contract: dict) -> dict:
        return self.call(
            "POST",
            "/v1/work/contracts/create",
            {"scope_id": scope_id, "source_id": source_id, "contract": contract},
            purpose="state: write work contract",
        )

    def record_outcome(self, scope_id: str, source_id: str, outcome: dict) -> dict:
        return self.call(
            "POST",
            "/v1/work/outcomes/record",
            {"scope_id": scope_id, "source_id": source_id, "outcome": outcome},
            purpose="state: write task outcome",
        )


def _brief_sources(page: dict) -> dict:
    items = []
    for item in page.get("items", []):
        content = item.get("content") or ""
        items.append(
            {
                "source_id": item.get("source_id"),
                "position": item.get("position"),
                "content_digest": item.get("content_digest"),
                "content": content if len(content) <= 400 else content[:400] + f"…（共 {len(content)} 字符）",
            }
        )
    return {"items": items, "next_cursor": page.get("next_cursor")}


def _claims(texts: list[str]) -> list[dict]:
    return [{"text": text[:8000], "basis": "declared", "evidence": []} for text in texts if text.strip()]


@dataclass
class Outcome:
    source_id: str
    position: int
    status: str
    summary: str
    observations: list[str]
    checks: list[dict]
    remaining_work: list[str]
    machine: dict

    @property
    def step(self) -> str:
        return self.machine.get("step", "")


@dataclass
class TaskState:
    project: str
    task_id: str
    scope_title: str
    scope_id: str | None = None
    contracts: list[dict] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.contracts and not self.outcomes

    @property
    def latest(self) -> Outcome | None:
        return self.outcomes[-1] if self.outcomes else None

    @property
    def machine(self) -> dict:
        return self.latest.machine if self.latest else {}

    @property
    def steps_done(self) -> list[str]:
        return list(self.machine.get("steps_done", []))

    def latest_for(self, step: str) -> Outcome | None:
        for outcome in reversed(self.outcomes):
            if outcome.step == step:
                return outcome
        return None

    def to_dict(self) -> dict:
        latest = self.latest
        return {
            "project": self.project,
            "task_id": self.task_id,
            "scope_title": self.scope_title,
            "scope_id": self.scope_id,
            "empty": self.empty,
            "records": len(self.contracts) + len(self.outcomes),
            "contract": self.contracts[-1] if self.contracts else None,
            "latest_outcome": None
            if latest is None
            else {
                "source_id": latest.source_id,
                "position": latest.position,
                "status": latest.status,
                "summary": latest.summary,
                "done": latest.observations,
                "checks": latest.checks,
                "todo": latest.remaining_work,
                "machine": latest.machine,
            },
            "history": [
                {"position": o.position, "source_id": o.source_id, "step": o.step, "status": o.status, "summary": o.summary}
                for o in self.outcomes
            ],
        }


def scope_title(project: str, task_id: str) -> str:
    return f"sddctx/{project}/{task_id}"


def load_state(pc: PowerContext, project: str, task_id: str) -> TaskState:
    title = scope_title(project, task_id)
    state = TaskState(project=project, task_id=task_id, scope_title=title)
    state.scope_id = pc.find_scope(title)
    if state.scope_id is None:
        return state
    for item in pc.sources(state.scope_id):
        content = item.get("content")
        try:
            doc = json.loads(content) if isinstance(content, str) else content
        except ValueError:
            continue
        if not isinstance(doc, dict):
            continue
        if doc.get("schema") == CONTRACT_SCHEMA:
            state.contracts.append({"source_id": item["source_id"], "position": item["position"], **doc})
        elif doc.get("schema") == OUTCOME_SCHEMA:
            parts: dict[int, str] = {}
            observations = []
            for claim in doc.get("observations", []):
                text = claim.get("text", "")
                if not text.startswith(STATE_PREFIX):
                    observations.append(text)
                    continue
                body = text[len(STATE_PREFIX) :]
                match = STATE_PART.match(body)
                if match:
                    parts[int(match.group(1))] = body[match.end() :]
                else:
                    parts[1] = body
            try:
                machine = json.loads("".join(parts[k] for k in sorted(parts))) if parts else {}
            except ValueError:
                machine = {}
            state.outcomes.append(
                Outcome(
                    source_id=item["source_id"],
                    position=item["position"],
                    status=doc.get("status", "unknown"),
                    summary=doc.get("summary", ""),
                    observations=observations,
                    checks=[{k: c.get(k) for k in ("name", "status", "details")} for c in doc.get("checks", [])],
                    remaining_work=list(doc.get("remaining_work", [])),
                    machine=machine,
                )
            )
    state.contracts.sort(key=lambda c: c["position"])
    state.outcomes.sort(key=lambda o: o.position)
    return state


def todo_for(steps_done: list[str], extra: list[str] | None = None) -> list[str]:
    todo = list(extra or [])
    todo += [STEP_TODO[step] for step in STEPS if step not in steps_done]
    return todo


def write_contract(pc: PowerContext, state: TaskState, objective: str, facts: list[str], in_scope: list[str],
                   exclusions: list[str], criteria: list[str], notes: list[str]) -> dict:  # fmt: skip
    if state.scope_id is None:
        state.scope_id = pc.ensure_scope(state.scope_title, f"sddctx 任务状态：工程 {state.project}，任务 {state.task_id}")
    contract = {
        "schema": CONTRACT_SCHEMA,
        "trust": "untrusted_input",
        "objective": objective[:8000],
        "facts": _claims(facts)[:64],
        "in_scope": [s[:8000] for s in in_scope][:64],
        "exclusions": [s[:8000] for s in exclusions][:64],
        "completion_criteria": [s[:8000] for s in criteria][:64],
        "authorization_notes": [s[:8000] for s in notes][:64],
        "open_questions": [],
    }
    source_id = f"{state.task_id}/contract/{len(state.contracts) + 1:03d}"
    receipt = pc.record_contract(state.scope_id, source_id, contract)
    state.contracts.append({"source_id": source_id, "position": receipt.get("position"), **contract})
    return receipt


def write_outcome(pc: PowerContext, state: TaskState, *, step: str, status: str, summary: str, objective: str,
                  done: list[str], checks: list[dict], todo: list[str], machine: dict) -> dict:  # fmt: skip
    """写入一条 Task Outcome。done/checks 传入的是截至目前的累计值。"""
    if state.scope_id is None:
        state.scope_id = pc.ensure_scope(state.scope_title, f"sddctx 任务状态：工程 {state.project}，任务 {state.task_id}")
    machine = {**machine, "v": 1, "task": state.task_id, "step": step, "recorded_at": now_iso()}
    blob = json.dumps(machine, ensure_ascii=False, separators=(",", ":"))
    pieces = [blob[i : i + STATE_PART_SIZE] for i in range(0, len(blob), STATE_PART_SIZE)]
    blobs = [f"{STATE_PREFIX}{n}/{len(pieces)} {piece}" for n, piece in enumerate(pieces, 1)]
    outcome = {
        "schema": OUTCOME_SCHEMA,
        "trust": "untrusted_observation",
        "objective": objective[:8000],
        "status": status,
        "summary": summary[:8000],
        "observations": _claims(done[-(64 - len(blobs)) :] + blobs),
        "checks": [
            {"name": c["name"][:8000], "status": c["status"], "basis": "declared", "evidence": []}
            | ({"details": c["details"][:8000]} if c.get("details") else {})
            for c in checks
        ][:64],
        "produced_artifacts": [],
        "remaining_work": [t[:8000] for t in todo][:64],
    }
    source_id = f"{state.task_id}/outcome/{len(state.outcomes) + 1:03d}-{step}"
    receipt = pc.record_outcome(state.scope_id, source_id, outcome)
    state.outcomes.append(
        Outcome(
            source_id=source_id,
            position=int(receipt.get("position") or 0),
            status=status,
            summary=summary,
            observations=list(done),
            checks=[{k: c.get(k) for k in ("name", "status", "details")} for c in checks],
            remaining_work=list(todo),
            machine=machine,
        )
    )
    return receipt
