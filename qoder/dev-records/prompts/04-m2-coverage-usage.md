会话 04（里程碑 M2）：考前覆盖雷达 + 使用记录页。

先读 `docs/DEVLOG.md` 了解上个会话的状态，环境和上次一样（seekdb 127.0.0.1:10800，PowerContext 127.0.0.1:18801，密码在 `qoder/.env`；不要启停任何容器）。本会话的验收依据是 `samples/course-db/README.md` 里的"设计真值"一节。

## 先修会话 03 留下的问题

我复核了会话 03：6 条验收检索全部第一条命中，测试全部通过，标题、全角标点、页脚都对了。还剩三个问题，先改：

1. **集成测试会清空整个库**：现在为了避开 BM25 全表统计的影响，测试开始时删除所有课程的数据。用户如果对自己的库跑测试，会丢光数据。改成集成测试使用单独的数据库：设置 `EXAMRADAR_IT=1` 时默认连 `examradar_test`，也可以用 `SEEKDB_TEST_DATABASE` 覆盖。测试只在这个库里建表、导入和清理，绝不碰 `SEEKDB_DATABASE` 指向的库。
2. **PDF 段内硬换行**：库里的正文是"必须先写\n到稳定存储""完\n成"这样的形式，全文检索会把"完成"切成两半。同一段落内，把不以句末标点（。！？；：等）结尾的行和下一行拼起来：中文直接拼接，英文加一个空格。每页第一行（标题）保持独立。拼完后重新导入样例，确认 6 条验收检索仍然全部通过。
3. **测试和样例导入被记成了真实使用**：`scripts/load_sample.sh` 走 CLI 导入，CLI 默认记 `source=real`；浏览器里的操作也一律记成 real。使用数据要如实，开发和测试产生的事件不能算真实使用：
   - `cli import` 加 `--source real|auto`（默认 real）；`load_sample.sh`、`calibrate.py`、测试一律用 auto；
   - 页面带 `?source=auto` 打开时（自动化验证、演示），前端在所有 API 请求里加 `X-ExamRadar-Source: auto`，没有这个参数时记 real。你在本会话里用浏览器验证时都带上 `?source=auto`；
   - 开发库里已有的 usage_events 都是开发和验收时产生的，全部改成 auto。

## 本会话的工作方式

- 本会话用的模型是 Auto。
- 临时脚本放在 `qoder/.cache/scratch/`（已被 git 忽略），用完不用删。`rm` 不在允许的命令里。
- 页面验证：可以把 `playwright` 加进 dev 依赖组，用本机的 Chrome（`channel="chrome"`，不需要下载浏览器），或者沿用你上次写的 CDP 方式。截图存到 `qoder/.cache/scratch/` 下，就能用 Read 查看。
- 非交互模式下的权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip，用 uv；
  - 开发服务器用后台运行方式启动 `.venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800`，结束时用 PID 结束它。

## 本会话任务

1. **考试范围解析**：粘贴的文本 → 知识点列表。去掉编号和"……考试范围"这类标题行；每个知识点有稳定 id（t01、t02…）和名称；括号里的术语（如 3NF、BCNF、2PC）作为该知识点的关键词/别名一起用于检索。
2. **覆盖度**：每个知识点在 notes / slides / paper 中做一条 `DBMS_HYBRID_SEARCH`（RRF），用 `_semantic_score`、`_keyword_score` 等计算证据强度，判定 covered / thin / missing。要求：
   - 规则简单、可解释：界面上能说清"为什么判为薄弱 / 缺失"（例如：最强证据是哪一段、多少分、离阈值多远）；
   - 阈值可配置，写 `scripts/calibrate.py` 在样例上校准，并输出每个知识点的分数分布；
   - 注意两个坑：cosine 下 `_semantic_score`=(1+cos)/2，不相关文本也常在 0.6 以上；IK 自然语言模式下"与""的"这类常见字也会产生关键词分数，不要把"有关键词分数"直接当成"有覆盖"。
3. **考试权重**：往年试卷的每道题（已按题切块，带分值）**只归属到最相关的一个知识点**，知识点的考试权重 = 归属给它的题目分值之和。归属依据（哪道题、几分、相似度）要能在界面上展示。
4. **盲区**：按 考试权重 ×（1 − 覆盖度）排序。对 covered / thin 列出支撑段落和出处；对 missing 写明"在笔记、课件和阅读材料里都没有找到"，并列出考到它的试题。
5. **持久化**：一次分析的结果存进 seekdb（例如 coverage_runs / coverage_items）。`GET /api/coverage/latest?course_id=` 返回最近一次分析，后续首页和复习教练会用它来挑选薄弱知识点。
6. **API**：`POST /api/coverage/analyze`（入参：course_id、范围文本或知识点列表）、`GET /api/coverage/latest`。分析时也要写 usage_events。
7. **雷达页**：粘贴范围 → ECharts 雷达图（覆盖度、考试权重两个系列）+ 盲区清单（可展开证据、出处、分数）+ 每个知识点的判定理由。页面上提供"载入示例考试范围"的按钮，方便评审体验。
8. **使用记录**：`GET /api/usage/stats`、`GET /api/usage/export?format=csv|json`；使用记录页展示会话数、累计学习时长、检索 / 分析 / 答题次数、按天趋势。默认只统计 `source=real`，页面上可切换查看 `auto`。按天趋势按浏览器的时区分天，时区由前端作为 API 参数传入。（学习会话的开始 / 结束接口在 M3 实现，这里先把统计和展示做好，时长按已有事件计算。）
9. **测试**：覆盖度判定、题目归属、范围解析的单元测试；`analyze` 接口的集成测试。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- 用 `samples/course-db/syllabus.txt` 分析，结果与 README "设计真值"表一致：10 个知识点的覆盖判定、11 道题的归属全部一致，盲区第一名是 t04（25 分）。如果有做不到的，写清楚是哪一条、为什么，**不要为了凑结果去改样例数据，也不要写针对样例的特判**。
- 在 DEVLOG 里贴出每个知识点的证据分数和它离阈值有多远，说明阈值不是"刚好卡过去"的。
- 雷达页、使用记录页在浏览器里可用（验证时带 `?source=auto`）；使用记录页切换到 auto 能看到本会话产生的数据，默认的 real 视图里没有本会话产生的事件；导出的 CSV 能打开。
- `uv run pytest` 和 `export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过；跑完集成测试后，开发库里 db101 的文档数和块数不变。
- 6 条验收检索仍然全部第一条命中。

结束前在 `docs/DEVLOG.md` 追加本会话记录（做了什么、遇到的问题和解决办法、验收结果）。不要修改 `dev-records/` 和 `samples/`；会话结束前关掉你启动的进程。
