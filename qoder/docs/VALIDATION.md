# ExamRadar 验证样例（VALIDATION）

给评审手动执行的验证流程：从零导入示例课程《数据库系统原理》，逐项核对检索、覆盖雷达、使用记录的行为是否与设计真值一致。每个步骤都给出**界面操作**和等价的 **curl / CLI 命令**各一份，两种方式任选其一。

- 设计真值（覆盖判定、题目归属、盲区排序的预期）见 `samples/course-db/README.md`
- 本文档的全部命令已在开发服务器（127.0.0.1:18800）上实际执行通过，实际输出见 `docs/DEVLOG.md` 会话 08b（M2 部分）与会话 10（§7 记忆读写）
- 最后有一节说明如何用 `scripts/e2e_verify.py` 把这些步骤一次跑完

## 0. 约定

**auto 标记**：验证请求一律带请求头 `X-ExamRadar-Source: auto`（页面则用 `?source=auto`）。
带 auto 的操作在使用记录里记为 `source=auto`，不会混进"真实使用"的统计。

**前提**：三服务已启动且健康（部署方式见 `docs/DEPLOY.md` 或 README）：

```bash
curl -s http://127.0.0.1:18800/api/health
```

预期：seekdb、embedding、powercontext 三项都是 `"ok": true`。
embedding 一项会显示 `BAAI/bge-small-zh-v1.5 (512d)`。

**课程 ID**：以下全部使用样例课程 `db101`。

## 1. 初始数据

`samples/course-db/` 的 7 份文件（`syllabus.txt` 是考试范围，不作为资料导入）：

| 文件 | 类型（doc_kind） | 内容 | 导入后块数 |
| --- | --- | --- | --- |
| `notes/02-SQL速记.md` | notes | 第 2 章 SQL 速记，只记了基本查询和分组，没有视图、子查询 | 3 |
| `notes/03-索引与B+树.md` | notes | 第 3 章，B+树、聚簇索引、哈希索引记得很全 | 7 |
| `notes/05-事务与并发控制.md` | notes | 第 5 章，ACID、两阶段锁、死锁很全；隔离级别和 MVCC 只有两句 | 6 |
| `slides/第7讲-故障恢复.pdf` | slides | 9 页课件：故障类型、日志、WAL、检查点、ARIES | 9（按页） |
| `papers/two-phase-commit-primer.pdf` | paper | 2 页英文阅读材料：两阶段提交及其阻塞问题 | 2（按页） |
| `exams/2025-2026-1-期末试卷A.pdf` | exam | 2 页 11 道题、满分 100，每题标了分值 | 11（按题号） |
| `syllabus.txt` | —（不导入） | 老师公布的 10 个知识点，覆盖分析的输入 | — |

试卷 PDF 的文字里混有大量"康熙部首"兼容字符（如 `⻋` 而非 `车`），导入时系统自动做 Unicode 归一化，否则全文检索搜不到正常写法的中文词——第 3 步的验收检索顺带验证了这一点（能搜到说明归一化生效）。

## 2. 导入样例资料

### 界面

打开 http://127.0.0.1:18800/import.html?source=auto ，分别上传 6 份资料并选对应类型（笔记 notes / 课件 slides / 试卷 exam / 论文 paper）。
或者直接用脚本一键导入（推荐）：

### 命令

```bash
bash scripts/load_sample.sh
```

（对 Docker 部署：`APP_URL=http://127.0.0.1:<app端口> bash scripts/load_sample.sh`）

### 预期结果

- 6 份资料逐份打印块数，末尾 `=== Import complete: 38 chunks total ===`
- **再运行一次**：6 份全部 `skip (already imported)`，0 新块（按内容 SHA256 去重，幂等）
- 首页（`/`）"已导入资料"出现 6 份；导入页列表每份显示块数

### 用 seekdb 核对（CLI）

```bash
cd app
uv run python -m examradar.cli sql "SELECT name, doc_kind, chunk_count FROM documents WHERE course_id='db101' ORDER BY id"
uv run python -m examradar.cli sql "SELECT doc_kind, COUNT(*) AS chunks FROM chunks WHERE course_id='db101' GROUP BY doc_kind"
uv run python -m examradar.cli sql "SELECT question_no, points FROM chunks WHERE course_id='db101' AND doc_kind='exam' ORDER BY question_no"
```

预期：documents 6 行（notes 3/7/6、slides 9、exam 11、paper 2）；按 doc_kind 分组合计 38 块；试卷 11 行，`points` 为 5, 10, 10, 15, 10, 5, 5, 10, 10, 10, 10，**合计 100 分**。

> `cli sql` 从 `qoder/.env` 读连接信息，密码不会出现在命令行。

## 3. 问笔记（混合检索）

### 界面

打开 http://127.0.0.1:18800/ask.html?source=auto ，输入查询词。
结果每条显示：出处（`文件 · 第 N 页 · 第 N 题(分) · 标题路径`）、渲染后的正文、分数行
`RRF: … | 关键词: … (rank …) | 语义: … (rank …)`；页面可展开查看本次检索的 **seekdb 实际执行 SQL**。

### 命令

前 5 条在默认范围（notes/slides/paper）检索；最后一条"函数依赖"要加 `"include_exam": true` 把往年试卷也纳入：

```bash
curl -s -X POST http://127.0.0.1:18800/api/search \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"query": "B+树插入时结点分裂", "course_id": "db101"}'
```

```bash
curl -s -X POST http://127.0.0.1:18800/api/search \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"query": "函数依赖 候选码", "course_id": "db101", "include_exam": true}'
```

### 预期结果（6 条验收检索的第一条命中）

| 查询 | 第一条应为 | 实测分数 |
| --- | --- | --- |
| B+树插入时结点分裂 | 笔记 03 `3.3 B+树的查找、插入与删除` | kw 3.691 / sem 0.8571 |
| 脏页表 | 课件第 7 页 `ARIES 恢复算法的三个阶段` | kw 2.596 / sem 0.7332 |
| 先写日志原则 | 课件第 4 页 `先写日志原则（WAL）` | kw 11.231 / sem 0.8748 |
| coordinator crash blocking | 英文阅读材料第 2 页 `5. Handling Failures` | kw 2.772 / sem 0.7969 |
| 两阶段锁能不能避免死锁 | 笔记 05 `5.3 封锁与两阶段锁协议（2PL）` | kw 4.005 / sem 0.8442 |
| 函数依赖 候选码（含试卷） | 试卷第 4 题（15 分） | kw 3.854 / sem 0.8506 |

其他核对点：

- 每条结果的 `keyword_score`（BM25）都大于 0，说明全文索引确实命中，不只是向量兜底
- 默认范围的结果里不出现 `2025-2026-1-期末试卷A.pdf`（试卷只在 `include_exam=true` 时参与）
- 注意："两阶段锁能不能避免死锁"若加 `include_exam=true`，试卷第 8 题（题干含同样的词）会排到第一——这是语料范围变化所致，设计真值针对的是默认范围

### 怎么核对 seekdb 实际执行的查询

`POST /api/search` 的响应里有两个字段：

- `search_json`：发给 seekdb 的 `DBMS_HYBRID_SEARCH` JSON（含 BM25 `query`、向量 `knn`、`rank: {"rrf": {}}`、`_source`、`size`）
- `actual_sql`：调用 `SELECT DBMS_HYBRID_SEARCH.GET_SQL('chunks', '<上述 JSON>')` 得到的实际执行 SQL

ask 页面"seekdb 实际执行 SQL"一节展示的就是 `actual_sql`。看到 SQL 里同时有全文匹配（`_fts`）和向量检索（`_vs`）的 `ifnull` 拼接，即说明混合检索（RRF）在 seekdb 服务端执行，不在应用层。

## 4. 覆盖雷达

### 输入

`samples/course-db/syllabus.txt` 的考试范围原文（10 个知识点）：

```text
《数据库系统原理》2026 秋 期末考试范围
1. 关系模型与关系代数
2. SQL 查询与视图
3. 索引：B+树与哈希索引
4. 函数依赖与范式（3NF、BCNF）
5. 查询处理与优化
6. 事务的 ACID 特性
7. 并发控制：两阶段锁与死锁
8. 隔离级别与 MVCC
9. 故障恢复：WAL 与 ARIES
10. 分布式事务与两阶段提交（2PC）
```

### 界面

打开 http://127.0.0.1:18800/radar.html?source=auto ，点 **"载入示例考试范围"**（或粘贴上面原文），提交分析。
预期看到：ECharts 雷达图（覆盖度 + 考试权重两个系列）、盲区清单表格（含关联试题列）、
每个知识点可展开判定理由、最强证据（Markdown 渲染）、关联试题原文。

### 命令

```bash
curl -s -X POST http://127.0.0.1:18800/api/coverage/analyze \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"course_id": "db101", "syllabus_text": "《数据库系统原理》2026 秋 期末考试范围\n1. 关系模型与关系代数\n2. SQL 查询与视图\n3. 索引：B+树与哈希索引\n4. 函数依赖与范式（3NF、BCNF）\n5. 查询处理与优化\n6. 事务的 ACID 特性\n7. 并发控制：两阶段锁与死锁\n8. 隔离级别与 MVCC\n9. 故障恢复：WAL 与 ARIES\n10. 分布式事务与两阶段提交（2PC）"}'
```

保存上次结果后可随时取回：

```bash
curl -s "http://127.0.0.1:18800/api/coverage/latest?course_id=db101"
```

### 预期结果

响应 `items` 每项含：`topic_id`、`topic_name`、`coverage_level`、`coverage_score`、
`support_chunks`、`support_chars`、`terms`（每个考点词的 `found`/`chunks`/`aliases`）、
`best_evidence`、`exam_weight`、`exam_questions`（`question_no`/`points`/`similarity`/`matched_terms`/`content`）、
`blind_spot_score`、`reason`。

10 个知识点的判定与设计真值一致：

| topic_id | 知识点 | 判定 | 考试权重 |
| --- | --- | --- | --- |
| t01 | 关系模型与关系代数 | missing | 5 |
| t02 | SQL 查询与视图 | thin | 10 |
| t03 | 索引：B+树与哈希索引 | covered | 10 |
| t04 | 函数依赖与范式（3NF、BCNF） | missing | 25 |
| t05 | 查询处理与优化 | missing | 5 |
| t06 | 事务的 ACID 特性 | covered | 5 |
| t07 | 并发控制：两阶段锁与死锁 | covered | 10 |
| t08 | 隔离级别与 MVCC | thin | 10 |
| t09 | 故障恢复：WAL 与 ARIES | covered | 10 |
| t10 | 分布式事务与两阶段提交（2PC） | covered | 10 |

其他核对点：

- **判定依据是"考点词是否出现在材料里 + 支撑正文量"，语义分只用来给证据排序**（阈值 `COVERAGE_TERM_RATIO_COVERED=0.5`、`COVERAGE_SUPPORT_CHARS=280`、`COVERAGE_MIN_BODY_CHARS=50`，见 `.env.example`）
- `exam_weight` 合计 = 100（11 道题按考点词命中归属，见下）
- **盲区第一名**（`blind_spot_score` 最大）：t04，权重 25、coverage 0、blind 25.0；其后是 t08、t02。核对时按 `blind_spot_score` 找最大项，不要依赖 `items` 的先后顺序
- **判定理由**应"说清应该包含什么"：找到的考点词及出处（文档·页·标题）、没找到的考点词、支撑段落数和字数、离阈值的距离。例如 t02 的理由应包含：考点词 1/2 找到（"SQL 查询"→笔记 02 两处；"视图"未找到）、支撑 2 段共 233 字、距 covered 阈值（280 字）还差 47 字，判为 thin；t04 应是"函数依赖、范式在笔记、课件和阅读材料中均未出现，覆盖度 0"。不逐字对照整段理由原文，措辞可能随版本微调
- t04 的 `exam_questions` 是第 4 题（15 分）和第 5 题（10 分），`content` 为题目原文，`matched_terms` 显示归属依据（命中"函数依赖""范式"等考点词）
- t10 虽然"分布式事务"没找到，但经别名 `2PC` 命中英文阅读材料，判为 covered——别名机制生效的证据

### 用 seekdb 核对（CLI）

```bash
cd app
uv run python -m examradar.cli sql "SELECT topic_id, coverage_level, coverage_score, exam_weight, blind_spot_score FROM coverage_items WHERE course_id='db101' ORDER BY id"
uv run python -m examradar.cli sql "SELECT COUNT(*) AS runs FROM coverage_runs WHERE course_id='db101'"
```

预期：coverage_items 10 行，与上表一致（每次分析替换该课程旧记录）；coverage_runs 计数随分析次数递增。

## 5. 使用记录

### 界面

打开 http://127.0.0.1:18800/usage.html?source=auto （auto 模式下数据来源自动选 auto）。
预期：概览卡片（检索/导入/分析/答题次数、会话数）、按天趋势柱状图
（按浏览器时区分天）、累计学习时长（**按学习会话计算**：会话开始到最后一个事件，30 分钟无事件自动结束）、CSV/JSON 导出按钮。

### 命令

```bash
curl -s "http://127.0.0.1:18800/api/usage/stats?course_id=db101&source=auto&tz=Asia/Shanghai"
curl -s "http://127.0.0.1:18800/api/usage/export?course_id=db101&source=auto&format=json"
curl -s "http://127.0.0.1:18800/api/usage/export?course_id=db101&source=auto&format=csv"
```

### 预期结果

- `stats`：`search_count`、`import_count`、`analyze_count` ≥ 本文档第 2–4 步产生的次数（search ≥ 6、import ≥ 6、analyze ≥ 1），`total_events` 为合计；`daily` 数组按传入时区分天（用你的时区名，如 `Asia/Shanghai`、`America/New_York`）
- `stats` 的 `source=real` 视角不包含以上 auto 请求——所有验证操作带 `X-ExamRadar-Source: auto`，不应污染真实使用统计
- JSON 导出：事件数组，每条含 `id`、`session_id`、`course_id`、`source`、`event`、`payload`、`created_at`（UTC）
- CSV 导出：**前 3 个字节为 UTF-8 BOM（`EF BB BF`）**，Excel 双击打开中文不乱码；表头
  `id,session_id,course_id,source,event,payload,created_at`

### 用 seekdb 核对（CLI）

```bash
cd app
uv run python -m examradar.cli sql "SELECT source, event, COUNT(*) AS n FROM usage_events WHERE course_id='db101' GROUP BY source, event"
```

预期：`source=auto` 的行覆盖 import/search/coverage 三类事件，计数与 stats 接口一致。

## 6. 幂等与清理（CLI）

`delete-course` 默认保留使用记录（资料可重导，使用日志不该没）：

```bash
cd app
# 在临时课程上演示，不要对 db101 执行
uv run python -m examradar.cli import ../samples/course-db/notes/02-SQL速记.md --course s08b_demo --kind notes --source auto
uv run python -m examradar.cli sql "SELECT COUNT(*) AS events FROM usage_events WHERE course_id='s08b_demo'"   # 1
uv run python -m examradar.cli delete-course s08b_demo            # documents=1, chunks=3, usage_events kept
uv run python -m examradar.cli sql "SELECT COUNT(*) AS events FROM usage_events WHERE course_id='s08b_demo'"   # 仍为 1
uv run python -m examradar.cli delete-course s08b_demo --include-usage
uv run python -m examradar.cli sql "SELECT COUNT(*) AS events FROM usage_events WHERE course_id='s08b_demo'"   # 0
```

预期：默认删除只清 documents/chunks/coverage_*，usage_events 保留；加 `--include-usage` 才连使用记录一起删。

## 7. 核对 PowerContext 的记忆读写（M3：复习教练与学习者记忆）

本节验证闭环：会话开始时从 PowerContext 读回学习者记忆、判分后掌握度（mastery）更新
且错题（mistake）写入、出题前按知识点召回历史错题、下次会话开场白提到答错的知识点。
核对方式：应用侧 API 响应 + 直接查询 PowerContext 的记忆接口（18801）。

前提：第 2 步资料已导入、第 4 步覆盖分析已跑过（出题选题依赖覆盖结果）。
以下命令把 `learner` 换成一个**没用过的新名字**（比如加时间戳），保证首次 bootstrap 为空；
`scope_id`、`artifact_id`、`session_id` 每次运行都不同，以实际响应为准。

### 界面

打开 http://127.0.0.1:18800/coach.html?source=auto ，输入学习者名字开始会话。
预期：开场先出盲区知识点的题；答错一题、答对一题后结束会话；**再开一次会话**，
开场白出现"上次你在『…』上错了 1 次，先复习它"。
再打开 http://127.0.0.1:18800/memory.html?source=auto 输入同一名字：
掌握度卡片（含 revision 轨迹）、错题本、复习计划、会话小结、PowerContext 调用日志。

### 命令（一条链跑完）

```bash
# 1) 开始会话（首次：bootstrap 为 empty，opening_line 为 null，盲区第一名是 t04）
curl -s -X POST http://127.0.0.1:18800/api/sessions/start \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"learner": "验证记忆-<换新名字>", "course_id": "db101"}'
# 记下响应里的 session_id 和 scope_id

# 2) 出第 1 题（不指定 topic_id，自动选盲区第一名 t04 = missing → 往年原题自测）
curl -s -X POST http://127.0.0.1:18800/api/quiz/next \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"session_id": "<session_id>"}'
# 记下 question_id

# 3) 自评"不会"（答错）：mastery 卡片创建（盒 1）、mistake 写入、复习计划首建
curl -s -X POST http://127.0.0.1:18800/api/quiz/answer \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"question_id": "<question_id>", "self_rating": "不会"}'

# 4) 指定 t08 出填空题并答对（expected_answer 见 quiz/next 响应）
curl -s -X POST http://127.0.0.1:18800/api/quiz/next \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"session_id": "<session_id>", "topic_id": "t08", "question_type": "fill"}'
curl -s -X POST http://127.0.0.1:18800/api/quiz/answer \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"question_id": "<question_id>", "answer": "隔离级别"}'

# 5) 结束会话：写会话小结（session）+ 更新复习计划
curl -s -X POST http://127.0.0.1:18800/api/sessions/end \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "<session_id>", "source": "auto"}'

# 6) 再开一次会话：opening_line 出现个性化提示，bootstrap status=ready
curl -s -X POST http://127.0.0.1:18800/api/sessions/start \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"learner": "验证记忆-<同一个名字>", "course_id": "db101"}'

# 7) 会话 2 里对 t04 出题：history / mistake_history 召回上次的错题
curl -s -X POST http://127.0.0.1:18800/api/quiz/next \
  -H 'Content-Type: application/json' -H 'X-ExamRadar-Source: auto' \
  -d '{"session_id": "<新 session_id>", "topic_id": "t04"}'

# 8) 记忆页 API（掌握度卡片含 revisions 轨迹、错题、复习计划、会话小结）
curl -s "http://127.0.0.1:18800/api/memory?learner=<URL 编码的名字>&course_id=db101"
```

### 预期结果（应用侧，实测输出摘录）

- **第 1 题（自动选题）**：`topic_id` 为 t04、`question_type` 为 `self`，
  `question` 是期末试卷第 4 题原文（"4.（15 分）设关系模式 R(A, B, C, D, E)…"），
  `source.label` 为 `2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 第4题（15.0分）`，
  `hint` 为"笔记里没有这部分，建议先补。"——missing 知识点走往年原题自测；
- **答错（自评"不会"）**：`correct=false`、`box_before=1`、`box_after=1`（答错留在 1 号盒）；
  `mastery` 为新建卡片（`revision: 1`，正文含 `盒 1，答对 0 次 / 答错 1 次`）；
  `mistake_memory` 为新错题（正文以 `【错题】t04 …` 开头）；
  `review_plan` 首建，`opening` 为"上次你在『函数依赖与范式（3NF、BCNF）』上错了 1 次…"
- **答对（t08 填空）**：`box_before=1`、`box_after=2`（Leitner 升盒），
  `mistake_memory` 为 `null`（答对不写错题）；
- **结束会话**：`summary_memory` 正文为"会话小结：时长 N 分钟，做题 2 道，正确率 50%，
  薄弱点：函数依赖与范式（3NF、BCNF）（t04，错 1 次）"；`review_plan.revision` 递增；
- **第 2 次开始会话**：`opening_line` 即复习计划的 `opening`；
  `bootstrap.status` 为 `ready`，`items` 里有复习计划 artifact 的 id 和 revision；
- **会话 2 出 t04 的题**：响应 `mistake_history` 里出现上次那条 `【错题】t04 …`，
  且带 `citation.artifact_ref`（PowerContext 的引用格式）——出题前错题召回生效；
- **`GET /api/memory`**：`mastery_cards` 两张（t04 盒 1、t08 盒 2，各含 `revisions` 数组）、
  `mistakes` 一条、`review_plan`（`revisions` 有多次判分留下的历史）、
  `session_summaries`、`pc_calls`（PowerContext 最近调用日志）。

### 直接查 PowerContext（18801）

用上面拿到的 `scope_id` 和 artifact id（`/api/memory` 或判分响应里都有）：

```bash
# 掌握度卡片的 handle：mastery-<topic_id> → artifact_id + 当前 revision
curl -s "http://127.0.0.1:18801/v1/scopes/<scope_id>/artifact-handles/atomic-memory/mastery-t04"

# 卡片正文（content.kind = mastery，text 首行"掌握度：…"）
curl -s "http://127.0.0.1:18801/v1/scopes/<scope_id>/artifacts/atomic-memory/<artifact_id>"

# revision 历史（每次判分后 upsert 都留一条）
curl -s "http://127.0.0.1:18801/v1/scopes/<scope_id>/artifacts/atomic-memory/<artifact_id>/revisions"

# 错题的标签：应为 ["examradar", "topic-t04", "type-mistake"]
curl -s "http://127.0.0.1:18801/v1/scopes/<scope_id>/artifacts/atomic-memory/<错题 artifact_id>/tags"
```

预期：handle `mastery-t04` 指向的 artifact 与应用侧判分响应里 `mastery.artifact_id` 一致；
错题 tags 含 `examradar`、`topic-t04`、`type-mistake`（按知识点打标签，
`query_by_tags(["type-mastery"])` 就是记忆页掌握度卡片的取数方式）；复习计划的
handle 是 `review-plan`，tags 含 `bootstrap-context`（下次会话 bootstrap 只带它）。

### 隐私核对

使用记录里不出现学习者名字（只存 sha256 前 8 位哈希）：

```bash
curl -s "http://127.0.0.1:18800/api/usage/export?course_id=db101&source=auto&format=json"
```

预期：JSON 里搜不到上面的学习者明文；`session_start` 事件的 `payload.learner`
是 8 位哈希。累计学习时长按会话计算：`usage/stats` 的 `study_minutes` 随会话
（开始到最后一个事件）增长，`session_count`/`quiz_count` 计入本次会话。

## 8. 一次跑完：端到端脚本

以上步骤可以用 `scripts/e2e_verify.py` 自动跑一遍（导入 → 验收检索 → 覆盖分析 → **复习教练闭环** → 使用记录导出，全程带 auto 标记，并打印 seekdb 实际 SQL 与 PowerContext 请求日志）：

```bash
python3 scripts/e2e_verify.py --app-url http://127.0.0.1:18800
```

其中复习教练一步：用带时间戳的新学习者名开始会话（断言 bootstrap 为空）→
t04 自测题答"不会"（错）→ 同知识点答对（Leitner 盒 1→2、卡片 revision 递增）→
t08 填空答错 → 结束会话 → **新会话**开场白提到答错的知识点（bootstrap ready）→
直接查 PowerContext 核对 handle、tags、revision 历史 → 检查使用记录 quiz/session
计数和导出里没有学习者明文。报告正文含两道题的原文、PowerContext 读写明细表
（方向、接口、artifact id、revision、标签）和 prepare 召回的错题。

报告写入 `docs/validation/e2e-report.md`。
