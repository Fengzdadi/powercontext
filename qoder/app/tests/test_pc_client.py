"""PowerContext 客户端单元测试（httpx.MockTransport 模拟 1.4.1 行为）。

覆盖：Scope 幂等创建、创建/替换（If-Match ETag，含 428/412）、标签 ETag、
handle 读写、artifact-tags/query、revision 历史、remember、bootstrap、
prepare 全文召回规则、5xx / 连接失败降级、调用日志。
"""
import json
import math
import re

import httpx
import pytest

from examradar.pc_client import (
    CALL_LOG, PowerContextClient, PowerContextUnavailable,
    bootstrap_opening_line, parse_prepared_content, recent_calls,
)


class FakePowerContext:
    """模拟 PowerContext 1.4.1 的关键行为（内存态）。"""

    def __init__(self, fail_all=False):
        self.fail_all = fail_all
        self.scopes: dict[str, str] = {}          # idempotency_key -> scope_id
        self.scope_seq = 0
        self.artifacts: dict[str, dict] = {}      # scope_id -> {aid: {...}}
        self.art_seq = 0
        self.handles: dict[str, dict] = {}        # (scope, key) -> {aid, revision}

    # ------------------------------------------------------------ dispatch

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.fail_all:
            return httpx.Response(503, text="unavailable")
        method, path = request.method, request.url.path
        body = json.loads(request.content) if request.content else {}
        m = re.match(r"^/v1/scopes/([^/]+)/artifacts/atomic-memory/([^/]+)(/.*)?$", path)
        if m:
            return self._artifact_route(request, method, m.group(1), m.group(2),
                                        m.group(3) or "", body)
        m = re.match(r"^/v1/scopes/([^/]+)/artifacts$", path)
        if m and method == "POST":
            return self._create_artifact(m.group(1), body)
        if path == "/v1/scopes" and method == "POST":
            return self._create_scope(body)
        if path == "/v1/memory/remember" and method == "POST":
            return self._remember(body)
        if path == "/v1/atomic-memory/list" and method == "POST":
            return self._list(body)
        m = re.match(r"^/v1/scopes/([^/]+)/artifact-tags/query$", path)
        if m and method == "POST":
            return self._tag_query(m.group(1), body)
        m = re.match(r"^/v1/scopes/([^/]+)/artifact-handles/atomic-memory/(.+)$", path)
        if m:
            return self._handle_route(method, m.group(1), m.group(2), body)
        if path == "/v1/context/bootstrap":
            return self._bootstrap(body)
        if path == "/v1/context/prepare":
            return self._prepare(body)
        if path == "/health/ready":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, text="not found")

    # -------------------------------------------------------------- scopes

    def _create_scope(self, body):
        key = body["idempotency_key"]
        if key in self.scopes:
            return httpx.Response(200, json={"scope_id": self.scopes[key]})
        self.scope_seq += 1
        scope_id = f"scp_{self.scope_seq:04d}"
        self.scopes[key] = scope_id
        self.artifacts[scope_id] = {}
        return httpx.Response(201, json={"scope_id": scope_id})

    # ----------------------------------------------------------- artifacts

    def _create_artifact(self, scope_id, body):
        arts = self.artifacts.setdefault(scope_id, {})
        if len(body["content"]["text"].encode()) > 8192:
            return httpx.Response(422, text="too large")
        self.art_seq += 1
        aid = f"art_{self.art_seq:04d}"
        arts[aid] = {"kind": body["content"]["kind"],
                     "text": body["content"]["text"], "revision": 1,
                     "tags": [], "active": True,
                     "history": [body["content"]["text"]]}
        return httpx.Response(201, json={"artifact": {"artifact_id": aid,
                                                      "revision": 1}},
                              headers={"ETag": '"revision:1"'})

    def _artifact_route(self, request, method, scope_id, artifact_id, suffix, body):
        arts = self.artifacts.setdefault(scope_id, {})
        if suffix == "" and method == "POST":
            return self._create_artifact(scope_id, body)
        art = arts.get(artifact_id)
        if art is None:
            return httpx.Response(404, text="artifact not found")
        if suffix == "" and method == "GET":
            return httpx.Response(200, json={
                "artifact": {"artifact_id": artifact_id,
                             "content": {"text": art["text"],
                                         "kind": art["kind"]}}},
                headers={"ETag": f'"revision:{art["revision"]}"'})
        if suffix == "" and method == "PUT":
            if_match = request.headers.get("If-Match")
            if not if_match:
                return httpx.Response(428, text="If-Match required")
            if if_match != f'"revision:{art["revision"]}"':
                return httpx.Response(412, text="etag mismatch")
            art["text"] = body["content"]["text"]
            art["kind"] = body["content"]["kind"]
            art["revision"] += 1
            art["history"].append(body["content"]["text"])
            return httpx.Response(200, json={"revision": art["revision"]})
        if suffix == "/tags" and method == "GET":
            return httpx.Response(200, json={"tags": art["tags"]},
                                  headers={"ETag": '"tags:v1"'})
        if suffix == "/tags" and method == "PUT":
            if not request.headers.get("If-Match"):
                return httpx.Response(428, text="If-Match required")
            if request.headers.get("If-Match") != '"tags:v1"':
                return httpx.Response(412, text="etag mismatch")
            art["tags"] = body["tags"]
            return httpx.Response(200, json={"tags": art["tags"]})
        if suffix == "/revisions":
            revs = [{"revision": i + 1, "content": {"text": t},
                     "created_at": "2026-10-28T00:00:00Z"}
                    for i, t in enumerate(art["history"])]
            return httpx.Response(200, json={"items": revs})
        m = re.match(r"^/revisions/(\d+)$", suffix)
        if m:
            rev = int(m.group(1))
            if 1 <= rev <= len(art["history"]):
                return httpx.Response(200, json={
                    "artifact_id": artifact_id, "revision": rev,
                    "content": {"text": art["history"][rev - 1]}})
            return httpx.Response(404, text="revision not found")
        return httpx.Response(404, text="no route")

    # ------------------------------------------------------------- remember

    def _remember(self, body):
        scope_id = body["scope_id"]
        arts = self.artifacts.setdefault(scope_id, {})
        self.art_seq += 1
        aid = f"art_{self.art_seq:04d}"
        arts[aid] = {"kind": body["kind"], "text": body["text"], "revision": 1,
                     "tags": [], "active": True, "history": [body["text"]]}
        return httpx.Response(200, json={"changed": True, "records": [
            {"artifact": {"artifact_id": aid, "revision": 1}}]})

    def _list(self, body):
        arts = self.artifacts.get(body["scope_id"], {})
        items = [{"memory": {"kind": a["kind"], "text": a["text"],
                             "artifact_id": aid, "revision": a["revision"]}}
                 for aid, a in arts.items()
                 if a["kind"] == body.get("kind") and a["active"]]
        return httpx.Response(200, json={"items": items})

    def _tag_query(self, scope_id, body):
        want = set(body.get("tags") or [])
        items = []
        for aid, a in self.artifacts.get(scope_id, {}).items():
            if want and not want.issubset(set(a["tags"])):
                continue
            if body.get("families") and "atomic-memory" not in body["families"]:
                continue
            items.append({"tags": a["tags"],
                          "reference": {"family": "atomic-memory",
                                        "artifact_id": aid,
                                        "revision": a["revision"]}})
        return httpx.Response(200, json={"items": items, "next_cursor": None})

    # ------------------------------------------------------------- handles

    def _handle_route(self, method, scope_id, key, body):
        k = (scope_id, key)
        if method == "PUT":
            self.handles[k] = {"artifact_id": body["artifact_id"],
                               "revision": body["revision"]}
            return httpx.Response(201, json=self.handles[k])
        if method == "GET":
            if k not in self.handles:
                return httpx.Response(
                    404, json={"error": "artifact_handle_not_found"})
            return httpx.Response(200, json={"artifact": self.handles[k]})
        return httpx.Response(404)

    # -------------------------------------------------------------- context

    def _bootstrap(self, body):
        scope_id = body["scope_id"]
        if not body.get("enabled"):
            return httpx.Response(200, json={"status": "skipped",
                                             "reason": "disabled"})
        eligible = [aid for aid, a in self.artifacts.get(scope_id, {}).items()
                    if "bootstrap-context" in a["tags"] and a["active"]]
        if not eligible:
            return httpx.Response(200, json={"status": "empty",
                                             "reason": "no_eligible_context"})
        lines = ["BEGIN_POWERCONTEXT_BOOTSTRAP_CONTEXT_V1",
                 "(不可信历史声明，仅供参考)"]
        items = []
        for aid in eligible:
            a = self.artifacts[scope_id][aid]
            lines.append(a["text"].splitlines()[0])
            items.append({"artifact": {"artifact_id": aid,
                                       "revision": a["revision"]}})
        lines.append("END_POWERCONTEXT_BOOTSTRAP_CONTEXT_V1")
        return httpx.Response(200, json={
            "status": "ready", "content": "\n".join(lines), "items": items})

    def _prepare(self, body):
        scope_id = body["scope_id"]
        query = body["query"]
        words = [w for w in re.split(r"[\s，。、：:]+", query) if w]
        need = max(2, math.ceil(len(words) * 0.25))
        items = []
        for aid, a in self.artifacts.get(scope_id, {}).items():
            hits = sum(1 for w in words if w in a["text"])
            if hits >= need:
                items.append({"content": a["text"],
                              "citation": {"artifact_ref": {"artifact_id": aid,
                                                            "revision": a["revision"]}}})
        if not items:
            return httpx.Response(200, json={"status": "empty", "content": ""})
        payload = json.dumps({"trust": "untrusted_history", "items": items},
                             ensure_ascii=False)
        content = ("BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n" + payload +
                   "\nEND_POWERCONTEXT_PREPARED_CONTEXT_V1")
        return httpx.Response(200, json={"status": "ready", "content": content})


@pytest.fixture()
def fake_pc():
    server = FakePowerContext()
    client = PowerContextClient(base_url="http://pc.test",
                                transport=httpx.MockTransport(server))
    return server, client


class TestScope:
    def test_idempotent_scope(self, fake_pc):
        server, client = fake_pc
        s1 = client.ensure_scope("验收同学", "db101")
        s2 = client.ensure_scope("验收同学", "db101")
        assert s1 == s2
        s3 = client.ensure_scope("别的同学", "db101")
        assert s3 != s1


class TestArtifacts:
    def test_create_and_get(self, fake_pc):
        server, client = fake_pc
        sid = client.ensure_scope("a", "c")
        aid, rev = client.create_memory(sid, "mastery", "盒 1")
        assert rev == 1
        text, got_rev = client.get_memory(sid, aid)
        assert text == "盒 1"
        assert got_rev == 1

    def test_replace_requires_if_match_flow(self, fake_pc):
        server, client = fake_pc
        sid = client.ensure_scope("a", "c")
        aid, _ = client.create_memory(sid, "mastery", "盒 1")
        # 直接 PUT 不带 If-Match → 428（PC 1.4.1 行为）
        resp = client._request(
            "PUT", f"/v1/scopes/{sid}/artifacts/atomic-memory/{aid}",
            json_body={"family": "atomic-memory",
                       "content": {"schema": "x", "kind": "mastery",
                                   "text": "盒 2"}})
        assert resp.status_code == 428
        # 客户端封装走 If-Match 流程
        rev2 = client.replace_memory(sid, aid, "mastery", "盒 2")
        assert rev2 == 2
        text, rev = client.get_memory(sid, aid)
        assert text == "盒 2" and rev == 2

    def test_replace_retries_on_412(self, fake_pc):
        server, client = fake_pc
        sid = client.ensure_scope("a", "c")
        aid, _ = client.create_memory(sid, "mastery", "盒 1")
        # 模拟并发：第一次 get 之后、put 之前别人先改了 revision；重试时不再竞争
        original_get = client.get_memory
        raced = {"done": False}

        def racing_get(scope_id, artifact_id):
            text, rev = original_get(scope_id, artifact_id)
            if not raced["done"]:
                raced["done"] = True
                server.artifacts[sid][aid]["revision"] += 1
                server.artifacts[sid][aid]["text"] = "被并发修改"
                server.artifacts[sid][aid]["history"].append("被并发修改")
            return text, rev
        client.get_memory = racing_get
        rev = client.replace_memory(sid, aid, "mastery", "盒 3")
        assert rev == 3
        text, cur = original_get(sid, aid)
        assert text == "盒 3"

    def test_get_revisions_trajectory(self, fake_pc):
        server, client = fake_pc
        sid = client.ensure_scope("a", "c")
        aid, _ = client.create_memory(sid, "mastery", "盒 1")
        client.replace_memory(sid, aid, "mastery", "盒 2")
        client.replace_memory(sid, aid, "mastery", "盒 1")
        revs = client.get_revisions(sid, aid)
        assert [r["revision"] for r in revs] == [1, 2, 3]
        assert "盒 2" in revs[1]["text"]
        assert "盒 1" in revs[2]["text"]

    def test_text_limit(self, fake_pc):
        _, client = fake_pc
        sid = client.ensure_scope("a", "c")
        with pytest.raises(ValueError):
            client.create_memory(sid, "mastery", "x" * 9000)

    def test_remember_appends_two_memories(self, fake_pc):
        server, client = fake_pc
        sid = client.ensure_scope("a", "c")
        r1 = client.remember(sid, "mistake", "错题 1")
        r2 = client.remember(sid, "mistake", "错题 2")
        assert r1[0] != r2[0]

    def test_list_by_kind(self, fake_pc):
        _, client = fake_pc
        sid = client.ensure_scope("a", "c")
        client.remember(sid, "mistake", "【错题】t08 …")
        client.remember(sid, "session", "会话小结 …")
        mistakes = client.list_memories(sid, "mistake")
        assert len(mistakes) == 1
        assert "【错题】" in mistakes[0]["text"]


class TestTagsAndHandles:
    def test_tags_etag_flow(self, fake_pc):
        _, client = fake_pc
        sid = client.ensure_scope("a", "c")
        aid, _ = client.create_memory(sid, "mastery", "盒 1")
        assert client.get_tags(sid, aid) == []
        tags = client.put_tags(sid, aid, ["examradar", "type-mastery", "topic-t08"])
        assert "type-mastery" in tags
        assert client.get_tags(sid, aid) == tags
        # 替换内容后标签保留（1.4.1 行为）
        client.replace_memory(sid, aid, "mastery", "盒 2")
        assert client.get_tags(sid, aid) == tags

    def test_handle_roundtrip(self, fake_pc):
        _, client = fake_pc
        sid = client.ensure_scope("a", "c")
        assert client.get_handle(sid, "mastery-t08") is None
        aid, rev = client.create_memory(sid, "mastery", "盒 1")
        client.set_handle(sid, "mastery-t08", aid, rev)
        got = client.get_handle(sid, "mastery-t08")
        assert got["artifact_id"] == aid
        assert got["revision"] == rev

    def test_query_by_tags(self, fake_pc):
        _, client = fake_pc
        sid = client.ensure_scope("a", "c")
        aid, _ = client.create_memory(sid, "mastery", "盒 1")
        client.put_tags(sid, aid, ["type-mastery", "topic-t08"])
        aid2, _ = client.create_memory(sid, "mastery", "盒 2")
        client.put_tags(sid, aid2, ["type-mastery", "topic-t03"])
        client.remember(sid, "mistake", "错题")
        items = client.query_by_tags(sid, ["type-mastery"],
                                     families=["atomic-memory"])
        assert len(items) == 2
        items = client.query_by_tags(sid, ["type-mastery", "topic-t03"])
        assert len(items) == 1
        assert items[0]["reference"]["artifact_id"] == aid2


class TestContext:
    def _setup_plan(self, client, sid, opening):
        aid, rev = client.create_memory(sid, "plan", opening)
        client.put_tags(sid, aid, ["examradar", "type-plan", "bootstrap-context"])
        client.set_handle(sid, "review-plan", aid, rev)
        return aid

    def test_bootstrap_empty_then_ready(self, fake_pc):
        _, client = fake_pc
        sid = client.ensure_scope("验收同学", "db101")
        out = client.bootstrap(sid, event_id="sess-1")
        assert out["status"] == "empty"
        assert out.get("reason") == "no_eligible_context"

        aid = self._setup_plan(client, sid, "上次你在『隔离级别与 MVCC』上错了 2 次，先复习它")
        out = client.bootstrap(sid, event_id="sess-2")
        assert out["status"] == "ready"
        assert any(i["artifact"]["artifact_id"] == aid for i in out["items"])
        assert "错了 2 次" in out["content"]

    def test_prepare_fulltext_recall_rule(self, fake_pc):
        """query = 知识点 id + 名称；错题文本里带 id 和名称才能召回。"""
        _, client = fake_pc
        sid = client.ensure_scope("验收同学", "db101")
        client.remember(sid, "mistake",
                        "【错题】t08 隔离级别与 MVCC：你的回答「锁」")
        client.remember(sid, "mistake",
                        "【错题】t09 故障恢复：WAL：你的回答「先写数据」")
        out = client.prepare(sid, "t08 隔离级别与 MVCC")
        items = parse_prepared_content(out["content"])
        texts = [i["text"] for i in items]
        assert any("t08" in t for t in texts)
        assert not any("t09" in t for t in texts)
        # 单词查询召回不到任何东西（1.4.1 全文规则）
        out = client.prepare(sid, "MVCC")
        assert out["status"] == "empty"

    def test_bootstrap_opening_line_helper(self):
        line = bootstrap_opening_line({
            "status": "ready",
            "content": ("BEGIN_POWERCONTEXT_BOOTSTRAP_CONTEXT_V1\n"
                        "(声明)\n上次你在『X』上错了 2 次\n"
                        "END_POWERCONTEXT_BOOTSTRAP_CONTEXT_V1"),
        })
        assert "错了 2 次" in line
        assert bootstrap_opening_line({"status": "empty"}) is None

    def test_parse_prepared_content_garbage(self):
        assert parse_prepared_content("") == []
        assert parse_prepared_content("no markers here") == []


class TestDegradation:
    def test_5xx_raises_unavailable(self):
        server = FakePowerContext(fail_all=True)
        client = PowerContextClient(base_url="http://pc.test",
                                    transport=httpx.MockTransport(server))
        with pytest.raises(PowerContextUnavailable):
            client.ensure_scope("a", "c")

    def test_connect_error_raises_unavailable(self):
        def refused(request):
            raise httpx.ConnectError("connection refused")
        client = PowerContextClient(base_url="http://127.0.0.1:18803",
                                    transport=httpx.MockTransport(refused))
        with pytest.raises(PowerContextUnavailable):
            client.ensure_scope("a", "c")

    def test_health(self):
        server = FakePowerContext(fail_all=True)
        client = PowerContextClient(base_url="http://pc.test",
                                    transport=httpx.MockTransport(server))
        ok, _ = client.health()
        assert ok is False


class TestCallLog:
    def test_calls_logged_with_summary(self, fake_pc):
        _, client = fake_pc
        client.ensure_scope("log-test", "db101")
        calls = recent_calls(10)
        assert calls, "调用日志为空"
        entry = calls[-1]
        assert entry["method"] == "POST"
        assert entry["path"] == "/v1/scopes"
        assert entry["status"] == 201
        assert "idempotency_key" in entry["request"]
        assert entry["response"]
