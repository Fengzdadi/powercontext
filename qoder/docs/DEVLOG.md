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
