"""PowerContext 1.4.1 client.

Scope 幂等创建、原子记忆的创建/替换（If-Match ETag）、标签读写（ETag）、
handle 读写、artifact-tags/query、revision 历史、memory/remember、
context/bootstrap、context/prepare。

每次调用都会在模块级 CALL_LOG 里留下一条"请求 / 响应摘要"日志，
供验证脚本和"我的记忆"页面展示。

网络层错误（超时、连接失败）统一抛 PowerContextUnavailable，
调用方据此优雅降级（出题判分照常，界面提示"记忆服务暂不可用"）。
"""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import httpx

from .config import get_settings


class PowerContextUnavailable(Exception):
    """PowerContext 网络不可达 / 超时 / 5xx。调用方应降级而不是失败。"""


# 每条记忆的文本上限（PowerContext 1.4.1 实测）。
MEMORY_TEXT_LIMIT = 8000

CALL_LOG: deque[dict] = deque(maxlen=300)
_LOG_LOCK = threading.Lock()


def _log_call(entry: dict) -> None:
    with _LOG_LOCK:
        CALL_LOG.append(entry)


def recent_calls(limit: int = 100) -> list[dict]:
    with _LOG_LOCK:
        return list(CALL_LOG)[-limit:]


def check_powercontext() -> tuple[bool, str]:
    s = get_settings()
    try:
        resp = httpx.get(f"{s.powercontext_url}/health/ready", timeout=5)
        if resp.status_code == 200:
            return True, "ok"
        return False, f"status={resp.status_code}"
    except Exception as e:
        return False, str(e)


def _summarize(obj, limit: int = 400) -> str:
    try:
        text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    except Exception:
        text = str(obj)
    text = text.replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


class PowerContextClient:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None,
                 transport: Optional[httpx.BaseTransport] = None):
        s = get_settings()
        self.base_url = (base_url or s.powercontext_url).rstrip("/")
        self.timeout = timeout if timeout is not None else s.powercontext_timeout_seconds
        self.transport = transport

    # ------------------------------------------------------------------ base

    def _request(self, method: str, path: str, *, json_body: Optional[dict] = None,
                 headers: Optional[dict] = None) -> httpx.Response:
        url = f"{self.base_url}{path}"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "request": _summarize(json_body if json_body is not None else headers or ""),
        }
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                resp = client.request(method, url, json=json_body, headers=headers)
        except httpx.HTTPError as e:
            entry.update(status=None, response=f"网络错误: {type(e).__name__}: {e}")
            _log_call(entry)
            raise PowerContextUnavailable(str(e)) from e
        if resp.status_code >= 500:
            entry.update(status=resp.status_code, response=_summarize(resp.text))
            _log_call(entry)
            raise PowerContextUnavailable(f"HTTP {resp.status_code}: {resp.text[:200]}")
        entry.update(status=resp.status_code,
                     response=_summarize(resp.text if resp.text else "(空响应体)"))
        _log_call(entry)
        return resp

    def _ok_json(self, method: str, path: str, *, json_body: Optional[dict] = None,
                 headers: Optional[dict] = None,
                 expected: tuple[int, ...] = (200, 201)) -> dict:
        resp = self._request(method, path, json_body=json_body, headers=headers)
        if resp.status_code not in expected:
            raise RuntimeError(f"PowerContext {method} {path} 返回 {resp.status_code}: {resp.text[:300]}")
        if not resp.text:
            return {}
        return json.loads(resp.text)

    # ----------------------------------------------------------------- scope

    def ensure_scope(self, learner: str, course_id: str) -> str:
        """按 idempotency_key 幂等创建/取回学习者 × 课程的 Scope。"""
        key = f"examradar:learner:{learner}:course:{course_id}"
        data = self._ok_json(
            "POST", "/v1/scopes",
            json_body={
                "title": f"ExamRadar 学习者 {learner}（课程 {course_id}）",
                "summary": f"ExamRadar 复习教练记忆：学习者 {learner}，课程 {course_id}。",
                "idempotency_key": key,
            },
            expected=(200, 201),
        )
        return data["scope_id"]

    # ------------------------------------------------------------- artifacts

    def create_memory(self, scope_id: str, kind: str, text: str) -> tuple[str, int]:
        """创建原子记忆，返回 (artifact_id, revision)。"""
        if len(text.encode("utf-8")) > MEMORY_TEXT_LIMIT:
            raise ValueError("记忆文本超过 8192 字节上限")
        data = self._ok_json(
            "POST", f"/v1/scopes/{scope_id}/artifacts",
            json_body={
                "family": "atomic-memory",
                "content": {
                    "schema": "powercontext.atomic-memory.v1",
                    "kind": kind,
                    "text": text,
                },
            },
            expected=(200, 201),
        )
        artifact = data.get("artifact") or data
        return artifact["artifact_id"], int(artifact.get("revision") or 1)

    def get_memory(self, scope_id: str, artifact_id: str) -> tuple[str, int]:
        """读原子记忆，返回 (text, revision)。"""
        resp = self._request(
            "GET", f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}")
        if resp.status_code == 404:
            raise RuntimeError(f"artifact {artifact_id} 不存在: {resp.text[:200]}")
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET artifact {artifact_id} 返回 {resp.status_code}: {resp.text[:300]}")
        etag = resp.headers.get("ETag", "")
        revision = _parse_etag(etag, "revision")
        data = json.loads(resp.text)
        # 1.4.1 响应结构：artifact.content.text 或顶层 text
        content = data.get("content") or (data.get("artifact") or {}).get("content") or {}
        text = content.get("text") or data.get("text") or ""
        return text, revision

    def replace_memory(self, scope_id: str, artifact_id: str, kind: str,
                       text: str, retries: int = 2) -> int:
        """If-Match ETag 替换记忆内容，返回新 revision。412 时重读 ETag 重试。

        注意：1.4.1 的 ReplaceArtifactRequest（atomic-memory 分支）不接受
        `family` 字段（extra_forbidden），只传 content。
        """
        if len(text.encode("utf-8")) > MEMORY_TEXT_LIMIT:
            raise ValueError("记忆文本超过 8192 字节上限")
        body = {
            "content": {
                "schema": "powercontext.atomic-memory.v1",
                "kind": kind,
                "text": text,
            },
        }
        for attempt in range(retries):
            _, revision = self.get_memory(scope_id, artifact_id)
            resp = self._request(
                "PUT", f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}",
                json_body=body,
                headers={"If-Match": f'"revision:{revision}"'},
            )
            if resp.status_code == 200:
                data = json.loads(resp.text) if resp.text else {}
                return int(data.get("revision") or revision + 1)
            if resp.status_code == 412 and attempt < retries - 1:
                continue
            raise RuntimeError(
                f"PUT artifact {artifact_id} 返回 {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError("unreachable")

    def remember(self, scope_id: str, kind: str, text: str) -> Optional[tuple[str, int]]:
        """memory/remember 追加一条新记忆（不去重）。返回 (artifact_id, revision)。"""
        if len(text.encode("utf-8")) > MEMORY_TEXT_LIMIT:
            raise ValueError("记忆文本超过 8192 字节上限")
        data = self._ok_json(
            "POST", "/v1/memory/remember",
            json_body={"scope_id": scope_id, "kind": kind, "text": text},
        )
        records = data.get("records") or []
        for rec in records:
            artifact = rec.get("artifact") or {}
            if artifact.get("artifact_id"):
                return artifact["artifact_id"], int(artifact.get("revision") or 1)
        return None

    def list_memories(self, scope_id: str, kind: str, limit: int = 50) -> list[dict]:
        """按 kind 列出 active 原子记忆（不走带 tags 的缺陷接口）。"""
        data = self._ok_json(
            "POST", "/v1/atomic-memory/list",
            json_body={"scope_id": scope_id, "kind": kind, "limit": limit},
        )
        items = data.get("items") or data.get("memories") or []
        out = []
        for it in items:
            mem = it.get("memory") or it
            artifact = (it.get("artifact") or mem.get("artifact")
                        or mem.get("reference") or {})
            out.append({
                "artifact_id": artifact.get("artifact_id") or mem.get("artifact_id"),
                "revision": artifact.get("revision") or mem.get("revision"),
                "kind": mem.get("kind") or kind,
                "text": mem.get("text") or (mem.get("content") or {}).get("text") or "",
                "raw": it,
            })
        return out

    def get_revisions(self, scope_id: str, artifact_id: str) -> list[dict]:
        """历次 revision 列表（掌握度变化轨迹）。

        1.4.1 的列表接口只给 revision 号和 content_digest（无文本），
        每个 revision 的文本再单独 GET /revisions/{n}。
        """
        data = self._ok_json(
            "GET", f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/revisions",
            expected=(200, 201),
        )
        items = data.get("items") or []
        out = []
        for it in items:
            revision = it.get("revision")
            if revision is None:
                continue
            text = ""
            try:
                rev_data = self._ok_json(
                    "GET",
                    f"/v1/scopes/{scope_id}/artifacts/atomic-memory/"
                    f"{artifact_id}/revisions/{revision}",
                    expected=(200, 201),
                )
                content = rev_data.get("content") or {}
                text = content.get("text") or rev_data.get("text") or ""
            except (RuntimeError, json.JSONDecodeError):
                text = ""
            out.append({
                "revision": revision,
                "text": text,
                "created_at": it.get("created_at"),
            })
        out.sort(key=lambda r: int(r["revision"]))
        return out

    # ------------------------------------------------------------------- tags

    def get_tags(self, scope_id: str, artifact_id: str) -> list[str]:
        resp = self._request(
            "GET", f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/tags")
        if resp.status_code != 200:
            raise RuntimeError(f"GET tags 返回 {resp.status_code}: {resp.text[:300]}")
        data = json.loads(resp.text)
        return data.get("tags") or []

    def put_tags(self, scope_id: str, artifact_id: str, tags: list[str]) -> list[str]:
        """If-Match ETag 更新标签，返回新标签列表。"""
        for _ in range(3):
            resp = self._request(
                "GET", f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/tags")
            if resp.status_code != 200:
                raise RuntimeError(f"GET tags 返回 {resp.status_code}: {resp.text[:300]}")
            etag = resp.headers.get("ETag", "")
            put = self._request(
                "PUT", f"/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/tags",
                json_body={"tags": tags},
                headers={"If-Match": etag},
            )
            if put.status_code == 200:
                data = json.loads(put.text) if put.text else {}
                return data.get("tags") or tags
            if put.status_code == 412:
                continue
            raise RuntimeError(f"PUT tags 返回 {put.status_code}: {put.text[:300]}")
        raise RuntimeError("PUT tags: ETag 冲突重试次数耗尽")

    def query_by_tags(self, scope_id: str, tags: list[str],
                      families: Optional[list[str]] = None) -> list[dict]:
        """artifact-tags/query 按标签查找（规避 1.4.1 的 list/search tags 422 缺陷）。"""
        body: dict = {"tags": tags}
        if families:
            body["families"] = families
        data = self._ok_json(
            "POST", f"/v1/scopes/{scope_id}/artifact-tags/query", json_body=body)
        return data.get("items") or []

    # ---------------------------------------------------------------- handles

    def set_handle(self, scope_id: str, key: str, artifact_id: str, revision: int) -> None:
        self._ok_json(
            "PUT", f"/v1/scopes/{scope_id}/artifact-handles/atomic-memory/{key}",
            json_body={"artifact_id": artifact_id, "revision": revision},
            expected=(200, 201, 204),
        )

    def get_handle(self, scope_id: str, key: str) -> Optional[dict]:
        """按 handle 取记忆引用；还没有时返回 None（404）。"""
        resp = self._request(
            "GET", f"/v1/scopes/{scope_id}/artifact-handles/atomic-memory/{key}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RuntimeError(f"GET handle {key} 返回 {resp.status_code}: {resp.text[:300]}")
        data = json.loads(resp.text)
        ref = data.get("artifact") or data.get("reference") or data
        artifact = ref.get("artifact") or ref
        return {
            "artifact_id": artifact.get("artifact_id"),
            "revision": artifact.get("revision"),
        }

    # ---------------------------------------------------------------- context

    def bootstrap(self, scope_id: str, event_id: str,
                  max_bytes: int = 2000) -> dict:
        """会话开始时取回 bootstrap-context 记忆。"""
        return self._ok_json(
            "POST", "/v1/context/bootstrap",
            json_body={
                "scope_id": scope_id,
                "enabled": True,
                "lifecycle": "startup",
                "integration": "examradar",
                "event_id": event_id,
                "max_bytes": max_bytes,
            },
        )

    def prepare(self, scope_id: str, query: str, max_bytes: int = 2000) -> dict:
        """按问题准备上下文。query 必须短（知识点 id + 名称）以适配全文召回规则。"""
        return self._ok_json(
            "POST", "/v1/context/prepare",
            json_body={
                "scope_id": scope_id,
                "query": query,
                "max_bytes": max_bytes,
            },
        )

    # ------------------------------------------------------------------ misc

    def health(self) -> tuple[bool, str]:
        try:
            resp = self._request("GET", "/health/ready")
            return resp.status_code == 200, f"status={resp.status_code}"
        except PowerContextUnavailable as e:
            return False, str(e)


def _parse_etag(etag: str, prefix: str) -> int:
    """ETag 形如 "revision:3" / "tags:abc"。取 revision 数字。"""
    inner = etag.strip().strip('"')
    if inner.startswith(f"{prefix}:"):
        value = inner[len(prefix) + 1:]
        try:
            return int(value)
        except ValueError:
            pass
    raise RuntimeError(f"无法从 ETag {etag!r} 解析 {prefix}")


# ------------------------------------------------------------- content parse

def parse_prepared_content(content: str) -> list[dict]:
    """解析 context/prepare 的 content：BEGIN/END 之间是 JSON。

    返回 items 列表（记忆原文 + citation）。解析失败返回 []。
    """
    if not content:
        return []
    begin = content.find("BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1")
    end = content.find("END_POWERCONTEXT_PREPARED_CONTEXT_V1")
    if begin < 0 or end < 0 or end <= begin:
        return []
    start = begin + len("BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1")
    payload = content[start:end].strip()
    try:
        data = json.loads(payload)
    except Exception:
        return []
    items = data.get("items") or []
    out = []
    for it in items:
        out.append({
            "text": it.get("content") or "",
            "citation": it.get("citation") or {},
        })
    return out


def bootstrap_opening_line(bootstrap_result: dict) -> Optional[str]:
    """从 bootstrap 结果中取第一条可用记忆的第一行（复习计划的开场白）。

    返回 None 表示 bootstrap 为空 / 不可用。
    """
    if not bootstrap_result or bootstrap_result.get("status") != "ready":
        return None
    content = bootstrap_result.get("content") or ""
    if not content:
        return None
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(("BEGIN_", "END_", "(", ">", "#", "-")):
            continue
        if "POWERCONTEXT" in line:
            continue
        return line
    return None
