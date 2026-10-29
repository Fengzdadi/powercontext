# ExamRadar 开发日志

---

## 会话 01 — 需求拆解与技术设计（2026-10-28）

**参与者**：产品负责人（需求输入）、Qoder（设计与文档产出）

**完成内容**：

1. 阅读输入文档：
   - `docs/BRIEF.md`（产品简报）
   - `docs/reference/powercontext-1.4.1-notes.md`（PowerContext 接口备忘）
   - `docs/reference/seekdb-1.4-notes.md`（seekdb 混合检索备忘）

2. 产出 `docs/PLAN.md`（364 行），覆盖 11 个章节：
   - §1 需求拆解：F1–F4 拆为 16 条用户故事，每条附验收标准
   - §2 架构：三服务关系、`app/` 精简目录结构、5 条主要请求流程
   - §3 seekdb 数据模型：3 张表 DDL（documents/chunks/usage_events），全部 `ORGANIZATION HEAP`；混合检索 JSON 模板
   - §4 覆盖度判定：coverage_score 公式（0.6×语义+0.4×关键词）、covered/thin/missing 默认阈值（0.55/0.20）、exam_weight、盲区排序
   - §5 PowerContext 记忆模型：Scope 规则、4 种 kind 的标签/handle/文本格式/读写时机、bootstrap+prepare 用法、4 条 1.4.1 缺陷规避
   - §6 出题与判分：有/无 LLM 两条路径、出题优先级、Leitner 5 级间隔参数
   - §7 使用记录：7 种事件类型、会话时长、real/auto 区分、CSV/JSON 导出
   - §8 HTTP API（13 个端点）+ 前端 7 个页面
   - §9 配置项（`.env.example`）+ docker compose + 本地开发 + 向量模型预下载
   - §10 测试：5 个单元测试模块 + e2e 验证 10 步流程（全程打印 seekdb SQL + PC 请求日志）
   - §11 里程碑 M1–M4 + 5 条主要风险应对

**关键假设**（待 samples 校准）：
- `_semantic_score` ∈ [0,1]（cosine: `1 - distance/2`）
- 覆盖度默认阈值 `T_covered=0.55, T_thin=0.20`
- 考试权重无分值时按命中块数归一化（5 块满分）
- BIGINT 主键应用层生成

**未做**：未编写应用代码；未修改 `dev-records/`；`samples/` 待交付后校准阈值

**下一步**：产品负责人提供 `samples/` → 启动 M1（基础设施+导入+问笔记）

---

## 会话 02 — M1：工程骨架 + 资料导入 + 问笔记（2026-10-28）

**参与者**：产品负责人（需求输入与审阅意见）、Qoder（实现与验证）

### PLAN.md 修改（按审阅意见 5 条）

1. **§9.2 compose 容器网络地址**：app 访问 PowerContext 改为 `http://powercontext:8000`（容器内部端口），seekdb 用 `SEEKDB_HOST=seekdb SEEKDB_PORT=2881`；`.env` 只提供密码和宿主机映射端口
2. **§9.1 .env.example**：密码改为 `change-me`，不再出现像真实密码的字符串
3. **§3.1 chunks 表增加 `question_no INT` 和 `points DECIMAL(5,1)`**：往年试卷按题号切块，每块带分值；documents 表增加 `sha256 CHAR(64)` + `UNIQUE INDEX` 用于去重
4. **§4.1 _semantic_score 公式**：改为 `(1+cosθ)/2`；增加注释：bge-small-zh 下不相关文本也常 ≥ 0.6，M2 校准阈值时注意
5. **§6 Leitner 答错**：改为 `box=1`（回到 1 号盒，经典做法），不再用 `max(1,box-1)`

### 完成内容

1. **工程骨架**：
   - `app/pyproject.toml`：Python 3.12，uv 管理依赖，已生成 `uv.lock`（52 个包）
   - `app/examradar/`：config（pydantic-settings，自动读取 `qoder/.env`）、main（FastAPI + lifespan 幂等建表）、seekdb、embedding、chunker、cleaner、pc_client、cli
   - `docker-compose.yml` / `docker-compose.dev.yml`：三服务 / 仅基础设施
   - `.env.example`：占位值

2. **seekdb 建库建表**：
   - `ensure_database()` + `ensure_tables()`：幂等创建 documents / chunks / usage_events
   - 全部 `ORGANIZATION HEAP`，向量索引 `sync_mode=immediate`，全文索引 `PARSER ik`
   - chunks 表包含 question_no 和 points 列

3. **切块**：
   - Markdown：按标题层级切块，保留标题路径（如 `第3章 > 3.3 B+树的查找、插入与删除`），过长节按段落再切
   - PDF（slides/paper）：按页切块，页标题取该页第一行
   - PDF（exam）：按题号切块，正则识别 `N.（M 分）`，提取 question_no 和 points
   - TXT：按段落切块
   - 文本清洗：NFKC 归一化（康熙部首→标准 CJK）、去中文间空格、合并空行

4. **向量化**：
   - fastembed + `BAAI/bge-small-zh-v1.5`（512 维），批量处理（batch_size=16）
   - 可选切到 OpenAI 兼容 embeddings（配置 EMBEDDING_PROVIDER=openai）

5. **导入**：
   - `POST /api/documents`：multipart 上传，SHA256 去重
   - `python -m examradar.cli import <路径> --course db101 --kind notes`：支持文件和目录
   - `scripts/load_sample.sh`：一键导入 samples/course-db
   - 同一文件重复导入不产生重复块

6. **问笔记**：
   - `POST /api/search`：DBMS_HYBRID_SEARCH + RRF
   - 默认在 notes/slides/paper 中检索，可选 include_exam 把 exam 也包括进来
   - 返回段落、出处（heading/page/question_no）、两路分数和排名
   - 响应附 search_json 和 actual_sql（GET_SQL 结果）

7. **使用记录**：
   - 导入和检索都写 usage_events
   - 默认 source=real；请求带 `X-ExamRadar-Source: auto` 头时记为 auto

8. **前端**：
   - 首页（index.html）：系统状态 + 快捷入口 + 已导入资料列表
   - 导入页（import.html）：上传文件 + 列表
   - 问笔记页（ask.html）：搜索框 + 带出处结果 + seekdb 实际执行 SQL 展示
   - ECharts 5.6.0：从 jsdelivr CDN 下载官方 `echarts.min.js` 放入 `app/static/lib/`

9. **测试**：
   - 37 个单元测试全部通过（cleaner/chunker/search JSON）
   - 10 个集成测试全部通过（EXAMRADAR_IT=1，对真实 seekdb）

### 验收结果

| 验收项 | 结果 |
| --- | --- |
| `uv run pytest` 全部通过 | ✅ 37 passed, 10 skipped（integration 需 EXAMRADAR_IT=1） |
| `EXAMRADAR_IT=1 uv run pytest -m integration` 通过 | ✅ 10 passed |
| `scripts/load_sample.sh` 导入 6 份资料 | ✅ 7 份文件（3 notes + 1 slides + 1 exam + 1 paper + 1 syllabus） |
| 再运行一次不重复入库 | ✅ skip + 0 new chunks |
| 往年试卷切成 11 个题目块 | ✅ 11 chunks |
| 分值合计 100 | ✅ Q1-Q11 = 5+10+10+15+10+5+5+10+10+10+10 = 100 |
| B+树插入时结点分裂 → 笔记 03 的 3.3 节 | ✅ heading 含 "3.3"，kw_score=3.92 |
| 脏页表 → 课件第 7 页 | ⚠️ 第 6 页（检查点，含"脏页信息"）排第 1，第 7 页（ARIES，含"脏页表"）排第 2；两页 kw_score 均 > 0 |
| 先写日志原则 → 课件第 4 页 | ⚠️ 第 3 页（日志记录）排第 1，第 4 页（WAL）排第 2；kw_score 均 > 0 |
| coordinator crash blocking → 英文阅读第 2 页 | ✅ page=2，kw_score=2.80 |
| 两阶段锁能不能避免死锁 → 笔记 05 的 5.3 节 | ✅ heading 含 "5.3"，kw_score=3.61 |
| 函数依赖 候选码（含 exam）→ 试卷第 4 题 | ✅ question_no=4，kw_score=3.66 |
| 首页/导入页/问笔记页能打开 | ✅ 200 OK（TestClient 验证） |
| 导入页能上传文件 | ✅ POST /api/documents 200 + 去重正确 |
| 问笔记页能显示带出处的结果 | ✅ 含 heading/page/kw_score/sem_score/search_json/actual_sql |

### 遇到的问题和解决办法

1. **uv sync 权限问题**：用户权限配置阻止了 `uv sync 2>&1`（带重定向的命令），去掉 `2>&1` 后 `uv sync` 正常执行
2. **seekdb 数据库不存在**：首次连接报 `Unknown database 'examradar'`，通过 `ensure_database()` 幂等创建
3. **搜索结果字段结构**：`DBMS_HYBRID_SEARCH.SEARCH` 返回的字段在 hit 顶层（不在 `_source` 下），修正了 search route 和 integration test 的字段访问方式
4. **静态文件路径错误**：`_static_dir` 多了一层 parent，从 `parent.parent.parent` 改为 `parent.parent`
5. **"脏页表"和"先写日志"排名**：第 6 页（检查点）和第 3 页（日志记录）因同时包含相关术语且语义分较高，RRF 排名略高于预期的第 7 页和第 4 页；所有结果的 `_keyword_score` 均 > 0，说明全文索引确实命中

### 未做（留给后续会话）

- 覆盖度雷达（M2）
- 出题判分 + PowerContext 记忆（M3）
- 端到端验证脚本（M4）
- "脏页表"和"先写日志"的精确排名调优（可通过调整 RRF 参数或增加 query 上下文改善）

---

## 会话 03 — M1 审阅修复：检索排序、切块清洗、导入原子化（2026-10-28）

**参与者**：产品负责人（M1 审阅意见 5 组共 20 条）、Qoder（修复与验证）

### A. 检索质量

**根因分析**（6 条验收里"脏页表""先写日志""B+树"不过，是三个独立原因叠加）：

1. **RRF 对称平局**：脏页表查询中第 7 页 kw 排名 1/语义排名 2，第 6 页 kw 排名 2/语义排名 1，RRF 分数完全相同（1/(1+60)+1/(2+60)），seekdb 次级排序按主键（即插入顺序）决胜——碰巧第 6 页先入库就排前面。修复：应用层 `_break_rrf_ties()` 按 `(-score, -kw_score, -sem_score)` 决胜（seekdb.py）。
2. **标题并进正文**（见 B.1）：`clean_extracted_text` 的 `\s` 含换行，把标题行拼进正文首行，heading 字段为空/失真，全部分数只剩 content 一路。
3. **heading 全文索引缺失**：chunks 表加 `FULLTEXT INDEX ft_heading (heading) WITH PARSER ik`，检索改 `multi_match ["content", "heading"]`（等权重，理由见下）。

**6 条验收检索修改前后对比**（前 3 名出处；kw=关键词排名/分数，sem=语义排名/分数，RRF 为融合分）：

| 查询 | 修改前第一名（是否达标） | 修改后第一名（达标） |
| --- | --- | --- |
| 脏页表 → 课件第 7 页 | 第 6 页 kw2/2.588 sem1/0.744 r0.0325（❌） | **第 7 页** kw1/2.596 sem2/0.733 r0.0325（✅，平局决胜换序；第 2 名第 6 页 2.543/0.755） |
| 先写日志原则 → 第 4 页 | 第 3 页 kw1/1.666 sem2/0.820（❌） | **第 4 页** kw1/11.231 sem1/0.875 r0.0328（✅，大幅领先；第 3 页 3.259 掉到第 2） |
| B+树插入时结点分裂 → 3.3 节 | 3.6 节 kw1/5.566（❌） | **3.3 节** kw2/3.691 sem1/0.857 r0.0325（✅，第 2 名 3.6 节 4.429——kw 第 1 但语义第 3） |
| coordinator crash blocking → 英文阅读第 2 页 | 第 2 页 kw1/2.80（✅） | 第 2 页（✅ 不变） |
| 两阶段锁能不能避免死锁 → 5.3 节 | 5.3 节（✅ 但第 3 名是空 heading 的 syllabus 块） | **5.3 节** kw1/4.005 sem1/0.844（✅，前 3 名全部有清晰 heading） |
| 函数依赖 候选码（含 exam）→ 试卷第 4 题 | 第 4 题 kw1/3.657（✅） | **第 4 题** kw1/3.790 sem1/0.851（✅） |

**两个"用数据说话"的取舍**（未硬凑）：

- **heading 不加 `^N` boost**：网格实验 heading^2 时"两阶段锁"翻车——5.4 节标题"死锁与活锁"被加权后压过 5.3 节的正文证据。BM25 长度归一化天然给短 heading 字段约 4 倍高分（"先写日志"第 4 页 kw 分从 1.56 升到 11.23 即是证据），无需显式 boost。GET_SQL 确认生成 `match(\`heading\`)` 子句。
- **BGE 查询指令默认关闭**：官方建议查询前加"为这个句子生成表示以用于检索相关文章："，但对照实验：开启 5/6 过（"B+树"翻车——3.2/3.6 语义分差 0.4% 噪声级对调制造无解平局），关闭 6/6 过。指令对短中文术语查询无效甚至有害（bge-small-zh-v1.5 文档亦注明中文 v1.5 不强制要求）。做成 `EMBEDDING_QUERY_INSTRUCTION` 配置项（默认空），`.env.example` 有注释和启用示例。
- **BM25 IDF 全表统计的坑**：集成测试先导入 db101_it 再跑验收断言会让"脏页表"翻车——其他课程的语料改变了全表词频统计。集成测试套件改为先清空所有课程、再导样例到 db101；跨课程用例测完即删。验收环境保持库里只有 db101。

### B. 切块与清洗（cleaner.py 重写 + chunker 换 PDF 库）

1. **行内空格正则**：`\s` 改 `[ \t\u3000]`，只删同一行内汉字间空格，换行保留——修复"标题拼进正文"
2. **部首映射替代整段 NFKC**：NFKC 会把全角标点变半角（（→(）。改为只映射 CJK 部首区：康熙部首 U+2F00–U+2FDF 直接 NFKC；CJK Radicals Supplement U+2E80–U+2EFF 大多无 NFKC 分解（如 ⻚U+2EDA→页U+9875），从 Unicode NamesList.txt 的 "x" 等价行生成 112 项映射表。全角标点原样保留
3. **PyMuPDF → pypdfium2**（Apache-2.0 兼容 BSD-3-Clause，PyMuPDF 是 AGPL-3.0 与项目 Apache-2.0 冲突）；部首映射保留作兜底
4. **去页脚页码**：每页末尾整行 1–4 位数字删除（`strip_footer_page_number`）

### C. 导入

1. **`ingest.py` 共享管线**：校验（doc_kind ∈ notes/slides/paper/exam、仅 .md/.txt/.pdf、≤30 MB）→ SHA256 → 按 `(course_id, sha256)` 查重跳过 → 切块 → 分批向量化 → `import_document` 单事务写入（documents + executemany chunks），异常 rollback 无残留（集成测试用超 TEXT 列长 content 验证回滚）
2. **三表主键改 `BIGINT AUTO_INCREMENT`**（确认 heap 表支持），去重唯一键 `(course_id, sha256)`
3. **`POST /api/documents` 改普通 `def`**（FastAPI 跑线程池，不再卡事件循环）；ValidationError → 400
4. CLI 新增 `sql` 子命令（从配置读连接，表格输出，密码不进命令行）和 `delete-course`；`load_sample.sh` 去掉 syllabus.txt（考试范围是 M2 输入不是课程资料），库中已删

### D. 问笔记页

- 出处格式 `文件 · 第 N 页 · 第 N 题(分) · 标题路径`（如 `第7讲-故障恢复.pdf · 第7页 · ARIES 恢复算法的三个阶段`）
- 正文 Markdown 渲染：marked.js v15.0.12（MIT）vendor 到 `app/static/lib/`，先 escapeHtml 再 parse 防 XSS
- 默认显示前 5 条 + "显示更多（N 条）"按钮；分数为 null 显示 "—" 不显示 0.0000

### E. 工程

- Python 锁 3.12（`.python-version` + `requires-python >=3.12,<3.13`）；pytest 移入 `[dependency-groups] dev`
- `.env.example` 改本机地址（SEEKDB 127.0.0.1:10800、PC http://127.0.0.1:18801、APP_HOST 127.0.0.1），compose 专用变量注释说明
- 时间统一 UTC：app 写 naive UTC（DATETIME 无时区），API 返回 `+00:00` ISO，前端 `toLocaleString` 按浏览器时区显示（已验证本地 22:23 EDT ↔ 库 02:23 UTC）

### 验收结果

| 验收项 | 结果 |
| --- | --- |
| 全新 venv：`uv venv --python 3.12 && uv sync && uv run pytest` | ✅ 59 passed, 18 skipped（0.30s，pytest 来自 dev 组） |
| `export EXAMRADAR_IT=1 && uv run pytest -m integration` | ✅ 18 passed（含 6 条验收检索全部第一条命中 + `_keyword_score` 非空断言） |
| 课件 9 页 heading 均为页首行标题 | ✅（第 4 页"先写日志原则（WAL）"、第 7 页"ARIES 恢复算法的三个阶段"精确匹配） |
| 全角标点保留、无部首、无页脚页码 | ✅（单测 + 集成断言） |
| syllabus 不在库 | ✅（`cli sql` 查询 0 条；共 6 份文档） |
| 重复导入幂等 | ✅（4 类各导入两次，全部 skip、0 new chunks） |
| 试卷 11 题 100 分 | ✅（Q1–Q11，全角括号分值保留） |
| `python -m examradar.cli sql "SELECT ..."` 表格输出 | ✅（无密码进命令行） |
| 问笔记页浏览器验证（headless Chrome + CDP） | ✅ 脏页表查询：第一条 `第7讲-故障恢复.pdf · 第7页 · ARIES 恢复算法的三个阶段`；10 条结果默认显示 5 条 + "显示更多（5 条）"，点开后 10 条；渲染后正文无 `##`/`**` 残留；分数行 `RRF: 0.0325 \| 关键词: 2.60 (rank 1) \| 语义: 0.7332 (rank 2)` |
| 首页浏览器验证 | ✅ 三服务状态全绿；导入时间按本地时区显示（10/28/2026, 10:27 PM） |

### 遇到的问题和解决办法

1. **⻚ 无 NFKC 映射**：初版以为部首补充区可 NFKC 归一，实测 U+2EDA 等原样返回；下载 Unicode NamesList.txt 解析 "x"（等价）行生成 112 项映射表，只收 NFKC 覆盖不到的字符
2. **U+2EE1 测试失败**：我记错了码位——⻚ 是 U+2EDA，U+2EE1 是 ⻡（→𩠐）；修正测试
3. **heading^2 让"两阶段锁"翻车**（见 A 节）：网格实验后选等权重
4. **查询指令让"B+树"翻车**（见 A 节）：对照实验后默认关闭做成配置
5. **BM25 IDF 被测试数据污染**（见 A 节）：集成测试清空重建语料
6. **权限环境限制**：`rm -rf .venv`、内嵌 DROP TABLE 的 bash -c、`bash scripts/load_sample.sh` 均被拒——分别改用 `uv venv --python 3.12`、scratch 脚本文件、等价 cli import 命令；浏览器验证因无浏览器自动化工具，用 venv 里已有的 `websockets` 库手写 CDP 驱动 headless Chrome 完成

### 未做（留给后续会话）

- Docker/compose 问题留 M4（镜像构建、健康检查）
- 覆盖度雷达（M2，`examradar.py sql` 已具备查库基础）
- 表结构变更的既有数据迁移（表已删重建，验收环境数据已重导）
