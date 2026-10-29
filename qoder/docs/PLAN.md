# ExamRadar 技术设计（PLAN）

> 基于 `docs/BRIEF.md`、`docs/reference/powercontext-1.4.1-notes.md`、`docs/reference/seekdb-1.4-notes.md`。
> `samples/` 尚未交付；涉及示例数据处均为假设，待 samples 到位后校准阈值。

---

## 1. 需求拆解（用户故事 + 验收标准）

| ID | 用户故事 | 验收标准 |
|----|----------|----------|
| US1.1 | 上传 PDF/Markdown 资料并选类型 | ≤30s 切块入库；`documents` + `chunks` 有记录；前端显示块数 |
| US1.2 | 输入问题，得到带出处的段落 | 每段含 `file/page/heading`；无结果返回空数组 |
| US1.3 | 配 LLM 时返回引用式回答 | `[n]` 对应段落；无 LLM 退化为原文列表 |
| US2.1 | 粘贴考试范围 | 解析为 N 个知识点，前端可编辑 |
| US2.2 | 看到覆盖雷达图 | ECharts 雷达图；两圈：覆盖度 + 考试权重 |
| US2.3 | 看到盲区排序 | 按 `权重×(1-覆盖度)` 降序；可展开看证据 |
| US2.4 | 判定可解释 | 点击知识点弹出支撑段落（含 `_score`、rank） |
| US3.1 | 针对薄弱知识点出题 | 题目含出处；优先 thin/missing + 到期复习 |
| US3.2 | 提交答案得到对错+解析 | 选择/填空精确匹配；简答有 LLM 则点评，无则给参考答案 |
| US3.3 | 判分后自动更新掌握度 | mastery revision +1；错题写入 mistake |
| US3.4 | 新会话首页显示"上次你…" | bootstrap content 非空；首页渲染个性化提示 |
| US3.5 | 进入知识点召回历史错题 | prepare 返回该知识点 mistake 记忆 |
| US3.6 | 查看掌握度卡片和错题 | 页面列 mastery（含 revision 历史）和 mistake |
| US4.1 | 每次操作自动记录 | 事件写入 `usage_events`；`source=real/auto` |
| US4.2 | 使用记录页面展示统计 | 会话数、累计时长、检索/答题次数、正确率折线 |
| US4.3 | 导出 CSV/JSON | 内容与统计一致；auto 默认排除 |

---

## 2. 架构

### 2.1 目录结构

```
qoder/
├── app/examradar/          # Python 包：config, main, seekdb_client, pc_client,
│   │                       #   embedding, chunker, search, coverage, quiz,
│   │                       #   scoring, mastery, memory, usage
│   ├── routes/             # documents, search, coverage, quiz, sessions, memory, usage
│   └── static/             # index/import/ask/radar/quiz/memory/usage.html,
│                           #   lib/echarts.min.js, css/, js/
├── samples/                # 产品负责人提供
├── scripts/                # e2e_verify.py, calibrate.py
├── docker/                 # Dockerfile.app, Dockerfile.powercontext
├── docker-compose.yml      # 三服务
├── docker-compose.dev.yml  # 只起 seekdb + powercontext
├── .env.example
├── docs/  dev-records/     # 不动
```

### 2.2 三服务关系

- **seekdb**（:10800）：课程知识库 — 资料切块存储、混合检索、覆盖度打分、使用记录
- **PowerContext**（:18801）：学习者记忆 — 掌握度卡片、错题、复习计划、会话小结（内嵌 seekdb 存储）
- **ExamRadar**（:18800）：业务编排，无状态；HTTP 调 PowerContext，MySQL 协议调 seekdb

### 2.3 主要请求流程

**导入**：POST `/api/documents` → chunker 切块（MD 按标题层级/PDF 按页/exam PDF 按题号+分值/TXT 按段落）→ embedding 向量化 → INSERT documents + chunks → 记录 event=import

**问笔记**：POST `/api/search` → 向量化 query → `DBMS_HYBRID_SEARCH.SEARCH` RRF 融合 → 有 LLM 生成引用式回答 / 无 LLM 返回段落 → 记录 event=search

**覆盖雷达**：POST `/api/coverage/analyze` → 每个 topic 两次检索：①notes/slides/paper → 覆盖度 ②exam → 考试权重 → 判定 covered/thin/missing + 盲区排序 → 记录 event=coverage

**出题判分**：POST `/api/quiz/generate` → prepare 召回历史错题 → 检索原文 → 有 LLM 生成 / 无 LLM 挖空 → POST `/api/quiz/submit` → 判分 → mastery 替换 + 写错题 + 更新 plan → 记录 event=answer

**会话**：start → bootstrap → 个性化提示；end → 计算时长 → 写 session 小结 → 更新 usage

---

## 3. seekdb 数据模型

### 3.1 DDL

```sql
CREATE TABLE documents (
  id          BIGINT PRIMARY KEY,
  course_id   VARCHAR(64) NOT NULL,
  name        VARCHAR(256) NOT NULL,
  doc_kind    VARCHAR(16) NOT NULL,   -- notes/slides/exam/paper
  file_type   VARCHAR(8),             -- md/pdf/txt
  sha256      CHAR(64),               -- 内容哈希，用于去重
  chunk_count INT DEFAULT 0,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_course (course_id),
  UNIQUE INDEX idx_sha256 (sha256)
) ORGANIZATION HEAP;

CREATE TABLE chunks (
  id          BIGINT PRIMARY KEY,
  document_id BIGINT NOT NULL,
  course_id   VARCHAR(64) NOT NULL,
  doc_kind    VARCHAR(16) NOT NULL,
  content     TEXT NOT NULL,
  heading     TEXT,                    -- MD 标题路径 / PDF 页标题
  page        INT,                     -- PDF 页码
  question_no INT,                     -- exam 题号
  points      DECIMAL(5,1),            -- exam 分值（分）
  chunk_index INT,
  embedding   VECTOR(512),
  VECTOR INDEX idx_emb (embedding) WITH (distance=cosine, type=hnsw, sync_mode=immediate),
  FULLTEXT INDEX ft_content (content) WITH PARSER ik,
  INDEX idx_course_kind (course_id, doc_kind)
) ORGANIZATION HEAP;

CREATE TABLE usage_events (
  id          BIGINT PRIMARY KEY,
  session_id  VARCHAR(64),
  course_id   VARCHAR(64),
  source      VARCHAR(16) NOT NULL,   -- real / auto
  event       VARCHAR(32) NOT NULL,
  payload     TEXT,                    -- JSON
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_session (session_id),
  INDEX idx_course_source (course_id, source)
) ORGANIZATION HEAP;
```

**要点**：全部 `ORGANIZATION HEAP`；`sync_mode=immediate` 写完即可搜；`PARSER ik` 中文分词；主键 BIGINT 应用层生成（堆表不支持 AUTO_INCREMENT + 用户主键）。

### 3.2 查询模板

**混合检索**（问笔记 / 覆盖度通用，`doc_kind` 按需调整）：

```json
{"query":{"bool":{"must":[{"match":{"content":"<escaped_query>"}}],
  "filter":[{"term":{"course_id":"<cid>"}},{"terms":{"doc_kind":["notes","slides"]}}]}},
 "knn":{"field":"embedding","k":20,"query_vector":[...],
  "filter":[{"term":{"course_id":"<cid>"}},{"terms":{"doc_kind":["notes","slides"]}}]},
 "rank":{"rrf":{}},
 "_source":["id","document_id","content","heading","page",
            "_keyword_score","_semantic_score","_keyword_rank","_semantic_rank"],
 "size":10}
```

考试权重：同上但 `doc_kind: ["exam"]`，`size: 20`。

调试用 `SELECT DBMS_HYBRID_SEARCH.GET_SQL('chunks', '<JSON>')` 获取实际 SQL。

**使用统计**：`SELECT event, COUNT(*) FROM usage_events WHERE course_id=%s AND source='real' GROUP BY event`

---

## 4. 覆盖度判定算法

### 4.1 覆盖度分数

对每个知识点，检索 notes/slides/paper top-5：

```
sem_max  = max(h._semantic_score for h in hits)     # cosine: (1+cos)/2, ∈[0,1]
kw_count = sum(1 for h in hits if h._keyword_score > 0)
coverage_score = 0.6 * sem_max + 0.4 * min(kw_count / 3, 1.0)
```

> **注意**：cosine 索引下 `_semantic_score = (1+cos)/2`，bge-small-zh 模型下不相关文本也常有 0.6 以上的语义分，M2 校准阈值时需注意区分信号与噪声（本会话不做覆盖度校准）。

### 4.2 判定规则

| 等级 | 条件 | 默认阈值 |
|------|------|----------|
| `covered` | `coverage_score ≥ T_covered` | 0.55 |
| `thin` | `T_thin ≤ score < T_covered` | 0.20 |
| `missing` | `score < T_thin` | — |

阈值待 samples 校准：`scripts/calibrate.py` 遍历阈值组合，以人工标注为真值选 F1 最高组。

### 4.3 考试权重

```
exam_hits = 检索 exam top-20
parsed_points = sum(parse_points(h.content) for h in exam_hits)  # 解析"（10分）"等
exam_weight = min(parsed_points / max_total_points, 1.0)  # 无分值时: min(len/5, 1.0)
```

### 4.4 盲区排序

`blind_score = exam_weight * (1 - coverage_score)` 降序（高权重 + 低覆盖 = 最大盲区）。

---

## 5. PowerContext 记忆模型

### 5.1 Scope

`idempotency_key = "examradar:learner:{name}:course:{course_id}"` — 每学习者×课程一个，跨会话复用。

### 5.2 记忆类型

| kind | 标签 | handle | 写/替换 | 文本格式 |
|------|------|--------|---------|----------|
| `mastery` | `examradar`, `type-mastery`, `topic-{id}` | `mastery-{id}` | 替换 | `[MASTERY] topic_id=t03 topic_name=事务隔离级别\nbox=2 correct=3 wrong=2 next_review=2026-10-30\nlast_seen=2026-10-28 last_result=wrong` |
| `mistake` | `examradar`, `type-mistake`, `topic-{id}` | 无 | 新增 | `[MISTAKE] topic_id=t03\nQ: ...\nA_student: ...\nA_correct: ...\nSource: 笔记·3.2节` |
| `plan` | `examradar`, `type-plan`, **`bootstrap-context`** | `review-plan` | 替换 | `[PLAN] updated=2026-10-28\ndue_now: t03(事务隔离级别)\nweak: t05(范式)\nnext_suggested: t03` |
| `session` | `examradar`, `type-session` | 无 | 新增 | 自由文本 |

### 5.3 读写时机

| 时机 | 操作 |
|------|------|
| 会话开始 | `POST /v1/context/bootstrap`（`event_id`=session_id, `max_bytes:2000`）→ 渲染首页 |
| 进入知识点 | `POST /v1/context/prepare`（`query`=知识点名, `max_bytes:1500`）→ 拼入出题 prompt |
| 答对 | 替换 mastery（box+1, correct+1, next_review） |
| 答错 | 替换 mastery（box=max(1,box-1), wrong+1）+ 新增 mistake |
| 判分后 | 替换 plan（重算 due_now/weak/next_suggested） |
| 会话结束 | 新增 session 小结 |

### 5.4 对 1.4.1 缺陷的规避

| 缺陷 | 规避 |
|------|------|
| `atomic-memory/list` 和 `search` 带 tags 返回 422 | 按标签查找统一用 `artifact-tags/query` |
| 同样文本 remember 两次生成两条 | mastery/plan 用 PUT 替换，不用 remember |
| 无 embedding 时 FTS 要求命中 `max(2, ceil(25%))` | prepare query 用短关键词 |
| 标签只允许小写+数字+连字符 | 格式 `type-mastery`、`topic-t03` |

---

## 6. 出题与判分

| | 有 LLM | 无 LLM |
|---|---------|--------|
| 出题 | 检索原文+历史错题 → chat completions | 检索原文 → 规则挖空关键术语 |
| 题型 | 选择/填空/简答 | 仅填空 |
| 判分 | 选择精确匹配；简答 LLM 点评 | 选择/填空精确匹配（忽略首尾空白） |

**出题优先级**：①到期复习（`next_review ≤ today`）→ ②thin → ③missing → ④轮转

**出处**：每道题 `source` = top-1 chunk 的 `{document_name} · {page or heading}`

**Leitner 参数**：

| 盒号 | 1 | 2 | 3 | 4 | 5 |
|------|---|---|---|---|---|
| 间隔(天) | 1 | 2 | 4 | 7 | 14 |

答对 box=min(5,box+1)；答错 box=1（回到 1 号盒，经典 Leitner 做法）；`next_review=today+interval[box]`；初始 box=1。

---

## 7. 使用记录

| event | payload |
|-------|---------|
| `session_start` | `{session_id, course_id, learner}` |
| `session_end` | `{session_id, duration_seconds, questions_asked, questions_correct}` |
| `import` | `{document_id, doc_kind, chunk_count}` |
| `search` | `{query, top_k, result_count}` |
| `coverage` | `{topic_count, covered, thin, missing}` |
| `question` | `{question_id, topic_id, question_type, source_doc}` |
| `answer` | `{question_id, topic_id, correct, box_before, box_after}` |

- **时长**：`session_end.created_at - session_start.created_at`（服务端计算）
- **区分**：`source="real"` 正常操作；`source="auto"` 验证脚本；统计默认排除 auto
- **导出**：CSV（`session_id,event,payload,created_at`）或 JSON；默认排除 auto

---

## 8. HTTP API + 前端页面

### 8.1 API

| 方法 | 路径 | 要点 |
|------|------|------|
| POST | `/api/documents` | multipart: file, course_id, doc_kind → `{document_id, chunk_count}` |
| GET | `/api/documents?course_id=` | → `[{id, name, doc_kind, chunk_count}]` |
| POST | `/api/search` | `{query, course_id, doc_kinds?, top_k?}` → 带出处的段落 |
| POST | `/api/coverage/analyze` | `{course_id, topics:[{id,name}]}` → 覆盖度+盲区 |
| POST | `/api/sessions/start` | `{course_id, learner}` → `{session_id, bootstrap_content}` |
| POST | `/api/sessions/end` | `{session_id}` → `{duration_seconds, summary}` |
| POST | `/api/quiz/generate` | `{session_id, course_id, topic_id}` → 题目+出处 |
| POST | `/api/quiz/submit` | `{question_id, answer}` → 对错+解析 |
| GET | `/api/memory/mastery` | scope_id+topic_id → 卡片+revision 历史 |
| GET | `/api/memory/mistakes` | scope_id+topic_id → 错题列表 |
| GET | `/api/memory/plan` | scope_id → 复习计划 |
| GET | `/api/usage/stats` | course_id+source → 统计 |
| GET | `/api/usage/export` | format=csv/json → 文件下载 |

### 8.2 前端页面

| 页面 | 功能 |
|------|------|
| `/` (index.html) | bootstrap 个性化提示 + 快捷入口 |
| `/import.html` | 上传资料 + 列表 |
| `/ask.html` | 搜索框 + 带出处结果 |
| `/radar.html` | 考试范围输入 → 雷达图 + 盲区清单 |
| `/quiz.html` | 做题 + 判分 + 下一题 |
| `/memory.html` | 掌握度卡片 + 错题 + 复习计划 |
| `/usage.html` | 统计图表 + 导出 |

---

## 9. 配置 + 部署

### 9.1 环境变量（`.env.example`）

```bash
SEEKDB_HOST=seekdb          SEEKDB_PORT=2881        SEEKDB_USER=root
SEEKDB_PASSWORD=change-me    SEEKDB_HOST_PORT=10800
POWERCONTEXT_URL=http://powercontext:8000
POWERCONTEXT_SERVER_DATABASE_PATH=/data/seekdb      POWERCONTEXT_HOST_PORT=18801
APP_HOST=0.0.0.0          APP_PORT=18800
CORS_ORIGINS=http://localhost:18800
EMBEDDING_PROVIDER=local   EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5   EMBEDDING_DIM=512
# EMBEDDING_BASE_URL=      EMBEDDING_API_KEY=         # 仅 openai
# LLM_BASE_URL=            LLM_API_KEY=               LLM_MODEL=    # 可选
COVERAGE_T_COVERED=0.55    COVERAGE_T_THIN=0.20
LEITNER_INTERVALS=1,2,4,7,14
```

### 9.2 docker compose

三个服务：seekdb（镜像 `oceanbase/seekdb:1.4.0-...`）、powercontext（自建镜像，`POWERCONTEXT_SERVER_DATABASE_KIND=seekdb`）、app（自建镜像）。

- **容器网络地址**：compose 里 app 访问其他服务使用容器内部端口——`SEEKDB_HOST=seekdb`、`SEEKDB_PORT=2881`、`POWERCONTEXT_URL=http://powercontext:8000`（18801 是宿主机映射端口，容器内 PowerContext 监听 8000）。`SEEKDB_HOST/PORT` 和 `POWERCONTEXT_URL` 在 compose 里直接写容器网络地址；`.env` 只提供密码、宿主机映射端口和可选的模型配置。
- seekdb healthcheck: `mysqladmin ping`，interval 10s，retries 10
- powercontext healthcheck: `curl /health/ready`，interval 15s，retries 20（首次初始化 1-3 分钟）
- app depends_on seekdb + powercontext healthy
- 本地开发：`docker compose -f docker-compose.dev.yml up`（只起基础设施）+ `uv run uvicorn examradar.main:app --reload`
- 向量模型预下载：`Dockerfile.app` 中 `RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-zh-v1.5')"`

---

## 10. 测试策略

### 10.1 单元测试（pytest）

| 模块 | 测试内容 |
|------|----------|
| `chunker` | MD 按标题切块保留 heading 路径；PDF 按页切块；块大小 [200,1000] 字符 |
| `coverage` | mock hits → coverage_score 计算 + covered/thin/missing 判定 |
| `mastery` | Leitner 递推（答对 +1 最多 5；答错或"不会"回到 1 号盒）；next_review |
| `scoring` | 选择精确匹配；填空忽略空白；无 LLM 简答返回参考答案 |
| `pc_client` | mock HTTP → bootstrap/prepare/replace 参数 + 缺陷规避 |

### 10.2 端到端验证（`scripts/e2e_verify.py`）

前置：三服务运行中。流程：
1. 创建课程 → 2. 导入 4 份 samples → 打印 documents/chunks 行数
3. 问笔记 → 打印段落和出处
4. 10 个知识点覆盖分析 → 打印 score/level/weight/blind
5. 针对最大盲区出题 → 答题 → 判分 → 打印 mastery revision 变化
6. 故意答错 → 打印错题记忆和 mastery 变化
7. 结束会话 → 打印小结
8. 新会话 bootstrap → 打印提示（应含上次错题）
9. 导出使用记录 → 打印 CSV
10. **全程打印 seekdb SQL**（`GET_SQL`）和 **PowerContext 请求/响应**

输出：终端彩色打印 + `scripts/e2e_output/` JSON 存档。

---

## 11. 开发里程碑

| 会话 | 范围 | 完成标准 |
|------|------|----------|
| **M1** | 基础设施+导入+问笔记 | docker compose 起三服务；MD/PDF 切块入库；问笔记返回带出处段落；chunker+search 单元测试 |
| **M2** | 覆盖雷达+使用记录 | 雷达图+盲区清单可用；阈值用 samples 校准；使用记录+统计页面；coverage 单元测试 |
| **M3** | 出题判分+PowerContext | 有/无 LLM 两条路径出题判分；mastery revision 递增；bootstrap+prepare 生效；记忆页面；mastery 单元测试 |
| **M4** | 端到端+打磨 | e2e 跑通全流程并打印查询/记忆记录；README；导出；边界处理 |

### 主要风险

| 风险 | 应对 |
|------|------|
| seekdb/PC 首次初始化慢 | healthcheck retries 充足；app 启动重试 |
| IK 分词对术语不准 | 必要时 `ik_mode="max_word"`；校准阶段检查 |
| 无 LLM 出题质量有限 | 挖空优先选术语定义句；README 说明 |
| 覆盖度阈值不准 | `calibrate.py` 自动搜索最优阈值 |
| `DBMS_HYBRID_SEARCH` 转义 | `search.py` 统一清洗输入；过滤值只用受控 ID |
