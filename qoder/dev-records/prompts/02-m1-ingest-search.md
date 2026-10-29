会话 02（里程碑 M1）：工程骨架 + 资料导入 + 问笔记。

## 先看我对 docs/PLAN.md 的审阅意见（以这几条为准，请顺手把 PLAN.md 对应处改掉）

1. compose 里 app 访问 PowerContext 要用容器端口 `http://powercontext:8000`（18801 只是宿主机映射端口）。app 服务的 `SEEKDB_HOST/PORT`、`POWERCONTEXT_URL` 在 compose 里直接写容器网络地址；`.env` 只提供密码、宿主机端口和可选的模型配置。
2. `.env.example` 只放一看就是占位的值（如 `change-me`），不要出现像真实密码的字符串。
3. 往年试卷要**按题切块**：识别 `1.（5 分）` 这类题号和分值，把分值存成单独的列；否则一页里几道题混在一个块里，之后算考试权重会错。课件 PDF 按页切块，页标题取该页第一行；Markdown 按标题层级切块并保留标题路径，过长的节再按段落切。
4. cosine 索引下 `_semantic_score` = (1+cos)/2，bge 模型下不相关的文本也常有 0.6 以上，M2 校准阈值时要注意（本会话不做覆盖度）。
5. Leitner 答错应回到 1 号盒（经典做法），不是 box-1（M3 再做）。

## 环境（已经起好）

- `samples/course-db/` 已就位，先读它的 `README.md`：3 份 Markdown 笔记、课件 PDF、往年试卷 PDF、英文阅读 PDF、`syllabus.txt`。目录到类型的对应：`notes/`→notes、`slides/`→slides、`exams/`→exam、`papers/`→paper。
- seekdb 1.4.0：`127.0.0.1:10800`，用户 root，密码在 `qoder/.env`（已被 .gitignore 忽略；不要提交，也不要把密码打印到终端或写进文档）。要直接查库用：
  `docker exec examradar-dev-seekdb mysql -h127.0.0.1 -P2881 -uroot -p"<密码>" examradar -e "..."`
- PowerContext 1.4.1：`http://127.0.0.1:18801`（本会话用不上，可 `curl` 一下 `/health/ready`）。
- **不要**启动、停止或删除任何 docker 容器，也不要 `docker compose up`（这些端口已被占用）。compose 文件照常写，我之后会统一验证。
- 开发服务器用 18800 端口；会话结束前把你启动的进程关掉。

## 本会话任务

1. **工程骨架**：`app/pyproject.toml`（Python 3.12，uv 管理依赖并生成 `uv.lock`）、配置（pydantic-settings，本地开发读取 `qoder/.env`）、FastAPI 入口、静态页面托管、`GET /api/health`（报告 seekdb 连接、向量模型、PowerContext 是否可达）。
2. **seekdb**：启动时幂等建库建表（documents / chunks / usage_events 等，试卷题目的分值列等你按需补全）。
3. **切块**：Markdown / TXT / PDF。每块带文件名、页码、标题路径、doc_kind。PDF 抽出来的文字要清洗干净（中文行尾不要插空格，英文按单词拼接），**并检查抽出来的字符是否就是正常的汉字**。
4. **向量化**：fastembed + `BAAI/bge-small-zh-v1.5`（512 维），批量处理；可选切到 OpenAI 兼容 embeddings。
5. **导入**：`POST /api/documents`（multipart）；命令行 `python -m examradar.cli import <路径> --course db101 --kind notes`（支持目录批量）；`scripts/load_sample.sh` 一键导入 `samples/course-db`。同一文件（按内容 sha256）重复导入不产生重复块。
6. **问笔记**：`POST /api/search`，一条 `DBMS_HYBRID_SEARCH` + RRF；默认在 notes/slides/paper 中检索，可选把 exam 也包括进来。返回段落、出处（文件 · 页 · 标题路径）、两路分数和排名；响应里附上实际执行的检索 JSON 和 `GET_SQL` 的结果，便于验证和在界面上展示"seekdb 实际执行了什么"。没有配置大模型时只返回段落。
7. **使用记录**：导入和检索都写 usage_events。默认 `source=real`；请求带 `X-ExamRadar-Source: auto` 头时记为 `auto`（给验证脚本用）。
8. **前端**：先做首页、导入页、问笔记页的可用版本（中文界面，简洁清楚）。ECharts 下载官方发布的 `echarts.min.js` 放进 `app/static/lib/`，记下版本和来源。
9. **测试**：pytest 单元测试（切块、文本清洗、检索 JSON 的构造与转义）+ 对真实 seekdb 的集成测试（标记 `integration`，默认跳过，`EXAMRADAR_IT=1` 时运行）。

## 验收标准（请逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- `uv run pytest` 全部通过；`EXAMRADAR_IT=1 uv run pytest -m integration` 通过。
- `scripts/load_sample.sh` 导入 6 份资料并打印每份的块数；再运行一次不重复入库。往年试卷切成 11 个题目块，分值合计 100。
- 下面每条检索的**第一条结果**要命中正确出处，并且 `_keyword_score` 不为空（说明全文索引确实命中，不是只靠向量）：
  | 检索 | 范围 | 期望第一条 |
  | --- | --- | --- |
  | B+树插入时结点分裂 | 默认 | 笔记 03 的 3.3 节 |
  | 脏页表 | 默认 | 课件第 7 页（ARIES 三个阶段） |
  | 先写日志原则 | 默认 | 课件第 4 页 |
  | coordinator crash blocking | 默认 | 英文阅读材料第 2 页 |
  | 两阶段锁能不能避免死锁 | 默认 | 笔记 05 的 5.3 或 5.4 节 |
  | 函数依赖 候选码 | 含 exam | 往年试卷第 4 题 |
- `uv run uvicorn ...` 在 18800 端口启动后，首页、导入页、问笔记页都能在浏览器打开并正常工作（导入页能上传一个文件，问笔记页能显示带出处的结果）。

结束前在 `docs/DEVLOG.md` 追加本会话记录：做了什么、遇到的问题和解决办法、验收结果。不要修改 `dev-records/` 和 `samples/`。
