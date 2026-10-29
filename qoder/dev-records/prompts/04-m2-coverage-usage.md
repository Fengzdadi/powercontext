会话 04（里程碑 M2）：考前覆盖雷达 + 使用记录页。

先读 `docs/DEVLOG.md` 了解上个会话的状态，环境和上次一样（seekdb 127.0.0.1:10800，PowerContext 127.0.0.1:18801，密码在 `qoder/.env`；不要启停任何容器）。`samples/course-db/README.md` 新增了"设计真值"一节，`syllabus.txt` 第 10 条加了"（2PC）"。

{{REVIEW}}

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
8. **使用记录**：`GET /api/usage/stats`、`GET /api/usage/export?format=csv|json`；使用记录页展示会话数、累计学习时长、检索 / 分析 / 答题次数、按天趋势。默认只统计 `source=real`，页面上可切换查看 `auto`。（学习会话的开始 / 结束接口在 M3 实现，这里先把统计和展示做好，时长按已有事件计算。）
9. **测试**：覆盖度判定、题目归属、范围解析的单元测试；`analyze` 接口的集成测试。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- 用 `samples/course-db/syllabus.txt` 分析，结果与 README "设计真值"表一致：10 个知识点的覆盖判定、11 道题的归属全部一致，盲区第一名是 t04（25 分）。如果有做不到的，写清楚是哪一条、为什么，**不要为了凑结果去改样例数据，也不要写针对样例的特判**。
- 在 DEVLOG 里贴出每个知识点的证据分数和它离阈值有多远，说明阈值不是"刚好卡过去"的。
- 雷达页、使用记录页在浏览器里可用；使用记录页能看到本会话产生的数据，导出的 CSV 能打开。
- `uv run pytest` 和 `EXAMRADAR_IT=1 uv run pytest -m integration` 全部通过。

结束前在 `docs/DEVLOG.md` 追加本会话记录（做了什么、遇到的问题和解决办法、验收结果）。不要修改 `dev-records/` 和 `samples/`；会话结束前关掉你启动的进程。
