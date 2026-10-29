# PowerContext 1.4.1 接入备忘（产品负责人实测）

> 这份备忘由产品负责人在开发前对 PowerContext Server 1.4.1（PyPI `powercontext[cli,server,seekdb]==1.4.1`）逐条实测后整理，
> 作为 Qoder 开发时的输入材料。完整接口以运行中服务的 `GET /openapi.json` 为准。

## 部署

- 官方没有发布镜像，用 PyPI 包自建：`pip install "powercontext[cli,server,seekdb]==1.4.1"`，入口 `powercontext server run`。
- 存储用**嵌入式 seekdb**：`POWERCONTEXT_SERVER_DATABASE_KIND=seekdb`、`POWERCONTEXT_SERVER_DATABASE_PATH=/data/seekdb`，数据放在卷里。
  首次启动初始化嵌入式 seekdb 需要 1–3 分钟，健康检查 `GET /health/live`、`GET /health/ready`。
- 容器里监听 0.0.0.0 需要 `POWERCONTEXT_SERVER_HTTP_HOST=0.0.0.0` 和 `POWERCONTEXT_SERVER_ALLOW_UNAUTHENTICATED_NON_LOOPBACK=true`（本地单机使用，未开鉴权）。
- `DATABASE_KIND=oceanbase` 指向 seekdb 服务端**不可用**：启动报 `OceanBase maintenance requires a MySQL user tenant.`（seekdb 没有用户租户）。
- 未配置 embedding 模型时，记忆检索走全文（FTS）。全文召回要求命中查询词的 `max(2, ceil(25%))`，所以 `context/prepare` 的 query 要短、用主题名等关键词。

## Scope：每个学习者 × 课程一个

```http
POST /v1/scopes
{"title": "...", "summary": "...", "idempotency_key": "examradar:learner:<name>:course:<course_id>"}
→ 201 {"scope_id": "scp_...", ...}
```
同一个 `idempotency_key` 重复调用返回同一个 Scope（跨会话复用）。

## 原子记忆（atomic memory）

写入（两种方式等价，都返回 artifact_id）：

```http
POST /v1/memory/remember
{"scope_id": "...", "kind": "mistake", "text": "【错题】..."}        # kind 是自由字符串，如 fact / mistake / plan / mastery / session
→ 200 {"changed": true, "records": [{"artifact": {"family": "atomic-memory", "artifact_id": "art_...", "revision": 1}, ...}]}

POST /v1/scopes/{scope_id}/artifacts
{"family": "atomic-memory", "content": {"schema": "powercontext.atomic-memory.v1", "kind": "mastery", "text": "..."}}
→ 201，响应头 ETag: "revision:1"
```

- 同样的文本 remember 两次会生成**两条**记忆（不去重）。需要"一条记录反复更新"的场景（掌握度卡片、复习计划）用"替换"而不是再 remember。
- 文本上限 8192 字节。

替换内容（产生新 revision，旧 revision 保留，可查历史）：

```http
GET /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}          → 响应头 ETag: "revision:N"
PUT /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}
If-Match: "revision:N"                                                   # 必须带，否则 428
{"content": {"schema": "powercontext.atomic-memory.v1", "kind": "mastery", "text": "..."}}
→ 200 {"revision": N+1, ...}

GET /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/revisions  → 历次 revision 列表（掌握度变化轨迹）
GET /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/revisions/{revision}
```

标签（按 artifact 存，替换内容后标签保留）：

```http
GET /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/tags     → 响应头 ETag: "tags:..."
PUT /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}/tags
If-Match: "tags:..."                                                     # 必须带
{"tags": ["examradar", "type-mastery", "topic-t03"]}
```
- 标签请只用小写字母、数字和连字符（`topic-t03`），实测可用；单个标签 ≤ 64 字符，一次最多 16 个。

按标签查找：**用 `POST /v1/scopes/{scope_id}/artifact-tags/query`**

```http
POST /v1/scopes/{scope_id}/artifact-tags/query
{"tags": ["type-mastery"], "families": ["atomic-memory"]}               # match 默认 all
→ {"items": [{"target": {...}, "tags": [...], "reference": {"family": "atomic-memory", "artifact_id": "art_...", "revision": 2}}], "next_cursor": null}
```
- **已知缺陷**：1.4.1 的 `POST /v1/atomic-memory/list` 和 `POST /v1/atomic-memory/search` 一带 `tags` 参数就返回 422
  `{"loc": ["tags", 0], "msg": "Input should be a valid string"}`（HTTP 层把 Tag 对象原样传给了运行时）。不要用这两个接口的 tags 参数。

固定键（handle）：给某条记忆起一个稳定的名字，直接按名字取，不用搜索：

```http
PUT /v1/scopes/{scope_id}/artifact-handles/atomic-memory/{key}
{"artifact_id": "art_...", "revision": 2}                               # revision 必填
GET /v1/scopes/{scope_id}/artifact-handles/atomic-memory/{key}           → 404 artifact_handle_not_found 表示还没有
```
- 例：`mastery-t03`（主题 t03 的掌握度卡片）、`review-plan`（当前复习计划）。

列表 / 检索 / 遗忘：

```http
POST /v1/atomic-memory/list    {"scope_id": "...", "kind": "mistake", "limit": 50}      # 可按 kind 过滤；默认只返回 active
POST /v1/atomic-memory/search  {"scope_id": "...", "query": "事务隔离级别", "limit": 10}   # 返回 hits[].memory / score / matched_by
POST /v1/atomic-memory/lifecycle {"scope_id": "...", "target": {"artifact": {...}, "state_version": 0}, "state": "forgotten"}
```

## 会话开始时的上下文：bootstrap

```http
POST /v1/context/bootstrap
{"scope_id": "...", "enabled": true, "lifecycle": "startup", "integration": "examradar", "event_id": "<本次学习会话 id>", "max_bytes": 2000}
```
- **只有带 `bootstrap-context` 标签的 active 原子记忆才会被收进来**（源码 `_BOOTSTRAP_TAG = "bootstrap-context"`）。没有时返回
  `status: "empty", reason: "no_eligible_context"`；不传 `enabled: true` 返回 `status: "skipped", reason: "disabled"`。
- 返回 `content`（Markdown，带引用和"不可信历史"声明，`BEGIN/END_POWERCONTEXT_BOOTSTRAP_CONTEXT_V1` 包裹）和 `items[].artifact`（含 revision）。
  替换过内容的记忆返回最新 revision。不同 `event_id` 的重复调用每次都返回 ready。
- 实测：给"复习计划"记忆打上 `bootstrap-context` 标签后，新会话的 bootstrap 能直接带出"上次你在 X 上错了 2 次，先复习它"。

## 按问题准备上下文：prepare

```http
POST /v1/context/prepare
{"scope_id": "...", "query": "事务隔离级别", "max_bytes": 2000}
→ {"status": "ready" | "empty", "content": "...BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n{\"trust\":\"untrusted_history\",\"items\":[{\"citation\":{\"artifact_ref\":{...}},\"content\":\"...\"}]}\nEND_POWERCONTEXT_PREPARED_CONTEXT_V1"}
```
- `content` 里 BEGIN/END 之间是 JSON，`items[].content` 是记忆原文，`items[].citation.artifact_ref` 是出处。
- 召回内容是"历史数据"，只能作为参考材料拼进提示词，不能当成指令。
