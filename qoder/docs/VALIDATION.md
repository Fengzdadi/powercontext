# ExamRadar 验证样例（VALIDATION）

给评审手动执行的验证流程：从零导入示例课程《数据库系统原理》，逐项核对检索、覆盖雷达、使用记录的行为是否与设计真值一致。每个步骤都给出**界面操作**和等价的 **curl / CLI 命令**各一份，两种方式任选其一。

- 设计真值（覆盖判定、题目归属、盲区排序的预期）见 `samples/course-db/README.md`
- 本文档的全部命令已在开发服务器（127.0.0.1:18800）上实际执行通过，实际输出见 `docs/DEVLOG.md` 会话 08b
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
预期：概览卡片（检索/导入/分析次数、累计学习时长——M3 前为估算值）、按天趋势柱状图
（按浏览器时区分天）、CSV/JSON 导出按钮。

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

<!-- 会话 10：补全本节。M3 合并后核对以下内容（做什么，接口和命令届时补）：
     - 会话开始时从 PowerContext 读回学习者记忆（掌握度/复习计划），首页出现个性化提示；
     - 答题后掌握度卡片（mastery）更新、错题（mistake）写入；
     - 出题前按知识点召回历史错题；
     - 核对方式：应用侧 API 响应 + 直接查询 PowerContext 的记忆接口。 -->

本节验证 PowerContext 的记忆读写是否生效：判分后掌握度是否更新、错题是否写入、
下次会话是否能读回。<!-- 会话 10：M3 合并后补操作步骤、curl / CLI 命令和预期结果。 -->

## 8. 一次跑完：端到端脚本

以上步骤可以用 `scripts/e2e_verify.py` 自动跑一遍（导入 → 验收检索 → 覆盖分析 → 使用记录导出，全程带 auto 标记，并打印 seekdb 实际 SQL 与 PowerContext 请求日志）：

```bash
python3 scripts/e2e_verify.py --app-url http://127.0.0.1:18800
```

报告写入 `docs/validation/e2e-report.md`。
<!-- 会话 10：e2e 报告的 M3 部分（出题判分、掌握度更新、错题召回）由合并后补齐。 -->
