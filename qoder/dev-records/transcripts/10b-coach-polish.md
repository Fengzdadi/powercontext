# Qoder 会话记录：10b-coach-polish

| 项目 | 值 |
| --- | --- |
| 会话 ID | `aa07df25-90a3-495e-bbaf-22c2ed429508` |
| Qoder CLI | 1.1.80，模型 GLM-5.3，权限模式 acceptEdits |
| 工作目录 | `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder` |
| 开始 / 结束 | 2026-10-29T01:00:33-0400 / 2026-10-29T01:17:23-0400 |
| 轮数 / 耗时 | 105 轮 / 16.7 分钟 |
| Credits | 523.1254599999999（逐条请求累加 523.13） |
| 原始记录 | `sessions/10b-coach-polish.jsonl`（完整 stream-json） |

## 产品负责人的指令

会话 10b：修正复习教练和我的记忆页的几处问题。

先读 `docs/DEVLOG.md` 里会话 07 和会话 10 两节。环境同前：seekdb 127.0.0.1:10800，PowerContext 127.0.0.1:18801，密码在 `qoder/.env`；不要启停开发用的容器。

我在开发库上用一个新学习者走了一遍：开始会话 → 做 4 道题（自评"不会"、填空答错、再自评"不会"、填空答对）→ 结束 → 我的记忆。PowerContext 的读写、Leitner 盒号、revision 都对。下面这些要改。

## 要改的问题

1. **同一会话里反复出同一道题**
   - 现象：4 道题依次是 t04 自测（第4题）、t08 填空、t04 自测（又是第4题）、t08 填空（同一个空）。复习计划里的 t02、t01、t05 一直没轮到。
   - 要求：
     - 刚答过的知识点，至少隔 2 道别的题再出；
     - 计划里的知识点先轮一遍，再回到答错的；
     - t04 有第4题、第5题两道往年原题，自测题在这个知识点的原题之间轮换。
2. **出处里题号写了两遍**：自测题的出处是"2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 第4题（15.0分）"。去掉重复，分值写成"15 分"。
3. **复习计划的开场白里同一个知识点出现两次**："上次你在『函数依赖与范式（3NF、BCNF）』上错了 2 次，先复习它；……『函数依赖与范式（3NF、BCNF）』往年考 25 分但笔记里没有"。同一个知识点合成一句。
4. **我的记忆页的掌握度卡片表**：1440px 宽度下，"盒号""对/错"的表头和"下次复习"的日期折成了两行。这几列不折行。
5. **第5题的原文末尾带上了下一大题的标题**：覆盖雷达 t04 的关联试题里，第5题原文以"三、查询处理与事务（共 50 分）"结尾。
   - 切题时，把大题标题（"一、""二、"……开头、带"共 N 分"的行）从上一题的原文里去掉。
   - 改完在开发库上重新导入这份试卷（先删除再导入），再跑一次分析：10 个判定、11 道题的归属仍与设计真值一致，第5题原文不再带大题标题。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- `cd app && uv run pytest` 和 `cd app && export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过。
- 新增单测：
  - 出题顺序：同一会话里同一个知识点不连续出现，计划里的知识点先轮一遍；
  - 自测题在同一知识点的多道原题之间轮换；
  - 开场白里每个知识点只出现一次。
- 开发库上用一个新的学习者名字（带上时间）连做 6 道题（全部答错或自评"不会"），把 6 道题的知识点、题型、出处列进 DEVLOG。
- 浏览器验证（`?source=auto`，1440×900）：我的记忆页掌握度卡片表的表头和日期单元格只有一行高。截图，用 Read 看一遍。
- 端到端：`docker compose -p examradar-ci --env-file .env.ci up -d --build` 之后，`scripts/e2e_verify.py --app-url http://127.0.0.1:18807` 全部 ✅，报告写入 `docs/validation/e2e-report.md`。如果复习教练一步依赖旧的出题顺序，一起改。
- 会话结束前 `docker compose -p examradar-ci --env-file .env.ci down -v`，关掉你启动的进程。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。
- docker 命令只能这样写：`docker compose -p examradar-ci --env-file .env.ci <子命令>`，子命令为 `up -d --build`、`ps`、`logs <服务>`、`down -v`。CI 栈占用 18805–18807。
- 开发服务器只用 18800 端口：Bash 设为后台运行（run_in_background），命令是 `cd app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800`，末尾不要加 `&`；结束时用 PID 关掉。
- 浏览器验证用 `.cache/scratch/pwvenv/bin/python`，本机 Chrome（`channel="chrome"`），截图存到 `.cache/scratch/`。
- 权限规则同前：带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；前置环境变量用 `export X=1 && cmd`；不要用 pip，用 uv。

结束前在 `docs/DEVLOG.md` 末尾追加"会话 10b"一节：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。不要修改 `dev-records/` 和 `samples/`。

## 对话过程

<details><summary>Qoder 思考</summary>

Let me start by reading the DEVLOG sections for sessions 07 and 10.

</details>

**Qoder：** 我先读 DEVLOG 的会话 07 和 10 两节，了解背景。

🔧 **Bash** ```bash
grep -n "会话 07\|会话 10" docs/DEVLOG.md | head -20
```

<details><summary>结果</summary>

```
480:**并行说明**：会话 07（M3）、08b、09b 在各自 worktree 进行；本会话只改 `app/examradar/coverage.py`、`app/static/radar.html`、`app/tests/test_coverage.py`、`app/tests/test_integration.py`（`scripts/calibrate.py` 自有 `_ref_str` 与"距离阈值"措辞，不依赖本次改动，未改），并在本文件追加记录。
485:- 修法：新增纯函数 `blind_spot_sort_key(topic_id, blind_spot_score)`（分数降序、同分按 topic_id 升序，None 按 0 处理），`analyze()` 和 `get_latest()` 共用这一处排序；页面"排名"列以接口顺序为准。会话 07 的复习教练经 `get_latest()` 读到的也是与刚分析一致的顺序。
676:## 会话 07 — M3：复习教练 + PowerContext 学习者记忆 + 学习会话（2026-10-28）
842:**并行说明**：本会话在独立 worktree 进行；会话 07 在另一份目录改 `app/`（复习教练与学习者记忆），会话 08b 在另一份目录写 README / VALIDATION / `.env.example`，之后由产品负责人合并。本会话只改 `scripts/e2e_verify.py`、`docs/validation/` 和本 DEVLOG，**`app/` 零改动**（git status 确认）。
846:1. **按步骤组织**：每步一个函数（`step_health` / `step_import` / `step_search` / `step_coverage`），`STEPS` 表串起全流程；每步返回 `StepResult`（若干 `Check` + 报告正文），挂起即停并在报告里记"执行中断"。会话 10 在 `STEPS` 表加"复习教练"一步即可（表里已留注释占位）。
885:- "复习教练"步骤（会话 07 开发中、会话 10 合并后加进 `STEPS` 表）
894:**并行说明**：会话 07（M3）、08a（e2e 脚本）在各自 worktree 进行。本会话只改 `README.md`、`docs/VALIDATION.md`、`docs/images/README.md`、`.env.example`，并在本文件末尾追加记录；`docs/DEPLOY.md` 保留不动，README 以它为基础并链接。`app/`、`scripts/`、`docker*` 零改动（git status 确认）。开发栈（seekdb 10800 / PowerContext 18801，产品负责人启动）全程未动。
898:1. **`README.md`（新增）**：一句话介绍与解决的问题、核心功能表（覆盖判定按会话 05 的考点词证据规则写，明确"语义分只排序、不判定"）、截图占位（`docs/images/*.png`）、Mermaid 架构图、seekdb 与 PowerContext 分工表（各自存什么、在哪个功能起作用、代码位置）、部署方式 A/B、配置项全表、验证样例链接（`docs/VALIDATION.md` + `scripts/e2e_verify.py`）、常见问题、版本表、许可证与第三方组件表。M3 相关内容（复习教练、学习者记忆、PowerContext 读写核对）只按 PLAN.md 写"做什么"，留 `<!-- 会话 10：… -->` 标记，不写接口和命令。
901:4. **`.env.example` 重写**：逐变量中文注释，与 `config.py` 字段一一对应；compose 专用变量（`SEEKDB_HOST_PORT`、`POWERCONTEXT_HOST_PORT`、`HF_ENDPOINT`）单独成节。只放占位值，无任何真实密码/密钥。M3 新增配置留会话 10。未运行 `cp .env.example .env`（开发库配置由 `.env` 提供，覆盖会断开），核对方式为逐字段比对。
996:1. **`docs/DEPLOY.md` §5 应用变量表落后于会话 05**：仍列已废弃的 `COVERAGE_T_COVERED`(0.55)、`COVERAGE_T_THIN`(0.20)、`COVERAGE_KW_SCALE`(10.0)，缺现行的 `COVERAGE_TERM_RATIO_COVERED`、`COVERAGE_SUPPORT_CHARS`、`COVERAGE_MIN_BODY_CHARS` 和 `USAGE_SESSION_GAP_MINUTES`/`USAGE_MINUTES_PER_EVENT`（README 和 `.env.example` 均按 config.py 现行字段写）。任务规定 DEPLOY.md 保留不动，建议会话 10 统一修订。
997:2. **`docs/DEPLOY.md` SEEKDB_PASSWORD 行残留疑问句**："（compose 会自动设一个随机值吗？不会，请自己改掉 change-me）"——像是自问自答的草稿痕迹，可读性欠佳，待会话 10 顺手清理。
1002:- M3 相关文档（复习教练、学习者记忆、PowerContext 读写核对、quiz/memory 截图、M3 配置项）：会话 10 合并后补齐，README/VALIDATION 已留 `<!-- 会话 10：… -->` 标记
1004:- `docs/DEPLOY.md` 变量表与 config.py 的同步：见 F-1，建议随会话 10 处理
1006:## 会话 10 — M3 合并与集成：复习教练接会话 05 覆盖结果、导航/使用记录/文档收尾（2026-10-29）
1009:**任务**：把会话 07 的 M3（复习教练、学习者记忆、学习会话）与会话 05–08b 的工作集成到 `eco-qoder` 分支。开发栈（seekdb 10800 / PowerContext 18801）全程未动；本会话只使用 18800（开发服务器）与 18805–18807（examradar-ci 栈）。
1013:1. **合并收尾检查**：config.py / index.html / ask.html 的自动合并结果人工核对；确认会话 07 代码未引用会话 05 已删除的旧覆盖字段（`effective_database`、旧覆盖分数字段）。发现并修复 `usage_session_gap_minutes` / `usage_minutes_per_event` 成为死配置（见下 4），从 config.py 删除。
1022:7. **文档补全**（删全部 `<!-- 会话 10：… -->` 标记）：
1061:1. **t04（missing）出题材料跑偏**：会话 07 的 GROUP 出题用 hybrid 检索选材，t04 的"函数依赖"在语料里只在试卷题干出现，检索可能带回其他章节段落。改为 `_term_matched_chunks`（match_variant 全块扫描），missing 走 `make_self_test_question`、thin/covered 只从含考点词的段落出题；无覆盖数据时保留 hybrid 兜底。
```

</details>

🔧 **Bash** ```bash
ls qoder/app && ls qoder/app/src 2>/dev/null
```

<details><summary>结果（出错）</summary>

```
Exit code 1
ls: qoder/app: No such file or directory
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/docs/DEVLOG.md`

<details><summary>结果</summary>

```
676	## 会话 07 — M3：复习教练 + PowerContext 学习者记忆 + 学习会话（2026-10-28）
677	
678	> 本会话运行在独立 worktree（分支 `eco-qoder-m3`），dev 库 `examradar_m3` / 集成测试库
679	> `examradar_m3_test`，应用端口 18802。只新增文件 + 少量允许范围内的既有文件修改
680	> （main.py / config.py / routes/search.py / static/index.html / static/ask.html /
681	> docs/PLAN.md），未触碰 seekdb.py / coverage.py 等禁改文件。
682	
683	### 做了什么
684	
685	**新增模块**（均在 `app/examradar/`）：
686	
687	- `pc_client.py`（重写扩展）：PowerContext 完整客户端。scope 幂等创建（idempotency_key）；
688	  原子记忆创建 / 读取（ETag 解析 `revision:N`）/ 原子替换（先 GET 最新 ETag，PUT 带
689	  If-Match，412 时重试 2 次）；tags 读写（独立 ETag）；artifact-handles（`mastery-<topic_id>`、
690	  `review-plan`，404 → None）；artifact-tags/query（绕过 1.4.1 的 list+tags 422 bug）；
691	  revision 历史（列表无正文，逐个 GET `/revisions/{n}`）；remember 追加；bootstrap
692	  （enabled/lifecycle/startup/integration/event_id）；prepare（BEGIN/END 标记 JSON 解析）；
693	  每次调用的请求/响应摘要进 `CALL_LOG`（deque 300 条，memory 页展示）；
694	  连接错误 / 5xx → `PowerContextUnavailable` 优雅降级。
695	- `mastery.py`：Leitner 盒子递推（答对 +1 最多 5；答错或"不会"回到 1 号盒，间隔
696	  1/2/4/7/14 天）、掌握度卡片文本格式化/解析（首行人类可读，其余 key:value 机读）、
697	  错题文本、复习计划文本、开场白生成（"上次你在『X』上错了 N 次，先复习它"）、
698	  会话小结、`learner_hash`（sha256 前 8 位）、填空/选择题判分（NFKC 归一化：全半角、
699	  大小写、空白）。
700	- `llm.py`：OpenAI 兼容客户端（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），Ollama 走
701	  `options.num_ctx`（每次相同值避免模型重载），`/no_think` 尽力关闭 qwen3.5 思考；
702	  宽容 JSON 解析（去围栏、括号配平、截断兜底）；未配置时 `configured=False` 走规则路径。
703	- `learning_store.py`：新表 `learning_sessions`（session_id/scope_id/learner_hash/
704	  course_id/started_at/last_event_at/ended_at）与 `quiz_questions`（题目、payload、
705	  答案、correct、box_before/after）；30 分钟无事件自动结束（ended_at=last_event_at，
706	  时长按最后事件计）；隐私：只存名字哈希，明文名字只进本机 PowerContext Scope。
707	- `coach.py`：教练核心。选题优先级 到期复习 > 覆盖盲区（thin/missing 按盲区分）>
708	  其余，避免连续重复同一道题；规则填空题（挖空点：主题关键词 > ≥3 字符拉丁词，
709	  排除"第 N 章/节/讲"和数字；题干跳过 markdown `#`/`>` 结构行）；missing 主题给
710	  往年原题自测（会/模糊/不会 + "笔记里没有这部分，建议先补"）；LLM 出题（选择/
711	  简答 JSON，含参考答案/解析/chunk 出处，代码里再校验后才入库）；LLM 简答判分
712	  （correct + misconception 误区描述）；掌握度卡片 upsert（handle → 读旧卡 → apply →
713	  替换）；错题记忆 remember；复习计划记忆（handle `review-plan`，tags 含
714	  `bootstrap-context`，首行即下次开场白）。
715	  coverage 数据只通过 `coverage.get_latest(course_id)` 读取，使用的字段集中在
… （共 200 行，此处省略 160 行，完整内容见 .jsonl）
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/docs/DEVLOG.md`

<details><summary>结果</summary>

````
1006	## 会话 10 — M3 合并与集成：复习教练接会话 05 覆盖结果、导航/使用记录/文档收尾（2026-10-29）
1007	
1008	**参与者**：产品负责人（任务输入）、Qoder（集成与验证）
1009	**任务**：把会话 07 的 M3（复习教练、学习者记忆、学习会话）与会话 05–08b 的工作集成到 `eco-qoder` 分支。开发栈（seekdb 10800 / PowerContext 18801）全程未动；本会话只使用 18800（开发服务器）与 18805–18807（examradar-ci 栈）。
1010	
1011	### A. 做了什么
1012	
1013	1. **合并收尾检查**：config.py / index.html / ask.html 的自动合并结果人工核对；确认会话 07 代码未引用会话 05 已删除的旧覆盖字段（`effective_database`、旧覆盖分数字段）。发现并修复 `usage_session_gap_minutes` / `usage_minutes_per_event` 成为死配置（见下 4），从 config.py 删除。
1014	2. **coach 接会话 05 覆盖结果**（`app/examradar/coach.py`、`routes/quiz.py`）：
1015	   - `coverage_snapshot()` 映射会话 05 新字段：`terms[].{term,aliases,found,chunks}`、`best_evidence`、`support_chunks/support_chars/reason`，items 已按 `blind_spot_score` 降序（沿用 latest 排序，不重排）；
1016	   - 新增 `_term_matched_chunks(course_id, topic)`：用 `coverage.match_variant` 在全部资料块里找**考点词出现的段落**作为出题材料，替代原 hybrid 检索选材——保证 thin/covered 知识点的题目原文确实属于该知识点（修复 t04 出 GROUP 题材跑偏的问题）；无覆盖数据（topic 无 terms）时保留 hybrid 兜底；
1017	   - missing 知识点走往年原题自测（`make_self_test_question`）；挖空候选优先**找到的考点词本身**（term + aliases，要求 variant 在正文出现），其次 keywords / 拉丁术语 / 标题词。
1018	3. **导航统一**：7 个页面（index/import/ask/radar/coach/memory/usage）同一套导航，顺序"首页、导入资料、问笔记、覆盖雷达、复习教练、我的记忆、使用记录"；coach/memory 页补挂 source.js（`?source=auto` 跨页保持）；每页 viewport 后加内联空图标 `<link rel="icon" href="data:,">`，消除 favicon 404。
1019	4. **使用记录接学习会话**（`seekdb.py` / `config.py` / `test_usage.py` 重写）：`compute_usage_stats` 接收 learning_sessions 行，累计学习时长 = 各会话（ended_at or last_event_at）− started_at 之和，按 source 过滤（session_start 事件在 events 里才计）；answer/quiz 事件计入 `quiz_count` 与按天"答题"桶；`session_count` 按 session_start 事件计。删除事件间隔估算逻辑与 `USAGE_*` 两个死配置。导出（JSON/CSV）不含学习者明文——使用事件里只存 sha256 前 8 位哈希（`mastery.learner_hash`）。
1020	5. **`.env.example` 补 M3 配置**：`POWERCONTEXT_TIMEOUT_SECONDS`（含降级语义注释）、`SESSION_IDLE_MINUTES`、`PC_CONTEXT_MAX_BYTES`、`LLM_MAX_CONTEXT_BYTES`、LLM 节扩 Ollama 示例与 `LLM_NUM_CTX` 注释；删 USAGE 两项。`docker-compose.yml` app 服务透传 `LLM_*` 与 `POWERCONTEXT_TIMEOUT_SECONDS`（`${…:-}` 空串安全，`llm.configured` 要求 base_url 和 model 均非空）。
1021	6. **`scripts/e2e_verify.py` 加复习教练步骤**（`step_coach`，约 250 行）：新学习者（名字带时间戳，断言首会话 bootstrap 为空）→ t04 自测答"不会"（错，prepare 召回断言在第二题）→ 同知识点答对（盒 1→2、卡片 revision 递增）→ t08 填空答错（断言挖空即考点词）→ 结束 → 新会话开场白提到答错知识点（bootstrap ready）→ PC 直查（review-plan handle 一致、tags 含 bootstrap-context、t04 卡 revisions ≥2 且盒 1→盒 2）→ usage stats（quiz ≥3、session ≥1）→ 导出不含学习者明文。报告正文含两道题原文、PC 读写明细表（13 行：方向/接口/artifact/revision/标签）、revision 历史、prepare 召回错题。
1022	7. **文档补全**（删全部 `<!-- 会话 10：… -->` 标记）：
1023	   - README：功能表加复习教练/我的记忆两行、截图表加 coach.png/memory.png、架构图 PC 线改"健康检查 / 学习者记忆读写"、PowerContext 节重写为实际记忆类型表（4 种 kind/handle/标签/读写时机+代码位置）+ 优雅降级说明、seekdb 节加 learning_sessions/quiz_questions、配置表同步 M3 变量、第 9 节改实际功能介绍；
1024	   - VALIDATION：§5 学习时长措辞改"按学习会话计算"、§7 重写为完整 PowerContext 记忆核对（界面 + 8 步 curl 命令链 + 预期结果实测摘录 + PC 直查 handle/artifact/revisions/tags + 隐私核对）、§8 补 e2e 复习教练步骤说明；
1025	   - DEPLOY：变量表删旧阈值三项（`COVERAGE_T_COVERED`/`COVERAGE_T_THIN`/`COVERAGE_KW_SCALE`）换现行三项，补 M3 变量，删 SEEKDB_PASSWORD 行草稿疑问句（即会话 08b F-1/F-2 待办）；
1026	   - docs/images/README.md：加 coach.png / memory.png 两行（不用 quiz.png）。
1027	
1028	### B. t04 / t08 出题原文（实测，开发服务器 18800）
1029	
1030	t04（missing，盲区第一，25 分）走往年原题自测：
1031	
1032	```
1033	4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。 （1）求 R 的所有候选码；（2）求属性集闭包 (A) +；（3）判断 R 最高属于第几范式，说明理由。
1034	```
1035	
1036	- 出处：`2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 第4题（15.0分）`；提示："笔记里没有这部分，建议先补。"
1037	
1038	t08（thin）填空题，挖空即考点词、出处为找到考点词的段落：
1039	
1040	```
1041	填空：SQL 标准定义了四个＿＿＿：读未提交、读已提交、可重复读、可串行化。（4 个字）
1042	```
1043	
1044	- 出处：`05-事务与并发控制.md · 第5章 事务与并发控制（课堂笔记） > 5.5 隔离级别（只记了个大概，课上讲得快）`；正确答案：隔离级别（t08 的考点词）。
1045	
… （共 67 行，此处省略 27 行，完整内容见 .jsonl）
````

</details>

<details><summary>Qoder 思考</summary>

Now let me look at the relevant code files: coach.py, mastery.py, routes/quiz.py, memory.html, coverage.py (question splitting for issue 5), and tests. Let me explore.

</details>

**Qoder：** 现在看代码。先找到相关文件。

🔧 **Bash** ```bash
ls /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/static /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests
```

<details><summary>结果</summary>

```
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar:
__init__.py
__main__.py
chunker.py
cleaner.py
cli.py
coach.py
config.py
coverage.py
embedding.py
ingest.py
learning_store.py
llm.py
main.py
mastery.py
pc_client.py
routes
seekdb.py
syllabus.py

/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes:
__init__.py
coverage.py
documents.py
health.py
memory.py
quiz.py
search.py
sessions.py
usage.py

/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/static:
ask.html
coach.html
css
import.html
index.html
js
lib
memory.html
… （共 60 行，此处省略 20 行，完整内容见 .jsonl）
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py`

<details><summary>结果</summary>

```
1	"""复习教练：选题、出题（规则 / LLM）、判分、记忆写入编排。
2	
3	覆盖结果只通过 coverage.get_latest() 读取，用到的字段集中在
4	_coverage_snapshot() 一个函数里（合并时对照 DEVLOG 的字段清单）。
5	
6	PowerContext 不可用时优雅降级：出题判分照常进行，返回 memory_ok=False，
7	界面提示"记忆服务暂不可用"。
8	"""
9	from __future__ import annotations
10	
11	import json
12	import re
13	import uuid
14	from datetime import date, datetime, timezone
15	from typing import Optional
16	
17	from .config import get_settings
18	from .llm import LLMClient, LLMError, get_llm_client
19	from .mastery import (
20	    MasteryState, ReviewPlanData, build_opening_line, build_review_plan,
21	    format_mastery_text, format_mistake_text, format_session_summary,
22	    grade_choice, grade_fill, learner_hash, parse_mastery_text, parse_review_plan,
23	)
24	from .pc_client import (
25	    PowerContextClient, PowerContextUnavailable, bootstrap_opening_line,
26	    parse_prepared_content,
27	)
28	from .seekdb import (
29	    get_connection, get_coverage_chunks, hybrid_search, insert_usage_event,
30	)
31	from .syllabus import normalize_for_match
32	from . import coverage as coverage_mod
33	from . import learning_store
34	
35	TOPIC_TAGS_LIMIT = 16
36	
37	MEMORY_NOTICE = "记忆服务暂不可用"
38	
39	SELF_RATINGS = ["会", "模糊", "不会"]
40	
… （共 595 行，此处省略 555 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now the routes/quiz.py which manages session state / question selection per question.

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`

<details><summary>结果</summary>

```
1	"""出题与判分路由：quiz/next、quiz/answer。
2	
3	出题优先级：到期复习 > 覆盖分析 thin/missing（按盲区分）> 其余；
4	同一会话不连续重复同一道题。进入知识点前 context/prepare 召回历史错题。
5	"""
6	from __future__ import annotations
7	
8	import uuid
9	from typing import Optional
10	
11	from fastapi import APIRouter, Header
12	from fastapi.responses import JSONResponse
13	from pydantic import BaseModel
14	
15	from ..config import get_settings
16	from ..llm import get_llm_client
17	from ..mastery import MasteryState, grade_choice, grade_fill, parse_mastery_text
18	from ..pc_client import PowerContextClient, PowerContextUnavailable, parse_prepared_content
19	from ..seekdb import insert_usage_event
20	from .. import learning_store
21	from ..coach import (
22	    MEMORY_NOTICE, SELF_RATINGS, _fetch_chunk, _search_topic_chunks,
23	    _term_matched_chunks, build_review_plan_inputs, coverage_snapshot,
24	    grade_short_with_llm, load_mastery_states, make_fill_question,
25	    make_llm_question, make_self_test_question, remember_mistake, select_topic,
26	    update_review_plan, upsert_mastery_card,
27	)
28	
29	router = APIRouter()
30	
31	
32	class QuizNextRequest(BaseModel):
33	    session_id: str
34	    topic_id: Optional[str] = None
35	    question_type: Optional[str] = None  # fill / choice / short；缺省自动
36	
37	
38	class QuizAnswerRequest(BaseModel):
39	    question_id: str
40	    session_id: Optional[str] = None
… （共 353 行，此处省略 313 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now let's understand the issue 1: repeated same topic. select_topic only avoids `last_topic_id` (immediately previous). The flow: Q1 t04 self-test (answered "不会" → wrong, box 1). Q2: due topics? t04 answered wrong → box stays 1, next_review = today+1? Let me check mastery apply_answer: wrong → box 1, interval 1 day. So next_review is tomorrow — not due. Then coverage weak pool sorted by blind_spot desc: t04 (25) first... but last_topic is t04 so skip → t08. Q2 t08 fill, answered wrong. Q3: last_topic t08 → select t04 again (blind spot highest). Q4: last_topic t04 → t08. So it alternates t04/t08 forever, never reaching t02/t01/t05.

Requirements:
- Just-answered topic: at least 2 other questions gap (隔 2 道别的题再出).
- Plan topics rotate through all first, then return to wrong ones.
- t04 has two past exam questions (第4题、第5题); self-test should rotate among them.

Issue 2: source label duplicate "第4题 · 第4题（15.0分）" — heading is "第4题" for exam chunks and question_no also "第4题". Look at `_chunk_source`: parts include heading then question_no. For exam chunk heading = "第4题（15.0分）"? Actually label is "2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 第4题（15.0分）". So heading="第4题", question_no=4, points=15.0. Need to dedupe: if heading already matches 第N题, don't append question_no again; and points format "15 分" not "15.0分".

Wait — also issue 5: the chunk content for question 5 includes trailing section header "三、查询处理与事务（共 50 分）". That's in the chunker or cleaner for exam splitting. The coverage radar t04's related exam question #5's content ends with the next section title. So the exam question content from chunker includes the section header line. Need to fix the exam question extraction to strip section-title lines ("一、","二、"... with "共 N 分"). Where is that? Probably in chunker.py or syllabus.py — exam questions come from coverage analyze (exam_questions[].content). Let me look at coverage.py for exam question extraction.

Issue 3: opening line mentions same topic twice — build_opening_line in mastery.py. Need to merge mentions.

Issue 4: memory.html table columns nowrap.

Let me look at mastery.py and the chunker/coverage exam extraction.

</details>

**Qoder：** 现在看 mastery.py（开场白、计划）和 chunker/coverage 里试卷切题的逻辑。

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/mastery.py`

<details><summary>结果</summary>

```
1	"""Leitner 掌握度递推 + 记忆文本格式（mastery / mistake / plan / session）。
2	
3	写进记忆的只有判分代码确定的事实：对错、学生自己的答案、正确答案、出处。
4	掌握度卡片和错题记忆的文本里都写上知识点 id 和名称，
5	保证 PowerContext 全文召回（"t08 隔离级别与 MVCC" 这类查询）能命中。
6	
7	卡片 / 计划文本格式：第一行给人看，后面几行 `key: value` 机器可解析。
8	"""
9	from __future__ import annotations
10	
11	import hashlib
12	import unicodedata
13	from dataclasses import dataclass, field
14	from datetime import date, datetime, timedelta, timezone
15	from typing import Optional
16	
17	from .config import get_settings
18	
19	
20	def learner_hash(learner: str) -> str:
21	    """学习者名字的不可逆短哈希（sha256 前 8 位）。使用记录公开材料里只有它。"""
22	    return hashlib.sha256(learner.encode("utf-8")).hexdigest()[:8]
23	
24	
25	# --------------------------------------------------------------------- Leitner
26	
27	def next_box(box: int, correct: bool) -> int:
28	    """答对 +1（最多 5）；答错或"不会"回到 1 号盒（经典 Leitner）。"""
29	    if correct:
30	        return min(5, box + 1)
31	    return 1
32	
33	
34	def next_review(box: int, today: Optional[date] = None) -> date:
35	    intervals = get_settings().leitner_intervals_list
36	    days = intervals[box - 1]
37	    today = today or datetime.now(timezone.utc).date()
38	    return today + timedelta(days=days)
39	
40	
… （共 231 行，此处省略 191 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now the chunker for exam questions. Let me look at chunker.py and where exam question content is extracted (with the section header issue).

</details>

🔧 **TaskCreate** ```json
{
 "description": "quiz/next 选题：刚答过的知识点至少隔 2 道题；计划知识点先轮一遍再回到答错的；自测题在同一知识点多道原题间轮换",
 "subject": "修复出题顺序（重复知识点、原题轮换）"
}
```

🔧 **TaskCreate** ```json
{
 "description": "_chunk_source：heading 已含第N题时不再重复追加 question_no；points 格式\"15 分\"",
 "subject": "修出处题号重复与分值格式"
}
```

🔧 **TaskCreate** ```json
{
 "description": "build_opening_line：同一知识点只出现一次（wrong 与 blind_missing 合并）",
 "subject": "修开场白同一知识点出现两次"
}
```

🔧 **TaskCreate** ```json
{
 "description": "memory.html 掌握度卡片表 1440px 下盒号/对/错表头与日期不折行",
 "subject": "修记忆页表格列折行"
}
```

🔧 **TaskCreate** ```json
{
 "description": "切题时去掉大题标题行；开发库重导试卷+重跑分析核对真值",
 "subject": "修第5题原文带大题标题（chunker）"
}
```

<details><summary>结果</summary>

```
Task #1 created successfully: 修复出题顺序（重复知识点、原题轮换）
```

</details>

<details><summary>结果</summary>

```
Task #2 created successfully: 修出处题号重复与分值格式
```

</details>

<details><summary>结果</summary>

```
Task #3 created successfully: 修开场白同一知识点出现两次
```

</details>

<details><summary>结果</summary>

```
Task #4 created successfully: 修记忆页表格列折行
```

</details>

<details><summary>结果</summary>

```
Task #5 created successfully: 修第5题原文带大题标题（chunker）
```

</details>

🔧 **TaskCreate** ```json
{
 "description": "新增单测；6 题实测；浏览器截图验证；e2e 全绿；DEVLOG 会话 10b；收尾清理",
 "subject": "验收：单测+集成测试+6题实测+浏览器+e2e+DEVLOG"
}
```

<details><summary>结果</summary>

```
Task #6 created successfully: 验收：单测+集成测试+6题实测+浏览器+e2e+DEVLOG
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/chunker.py`

<details><summary>结果</summary>

```
1	"""Document chunking: Markdown, PDF (slides/paper/exam), plain text."""
2	from __future__ import annotations
3	
4	import re
5	from dataclasses import dataclass, field
6	from pathlib import Path
7	from typing import Optional
8	
9	from .cleaner import clean_extracted_text, normalize_text, strip_footer_page_number, join_intra_paragraph_lines, join_exam_lines
10	
11	
12	@dataclass
13	class Chunk:
14	    content: str
15	    heading: Optional[str] = None
16	    page: Optional[int] = None
17	    question_no: Optional[int] = None
18	    points: Optional[float] = None
19	    chunk_index: int = 0
20	
21	
22	@dataclass
23	class ChunkResult:
24	    chunks: list[Chunk] = field(default_factory=list)
25	    file_type: str = ""
26	    page_count: int = 0
27	
28	
29	def chunk_markdown(text: str, max_chars: int = 1000) -> list[Chunk]:
30	    """Split Markdown by heading hierarchy, preserving heading path.
31	    Long sections are further split by paragraphs if they exceed max_chars."""
32	    lines = text.split("\n")
33	    sections: list[tuple[list[tuple[int, str]], list[str]]] = []
34	
35	    current_path: list[tuple[int, str]] = []
36	    current_lines: list[str] = []
37	
38	    for line in lines:
39	        m = re.match(r"^(#{1,6})\s+(.+)$", line)
40	        if m:
… （共 217 行，此处省略 177 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Issue 5: In `chunk_exam_pdf`, the content for question i goes from match i start to match i+1 start. If question 4 is the last question of section 二, and question 5 begins section 三, then question 5's chunk spans from "5.（…分）" to end of file (if it's the last question) — and the text after question 5's stem includes "三、查询处理与事务（共 50 分）"? Wait no — the reported issue: "第5题原文以'三、查询处理与事务（共 50 分）'结尾". So question 5's content ends with the section-3 title. That means question 5 is the last numbered question before section 三 begins, and question 6 follows (matching "6.（N分）"), so question 5's chunk = [start of 5 .. start of 6), which includes the trailing "三、查询处理与事务（共 50 分）" line.

Fix: strip section-title lines from the end of the question content. Requirement: "切题时，把大题标题（'一、''二、'……开头、带'共 N 分'的行）从上一题的原文里去掉。" So remove lines matching ^[一二三四五六七八九十]+、.*共\s*\d+\s*分 (from the content). Better to trim such lines from the end of the chunk. Simplest: after building content, split lines, drop trailing lines matching the section pattern; maybe also drop any such lines anywhere in the chunk (a section title within a question body shouldn't exist, but only trailing ones occur). Requirement says "从上一题的原文里去掉" — trailing. But safe approach: remove all section-title lines from content? If a question's body references "三、查询处理" mid-text it wouldn't match the pattern with 共N分. I'll strip from the end (while loop), which is precise.

Pattern: r"^[一二三四五六七八九十]+\s*[、.．].*共\s*\d+(?:\.\d+)?\s*分" on a stripped line.

Now let me check where the coverage analyze's exam_questions come from — the content in radar comes from chunks, so re-import fixes it.

Also check cleaner.join_exam_lines — maybe the section title line gets joined with question text. Let me view cleaner.

</details>

**Qoder：** 看 cleaner 的 join_exam_lines 和 coverage 的试卷题目匹配逻辑。

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cleaner.py`

<details><summary>结果</summary>

```
1	"""Unicode text cleaning for Chinese PDF extraction."""
2	from __future__ import annotations
3	
4	import re
5	import unicodedata
6	
7	
8	# Kangxi radicals and CJK Radicals Supplement: map each char to its
9	# standard CJK unified ideograph. Avoid full-text NFKC, which would also
10	# convert full-width punctuation to half-width.
11	_RADICAL_RE = re.compile(r"[\u2e80-\u2eff\u2f00-\u2fdf]")
12	
13	# CJK Radicals Supplement chars with no NFKC decomposition, mapped via the
14	# "x" equivalences in the Unicode UCD NamesList.txt.
15	_RADICAL_MAP = {
16	    0x2E81: 0x20086, 0x2E82: 0x4E5B, 0x2E83: 0x4E5A, 0x2E84: 0x4E59,
17	    0x2E85: 0x4EBB, 0x2E86: 0x5182, 0x2E87: 0x20628, 0x2E88: 0x2008A,
18	    0x2E89: 0x5202, 0x2E8A: 0x535C, 0x2E8B: 0x353E, 0x2E8C: 0x5C0F,
19	    0x2E8D: 0x2D544, 0x2E8E: 0x5140, 0x2E8F: 0x5C23, 0x2E90: 0x5C22,
20	    0x2E91: 0x21BC2, 0x2E92: 0x5DF3, 0x2E93: 0x5E7A, 0x2E94: 0x5F51,
21	    0x2E95: 0x2B739, 0x2E96: 0x5FC4, 0x2E97: 0x5FC3, 0x2E98: 0x624C,
22	    0x2E99: 0x6535, 0x2E9B: 0x65E1, 0x2E9C: 0x65E5, 0x2E9D: 0x6708,
23	    0x2E9E: 0x6B7A, 0x2EA0: 0x6C11, 0x2EA1: 0x6C35, 0x2EA2: 0x6C3A,
24	    0x2EA3: 0x706C, 0x2EA4: 0x722B, 0x2EA5: 0x722B, 0x2EA6: 0x4E2C,
25	    0x2EA7: 0x20092, 0x2EA8: 0x72AD, 0x2EA9: 0x248E9, 0x2EAA: 0x24D14,
26	    0x2EAB: 0x7F52, 0x2EAC: 0x793A, 0x2EAD: 0x793B, 0x2EAE: 0x25AD7,
27	    0x2EAF: 0x7CF9, 0x2EB0: 0x7E9F, 0x2EB1: 0x7F53, 0x2EB2: 0x26270,
28	    0x2EB3: 0x7F51, 0x2EB4: 0x7F51, 0x2EB5: 0x2626B, 0x2EB6: 0x7F8A,
29	    0x2EB7: 0x2634C, 0x2EB8: 0x2634B, 0x2EB9: 0x8002, 0x2EBA: 0x8080,
30	    0x2EBB: 0x807F, 0x2EBC: 0x8089, 0x2EBD: 0x26951, 0x2EBE: 0x8279,
31	    0x2EBF: 0x8279, 0x2EC0: 0x8279, 0x2EC1: 0x864E, 0x2EC2: 0x8864,
32	    0x2EC3: 0x8980, 0x2EC4: 0x897F, 0x2EC5: 0x89C1, 0x2EC6: 0x89D2,
33	    0x2EC7: 0x278B2, 0x2EC8: 0x8BA0, 0x2EC9: 0x8D1D, 0x2ECA: 0x27FB7,
34	    0x2ECB: 0x8F66, 0x2ECC: 0x8FB6, 0x2ECD: 0x8FB6, 0x2ECE: 0x8FB6,
35	    0x2ECF: 0x9091, 0x2ED0: 0x9485, 0x2ED1: 0x9577, 0x2ED2: 0x9578,
36	    0x2ED3: 0x957F, 0x2ED4: 0x95E8, 0x2ED5: 0x28E0F, 0x2ED6: 0x961D,
37	    0x2ED7: 0x96E8, 0x2ED8: 0x9752, 0x2ED9: 0x97E6, 0x2EDA: 0x9875,
38	    0x2EDB: 0x98CE, 0x2EDC: 0x98DE, 0x2EDD: 0x98DF, 0x2EDE: 0x2967F,
39	    0x2EDF: 0x98E0, 0x2EE0: 0x9963, 0x2EE1: 0x29810, 0x2EE2: 0x9A6C,
40	    0x2EE3: 0x9AA8, 0x2EE4: 0x9B3C, 0x2EE5: 0x9C7C, 0x2EE6: 0x9E1F,
… （共 236 行，此处省略 196 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now let me look at learning_store.py (session questions), memory.html (table), and the tests for quizgen. Also check how the exam question #5 is in coverage exam_questions. Also check samples of the exam PDF. Let me read learning_store.

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py`

<details><summary>结果</summary>

```
1	"""学习会话与出题记录的存储（新表，M3 专用）。
2	
3	learning_sessions / quiz_questions 建表和读写都放在本模块，
4	不改动 seekdb.py 里已有的表定义。
5	
6	隐私：本表只存学习者名字的短哈希（learner_hash）和 PowerContext scope_id
7	（scp_… 随机 id），不存明文名字——名字只出现在本机 PowerContext 的 Scope 里。
8	
9	时长口径：30 分钟（config.session_idle_minutes）没有任何事件视为已结束，
10	时长按最后一个事件的时间计（ended_at / duration = last_event_at - started_at）。
11	"""
12	from __future__ import annotations
13	
14	import json
15	from datetime import datetime, timedelta, timezone
16	from typing import Optional
17	
18	from .config import get_settings
19	from .seekdb import get_connection
20	
21	
22	def _utc_now() -> datetime:
23	    return datetime.now(timezone.utc).replace(tzinfo=None)
24	
25	
26	def ensure_learning_tables() -> None:
27	    """幂等建表。由 main.py 的 lifespan 调用。"""
28	    conn = get_connection()
29	    try:
30	        with conn.cursor() as cur:
31	            cur.execute("""
32	                CREATE TABLE IF NOT EXISTS learning_sessions (
33	                    session_id    VARCHAR(64) PRIMARY KEY,
34	                    scope_id      VARCHAR(128),
35	                    learner_hash  CHAR(8) NOT NULL,
36	                    course_id     VARCHAR(64) NOT NULL,
37	                    started_at    DATETIME NOT NULL,
38	                    last_event_at DATETIME NOT NULL,
39	                    ended_at      DATETIME,
40	                    INDEX idx_learner_course (learner_hash, course_id)
… （共 239 行，此处省略 199 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now, I need to plan the redesign of topic selection for quiz/next.

Current: `select_topic(mastery, cov, last_topic_id)` — only avoids last topic. Problem: alternates between t04 and t08 because pool sorted by blind spot desc, skipping only last topic.

New requirements:
1. Same topic can't appear again until at least 2 other questions intervene (gap ≥ 2 questions).
2. Plan topics rotate once through all before returning to wrong ones. I.e., "计划里的知识点先轮一遍，再回到答错的" — the plan (review plan / coverage pool) topics should be cycled through fully before repeating any. So essentially: maintain a rotation. Use session history: recently asked topic_ids (last 2 questions at least). Prefer topics in pool order that haven't been asked yet in this session; then wrong-answered ones can come back after the gap.

Interpretation: selection should pick from pool (due > weak > rest) but:
- exclude topics asked in the last 2 questions (min gap of 2 other questions);
- prefer topics not yet asked this session ("先轮一遍") — but that's essentially the same exclusion until all pool topics are used;
- after all pool topics asked once, allow repeats (back to wrong ones) subject to gap ≥ 2.

Implementation: quiz_next needs session question history, not just last question. Add a learning_store function `session_topic_history(session_id)` returning list of topic_ids in order asked (or reuse session_question_stats — but need order and includes unanswered). Add function `recent_topic_ids(session_id, limit)` or full list.

Then selection logic in select_topic: signature change to accept `recent_topic_ids: list[str]` (topics of questions in this session, in order, maybe last N). Let's design:

```python
def select_topic(mastery, cov, recent_topic_ids):  # recent in order, oldest→newest
    today = ...
    # due first (but skip if in last 2)
    ...
```

Careful: due topics should still take priority but respect gap. If all due topics are in the last-2 window, fall through to coverage pool? Or pick the oldest due? Requirement focuses on coverage plan rotation. For due, keep priority but exclude last-2 window; if empty fall through.

Coverage pool: weak (thin/missing) sorted by blind desc, else all items. Among pool, first pass: topics not yet asked this session (asked = set of recent_topic_ids... actually all topics asked this session). Pick the first in pool order that isn't in the last-2 window and... "计划里的知识点先轮一遍" — prefer not-yet-asked; if all pool topics have been asked, then allow those asked (wrong ones first? "再回到答错的"). After first rotation, prioritize wrong-answered topics (they need re-drilling), subject to gap.

Hmm, but "再回到答错的" — after all plan topics rotated once, return to the ones answered wrong. So second pass: wrong-answered topics in this session (by wrong count desc? or pool order), excluding last-2 window. Then third: anything.

But wait — there's a subtlety: the "pool" for first pass should include all coverage items or just weak? "复习计划里的 t02、t01、t05 一直没轮到" — review plan mentions topics; the plan pool is coverage items (all, sorted by blind score). First rotation should go through the full pool in blind-score order presumably. Current behavior: pool = weak or items (if no weak, all items). In the dev scenario: weak = [t04 missing, t08 thin, maybe t02 thin...]. Actually plan mentions t02, t01, t05 — the review plan's blind/missing list? The user says "复习计划里的 t02、t01、t05 一直没轮到" — meaning the coach's plan (weak pool) includes those. So first rotation: iterate pool in order, asking each once; skip those within last-2.

Simplest robust design in quiz_next:
- Get session question history: list of (topic_id, correct) in order.
- `recent2` = topic_ids of last 2 questions.
- `asked` = set of topic_ids asked this session (answered or not? include unanswered current pending question — the last question is pending until answered; frontend answers then requests next. Use all questions created).
- `wronged` = ordered set of topic_ids answered wrong this session.

select_topic(mastery, cov, recent_topic_ids, wrong_topic_ids):

```
due = [...sorted by next_review]
for d in due: if d not in recent_last2: return
items pool...
# pass 1: not yet asked this session
for it in pool: if it.topic_id not in asked_set and not in last2: return
# pass 2: asked and wrong
for it in pool (or wronged order): if it.topic_id in wronged and not in last2: return
# pass 3: any pool item not in last2
for it in pool: if not in last2: return
# pass 4: pool[0]
```

Hmm pass 2 vs "再回到答错的" ordering: after first rotation, prefer wrong ones. Use pool order among wronged (pool is blind-score sorted which includes exam weight — reasonable). Actually maybe wrong count desc. Keep pool order — simpler and deterministic.

But wait: should pass 1 consider ALL coverage items or just the "pool" (weak or all)? If weak exists, pool = weak only, and other topics never asked. In dev scenario weak includes t04, t08, t02?, t01?, t05? — user says plan has t02/t01/t05 waiting. Let me check dev DB coverage levels. The review plan's blind_missing lists only missing ones. But the user's phrasing "复习计划里的" loosely means the coach's rotation. I'll keep pool = weak or all items as before.

Also `select_topic` signature used elsewhere? Check callers: routes/quiz.py and tests (test_quizgen). Also routes/sessions.py maybe uses select_topic for plan display. Let me grep.

Requirement 1c: self-test questions rotate among the multiple original exam questions of the same topic (t04 has 第4题 and 第5题). `make_self_test_question` picks the first exam question. Fix: pass recent question chunk ids / question_nos used in this session for this topic, pick the next one. Implementation: `make_self_test_question(topic, course_id, used_question_nos: set[int])` — iterate exam_questions, pick first whose question_no not in used; if all used, pick... rotate: pick first (or alternate). "轮换" — rotate. If all used, pick the least recently used? Simple: pick first not used; else pick the one used longest ago? Simplest: pick first not in used, else the second one / cycle by count. E.g. `used_list` for topic; index = len(used_list) % len(available). Deterministic rotation.

In quiz_next, gather used self-test question_nos for this topic from session questions: query learning_store for questions of session with topic_id, extract payload chunk_id or source.question_no. Add learning_store function `session_questions(session_id, topic_id=None)`.

Also the same repetition issue applies to fill questions (t08 same blank repeated). The requirement says at least 2-question gap for the same knowledge point generally. For question-level repetition, existing last_sig check only avoids the immediately previous identical question. With topic-gap ≥ 2, the same fill question can recur at position +3. Requirement 1 only says: same topic ≥2 gap, plan topics rotate first, self-test rotate among multiple originals. It doesn't demand fill questions rotate among different chunks, but "t08 填空（同一个空）" was part of the symptom. With 2-question gap and rotation-first, t08 would recur with the same blank at position 3+... Actually sequence with 6 weak topics: t04, t08, t02, t01, t05, ... then back to wrong. The user's acceptance test: 6 questions all wrong — they expect rotation through plan topics. Fine. But maybe also make fill questions avoid repeating the exact same chunk/term within a session when alternatives exist. I could extend: `_rule_fill` currently checks last_sig only. Extend to check signatures of recent questions for this topic. Let me keep it modest but improve: pass `used_sigs` (signatures of all questions for this topic in session) to _rule_fill; prefer a question whose sig isn't used; fall back.

Hmm — requirement text for tests: "出题顺序：同一会话里同一个知识点不连续出现，计划里的知识点先轮一遍" — wait, "同一个知识点不连续出现"?? The new test says "不连续" (not consecutive)? But requirement 1 says at least 2 questions gap. The acceptance test says "同一会话里同一个知识点不连续出现" — hmm, that's weaker. But requirement body says "刚答过的知识点，至少隔 2 道别的题再出". I'll implement gap ≥ 2 (which implies non-consecutive).

Requirement 2: source label. Exam chunk: document_name · 第1页 · heading(第4题) · 第4题（15.0分）. Fix: when heading is "第N题" and question_no == N, don't append question_no part again — but we still want points displayed as "15 分". Expected output: "2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15 分"? The user says 去掉重复，分值写成"15 分"。 So final: `…试卷A.pdf · 第1页 · 第4题（15 分）`? Or "第4题 · 15 分"? "去掉重复，分值写成'15 分'" — the duplicate is "第4题" appearing twice; the points "15.0分" → "15 分". So label becomes "2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15 分"? Hmm, original: "第1页 · 第4题 · 第4题（15.0分）". If we remove the duplicate question_no and reformat points: "第1页 · 第4题（15 分）" seems most natural — heading "第4题", then question part becomes just "（15 分）"? Or "第4题 · 15 分". I'll go: if heading already equals f"第{question_no}题", append only f"{points:g} 分" (no repeat of 第N题). Result: "…第1页 · 第4题 · 15 分". And points formatting: use `f"{points:g} 分"` so 15.0 → "15", 2.5 → "2.5". When heading doesn't match, keep "第N题（15 分）".

Requirement 3: build_opening_line merge duplicates: same topic in wrong_recent and blind_missing → one sentence: e.g. "上次你在『函数依赖与范式（3NF、BCNF）』上错了 2 次且往年考 25 分但笔记里没有，先复习它"? Need a combined sentence. Design: track mentioned topic ids. For the first wrong topic, if it's also in blind_missing, combine: f"上次你在『{name}』上错了 {count} 次，它往年考 {w} 分但笔记里没有，先复习它". For others in wrong_recent also in blind list, combine similarly. And blind_missing topics already mentioned are skipped. Also due_today could duplicate — merge too ("『X』今天到期" + wrong?). Keep it manageable: build per-topic info map, output each topic at most once.

New format proposal:
- For each topic in order (wrong first, then due, then blind), one clause; topic mentioned once.
- Combined clause for wrong+blind: "上次你在『X』上错了 N 次，先复习它（往年考 25 分但笔记里没有）" — hmm parentheses fine. Simpler: "『X』往年考 25 分但笔记里没有，上次错了 2 次，先复习它".

Let me write:

```python
def build_opening_line(wrong_recent, due_today, blind_missing):
    wrong_map = {tid: (name, count) for tid, name, count in wrong_recent[:3]}
    due_map = {tid: name for tid, name in due_today[:3]}
    blind_map = {tid: (name, weight) for tid, name, weight in blind_missing[:2]}
    parts = []
    mentioned = set()
    # wrong first (priority)
    for tid, name, count in wrong_recent[:3]:
        clauses = []
        if not parts:
            clauses.append(f"上次你在『{name}』上错了 {count} 次，先复习它")
        else:
            clauses.append(f"『{name}』错了 {count} 次")
        if tid in blind_map:
            w = blind_map[tid][1]
            clauses.append(f"往年考 {w:g} 分但笔记里没有")
        parts.append("，".join? ...
```

Hmm "上次你在『X』上错了 2 次，先复习它；往年考 25 分但笔记里没有" reads oddly. Better: "上次你在『X』上错了 2 次，先复习它——往年考 25 分但笔记里没有". Let me pick: for the first (wrong) topic that's also blind: f"上次你在『{name}』上错了 {count} 次，先复习它；它往年考 {weight} 分但笔记里没有". Using "；它" keeps it as one part joined by "；"? But overall join is "；" too. Use "，" within: f"上次你在『{name}』上错了 {count} 次（往年考 {w:g} 分但笔记里没有），先复习它". That reads well: "上次你在『函数依赖与范式（3NF、BCNF）』上错了 2 次（往年考 25 分但笔记里没有），先复习它".

For non-first wrong also blind: f"『{name}』错了 {count} 次（往年考 {w:g} 分但笔记里没有）".

Then due_today: skip if mentioned; clause "『X』今天到期" — if also blind: "『X』今天到期（往年考 25 分但笔记里没有）".

Then blind_missing: skip if mentioned; clause "『X』往年考 {w:g} 分但笔记里没有".

Join with "；". Each topic appears once. 

Requirement 4: memory.html table — find the mastery card table, add nowrap to 盒号/对/错 headers and 下次复习 date cells. Let me look at memory.html.

Requirement 5: chunk_exam_pdf strip trailing section header lines. Pattern from cleaner `_EXAM_SECTION_START_RE` = ^[一二三四五六七八九十]+\s*[、.．]. Requirement: lines starting with "一、"…"十、" and containing "共 N 分". I'll define in chunker:

```python
_EXAM_SECTION_TITLE_RE = re.compile(r"^[一二三四五六七八九十]+\s*[、.．].*共\s*\d+(?:\.\d+)?\s*分")
```

and strip matching lines from the end of each question content (while loop on last lines). Also maybe strip such lines anywhere? Trailing only is what's required. But what about the LAST question of the paper — content ends with end of text, no section title. Fine.

Wait — also should the section title go into a `section` field? Not required. Just remove.

Now check coverage.py to see exam_questions content source and the re-import flow (documents delete API). Let me read coverage.py and routes/documents.py quickly.

</details>

**Qoder：** 看 coverage.py 的试卷题目归属、routes/documents.py（重导入口）、memory.html 的表格。

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coverage.py`

<details><summary>结果</summary>

```
1	"""Coverage analysis: per-topic key-term evidence, exam weight, blind spots.
2	
3	Judgment is based on whether a topic's key terms (考点词) actually appear in
4	the course materials (notes / slides / paper). Semantic scores from
5	DBMS_HYBRID_SEARCH rank and annotate the evidence but never decide coverage:
6	with bge-small-zh-v1.5, cosine similarity for unrelated short Chinese terms
7	stays above ~0.7, so it cannot separate "covered" from "missing" (measured
8	in DEVLOG sessions 04/05).
9	"""
10	from __future__ import annotations
11	
12	import json
13	from dataclasses import dataclass, field
14	from datetime import datetime, timezone
15	from typing import Optional
16	
17	from .config import get_settings
18	from .seekdb import (
19	    hybrid_search, get_connection, save_coverage_run,
20	    get_latest_coverage, insert_usage_event, get_coverage_chunks,
21	    get_exam_chunks,
22	)
23	from .embedding import get_embedding_model
24	from .syllabus import Topic, Term, normalize_for_match, tokenize_term, parse_syllabus
25	
26	COVERAGE_DOC_KINDS = ["notes", "slides", "paper"]
27	
28	
29	@dataclass
30	class ChunkInfo:
31	    """One candidate chunk from the course materials."""
32	    chunk_id: int
33	    content: str
34	    heading: Optional[str]
35	    page: Optional[int]
36	    document_name: Optional[str]
37	    body_chars: int = 0
38	    norm_text: str = ""
39	    matched_terms: list[str] = field(default_factory=list)
40	    sem_score: Optional[float] = None
… （共 636 行，此处省略 596 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now memory.html table and routes/documents.py delete endpoint.

</details>

🔧 **Bash** ```bash
grep -n "盒号\|下次复习\|对/错\|nowrap\|white-space" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/static/memory.html
```

<details><summary>结果</summary>

```
98:    html += '<table><tr><th>知识点</th><th>盒号</th><th>对/错</th><th>下次复习</th><th>artifact</th><th>轨迹</th></tr>' +
113:      '<pre style="white-space:pre-wrap">' + escapeHtml(m.text) + '</pre></div>').join('');
121:      '<pre style="white-space:pre-wrap">' + escapeHtml(m.text) + '</pre></div>').join('');
```

</details>

🔧 **Bash** ```bash
grep -n "delete\|DELETE" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/documents.py
```

<details><summary>结果</summary>

```
No matches found
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/static/memory.html`

<details><summary>结果</summary>

```
1	<!DOCTYPE html>
2	<html lang="zh-CN">
3	<head>
4	<meta charset="utf-8">
5	<meta name="viewport" content="width=device-width, initial-scale=1">
6	<link rel="icon" href="data:,">
7	<title>我的记忆 — 考前雷达</title>
8	<link rel="stylesheet" href="/static/css/style.css">
9	<script src="/static/js/source.js"></script>
10	</head>
11	<body>
12	<header>
13	<div class="container">
14	<h1>考前雷达</h1>
15	<nav>
16	<a href="/">首页</a>
17	<a href="/import.html">导入资料</a>
18	<a href="/ask.html">问笔记</a>
19	<a href="/radar.html">覆盖雷达</a>
20	<a href="/coach.html">复习教练</a>
21	<a href="/memory.html">我的记忆</a>
22	<a href="/usage.html">使用记录</a>
23	</nav>
24	</div>
25	</header>
26	<div class="container">
27	<div class="card">
28	<h2>我的记忆</h2>
29	<div class="form-row">
30	<div>
31	<label for="learner-input">你的名字</label>
32	<input type="text" id="learner-input" placeholder="例如：验收同学">
33	</div>
34	<div>
35	<label for="course-id">课程 ID</label>
36	<input type="text" id="course-id" value="db101">
37	</div>
38	</div>
39	<button class="btn" style="margin-top:12px" onclick="loadMemory()">查看记忆</button>
40	<div id="memory-notice" class="status err" style="display:none;margin-top:12px">记忆服务暂不可用</div>
… （共 154 行，此处省略 114 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Fix table columns: add `white-space:nowrap` to 盒号, 对/错 headers and cells and 下次复习 date cells. I'll add style to those `<th>` and `<td>`s: `<th style="white-space:nowrap">盒号</th><th style="white-space:nowrap">对/错</th><th style="white-space:nowrap">下次复习</th>` and corresponding `<td style="white-space:nowrap">`. The date `next_review` like "2026-10-30" — wrap due to column width. Add nowrap to those cells.

Now, check documents.py for delete/reimport endpoints and how to re-import the exam PDF on dev DB. Also check .env and samples. And tests test_quizgen.py for existing select_topic tests.

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/documents.py`

<details><summary>结果</summary>

```
1	"""Document import endpoint."""
2	from __future__ import annotations
3	
4	from typing import Optional
5	
6	from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
7	
8	from ..ingest import ingest_bytes, ValidationError
9	from ..seekdb import get_documents
10	
11	router = APIRouter()
12	
13	
14	@router.post("/api/documents")
15	def upload_document(
16	    file: UploadFile = File(...),
17	    course_id: str = Form(...),
18	    doc_kind: str = Form(...),
19	    x_examradar_source: Optional[str] = Header(None),
20	):
21	    # Sync def: chunking + embedding run in the threadpool, so the event
22	    # loop (and every other request) is not blocked during import.
23	    source = "auto" if x_examradar_source == "auto" else "real"
24	    content = file.file.read()
25	
26	    try:
27	        return ingest_bytes(content, file.filename or "unknown", course_id,
28	                            doc_kind, source)
29	    except ValidationError as e:
30	        raise HTTPException(status_code=400, detail=str(e))
31	
32	
33	@router.get("/api/documents")
34	def list_documents(course_id: str):
35	    return get_documents(course_id)
36
```

</details>

<details><summary>Qoder 思考</summary>

No delete API. Need to delete the exam doc from dev DB directly via SQL (seekdb). Check ingest.py for how documents are stored, and check test_ingest or CLI for a delete path. Maybe there's a CLI. Let me check cli.py and seekdb for delete functions. Also check test_quizgen.py to understand select_topic test conventions.

</details>

🔧 **Bash** ```bash
grep -n "def \|DELETE\|delete" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py
```

<details><summary>结果</summary>

```
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:7:from .seekdb import ensure_tables, delete_course, get_connection
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:20:def _detect_kind(filepath: Path) -> str:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:28:def import_path(path: str, course: str, kind: str | None = None,
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:67:def _format_cell(value) -> str:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:73:def run_sql(sql: str):
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:101:    def fmt_row(cells: list[str]) -> str:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:111:def main():
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:127:    dc = sub.add_parser("delete-course", help="Delete a course's materials and coverage analyses (usage_events are kept)")
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:130:                    help="Also delete this course's usage_events (the usage log)")
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:137:    elif args.command == "delete-course":
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/cli.py:138:        counts = delete_course(args.course, include_usage=args.include_usage)
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:14:def _utc_now() -> datetime:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:18:def get_connection(database: Optional[str] = None):
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:32:def ensure_database():
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:54:def ensure_tables():
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:154:def _ensure_columns(conn, table: str, columns: dict[str, str]):
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:169:def import_document(
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:214:def find_document_by_sha256(sha256: str, course_id: str) -> Optional[dict]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:227:def delete_course(course_id: str, include_usage: bool = False) -> dict:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:231:    include_usage=True to delete them as well.
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:241:                cur.execute(f"DELETE FROM {table} WHERE course_id = %s", (course_id,))
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:248:def get_coverage_chunks(course_id: str, doc_kinds: list[str]) -> list[dict]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:266:def get_exam_chunks(course_id: str) -> list[dict]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:282:def insert_usage_event(course_id: str, source: str, event: str, payload: dict,
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:298:def _escape_search_text(text: str) -> str:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:314:def build_search_json(
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:357:def hybrid_search(
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:396:def _break_rrf_ties(hits: list[dict]) -> list[dict]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:402:    def key(h: dict):
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:413:def get_document_names(course_id: str) -> dict[int, str]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:423:def get_documents(course_id: str) -> list[dict]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:444:def check_connection() -> bool:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:455:def save_coverage_run(
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:501:def get_latest_coverage(course_id: str) -> Optional[dict]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:536:def get_usage_events(
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:557:def get_usage_stats(course_id: str, source: str = "real",
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:575:def get_learning_session_rows(course_id: str) -> list[dict]:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py:591:def compute_usage_stats(events: list[dict], tz: ZoneInfo, settings,
```

</details>

<details><summary>Qoder 思考</summary>

Re-import on dev DB: "先删除再导入这份试卷". I can delete only the exam document rows (documents + chunks) via SQL through the app's CLI `run-sql`? The CLI has `run_sql` command. Let me check the CLI run-sql usage and .env config. Deleting only the exam doc: `DELETE FROM chunks WHERE document_id=...; DELETE FROM documents WHERE id=...`. That's a dev DB, acceptable (the task explicitly instructs to delete and re-import). I'll do it via a small Python script using examradar.seekdb.get_connection (run with uv from app dir).

Now look at test_quizgen.py to see existing tests of select_topic/make_self_test_question, and conftest for fixtures.

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py`

<details><summary>结果</summary>

```
1	"""出题与判分的单元测试（不依赖 seekdb / PowerContext / LLM 网络）。"""
2	from datetime import date
3	
4	import pytest
5	
6	import examradar.coach as coach
7	from examradar.llm import LLMError
8	from examradar.mastery import MasteryState
9	
10	
11	def make_chunk(content, heading=None, doc="05-事务与并发控制.md", page=None,
12	               chunk_id=101):
13	    return {"id": chunk_id, "content": content, "heading": heading,
14	            "page": page, "document_name": doc, "question_no": None,
15	            "points": None}
16	
17	
18	class TestFillQuestion:
19	    def test_blank_keyword_from_topic_keywords(self):
20	        topic = {"topic_id": "t08", "topic_name": "隔离级别与 MVCC",
21	                 "keywords": ["MVCC"]}
22	        chunk = make_chunk(
23	            "多版本并发控制（MVCC）让读操作不加锁。快照读基于一致性视图实现。",
24	            heading="5.2 隔离级别")
25	        q = coach.make_fill_question(topic, chunk)
26	        assert q is not None
27	        assert q["question_type"] == "fill"
28	        assert q["expected_answer"] == "MVCC"
29	        assert "＿＿＿" in q["question"]
30	        # 标明出处：文件 · 页/标题
31	        assert q["source"]["document_name"] == "05-事务与并发控制.md"
32	        assert "5.2 隔离级别" in q["source"]["label"]
33	        assert q["chunk_id"] == 101
34	
35	    def test_falls_back_to_latin_terms(self):
36	        topic = {"topic_id": "t09", "topic_name": "故障恢复：WAL 与 ARIES",
37	                 "keywords": []}
38	        chunk = make_chunk("先写日志原则要求日志先于数据落盘。")
39	        q = coach.make_fill_question(topic, chunk)
40	        assert q is None or q["expected_answer"]
… （共 327 行，此处省略 287 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now let's check routes/sessions.py to see where select_topic is used for the plan, and coach.html briefly. Also test_mastery.py for build_opening_line tests.

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/sessions.py`

<details><summary>结果</summary>

```
1	"""学习会话路由：start（bootstrap）/ end（会话小结 + 复习计划）。"""
2	from __future__ import annotations
3	
4	import json
5	import uuid
6	from typing import Optional
7	
8	from fastapi import APIRouter, Header, Request
9	from fastapi.responses import JSONResponse
10	from pydantic import BaseModel
11	
12	from ..config import get_settings
13	from ..mastery import learner_hash, format_session_summary
14	from ..pc_client import (
15	    PowerContextClient, PowerContextUnavailable, bootstrap_opening_line,
16	)
17	from ..seekdb import insert_usage_event
18	from .. import learning_store
19	from ..coach import (
20	    MEMORY_NOTICE, build_review_plan_inputs, coverage_snapshot, due_topics,
21	    load_mastery_states, review_plan_opening, update_review_plan,
22	)
23	
24	router = APIRouter()
25	
26	
27	class SessionStartRequest(BaseModel):
28	    learner: str
29	    course_id: str
30	
31	
32	@router.get("/api/coach/status")
33	def coach_status():
34	    from ..llm import get_llm_client
35	    s = get_settings()
36	    llm = get_llm_client()
37	    pc = PowerContextClient()
38	    pc_ok, pc_detail = pc.health()
39	    return {
40	        "llm": {
… （共 210 行，此处省略 170 行，完整内容见 .jsonl）
```

</details>

🔧 **Bash** ```bash
grep -n "build_opening_line\|select_topic\|make_self_test_question" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/*.py /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/scripts/e2e_verify.py
```

<details><summary>结果</summary>

```
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_mastery.py:7:    MasteryState, ReviewPlanData, build_opening_line, build_review_plan,
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_mastery.py:97:        line = build_opening_line(
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_mastery.py:106:        assert "复习" in build_opening_line([], [], [])
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py:148:        q = coach.make_self_test_question(topic, "db101")
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py:161:        assert coach.make_self_test_question(topic, "db101") is None
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py:278:        topic = coach.select_topic(mastery, cov, last_topic_id=None)
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py:292:        topic = coach.select_topic({}, cov, last_topic_id=None)
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py:296:        assert coach.select_topic({}, None, None) is None
```

</details>

<details><summary>Qoder 思考</summary>

Also need to check e2e_verify.py's coach step — it might depend on the old question order (e.g. expects Q1 t04 self-test, Q2 t08 fill). Requirement says "如果复习教练一步依赖旧的出题顺序，一起改。" Let me view the coach step in e2e_verify.py.

</details>

🔧 **Bash** ```bash
grep -n "step_coach\|def step\|STEPS" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/scripts/e2e_verify.py
```

<details><summary>结果</summary>

```
296:def step_health(ctx: Ctx) -> StepResult:
346:def step_import(ctx: Ctx) -> StepResult:
451:def step_search(ctx: Ctx) -> StepResult:
655:def step_coverage(ctx: Ctx) -> StepResult:
755:def step_coach(ctx: Ctx) -> StepResult:
1006:STEPS: list[tuple[str, Callable[[Ctx], StepResult]]] = [
1011:    ("复习教练", step_coach),
1073:    for name, func in STEPS:
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/scripts/e2e_verify.py`

<details><summary>结果</summary>

```
755	def step_coach(ctx: Ctx) -> StepResult:
756	    res = StepResult("复习教练")
757	    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
758	    learner = f"e2e教练{ts}"
759	
760	    status = ctx.app.get("/api/coach/status")
761	    pc_ok = bool((status.get("powercontext") or {}).get("ok"))
762	    res.checks.append(Check(
763	        "/api/coach/status：PowerContext 可用", pc_ok,
764	        f"llm configured={bool((status.get('llm') or {}).get('configured'))}"
765	        f"（CI 栈不配大模型，走无模型路径）",
766	    ))
767	
768	    # ---- 会话 1：新学习者，bootstrap 必须为空 ----
769	    s1 = ctx.app.post_json("/api/sessions/start",
770	                           {"learner": learner, "course_id": COURSE_ID})
771	    scope_id = s1.get("scope_id") or ""
772	    res.checks.append(Check(
773	        "新学习者开始会话：scope 已建、bootstrap 为空",
774	        bool(scope_id)
775	        and (s1.get("bootstrap") is None or not (s1.get("bootstrap") or {}).get("items"))
776	        and s1.get("opening_line") is None,
777	        f"scope_id={scope_id[:12]}…，bootstrap items="
778	        f"{(s1.get('bootstrap') or {}).get('items') or []}",
779	    ))
780	    sid1 = s1.get("session_id") or ""
781	
782	    # ---- 第 1 题：自动选题应为盲区第一 t04（missing → 往年原题自测）----
783	    q1 = ctx.app.post_json("/api/quiz/next", {"session_id": sid1})
784	    res.checks.append(Check(
785	        "第 1 题自动选题 = 盲区第一 t04，missing 走往年原题自测",
786	        q1.get("topic_id") == BLIND_SPOT_TOP_TOPIC
787	        and q1.get("question_type") == "self"
788	        and "笔记里没有" in (q1.get("hint") or "")
789	        and "期末试卷" in ((q1.get("source") or {}).get("label") or "")
790	        and q1.get("self_ratings") == SELF_RATINGS,
791	        f"topic={q1.get('topic_id')}，题型={q1.get('question_type')}，"
792	        f"出处={((q1.get('source') or {}).get('label') or '')[:60]}",
793	    ))
794	    q1_text = (q1.get("question") or "").strip()
… （共 260 行，此处省略 220 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

The e2e coach step:
- Q1: auto → t04 (blind first). OK with new logic (first question, nothing asked).
- Q2: explicit topic_id=t04 — explicit request bypasses gap? The user asks Q2 on the same topic deliberately (to test mistake recall). With req.topic_id explicit, we should still honor the explicit request (user chose it). Keep explicit path bypassing the gap rule.
- Q3: auto, question_type=fill. Old expectation: t08. New logic: last 2 questions are t04, t04 → t04 excluded; pool weak = [t04, t08, ...]; not-yet-asked first → t08 if t08 is next in pool order among unasked. Pool sorted by blind desc: t04 (25 missing?), t08 (8.41), t02 (7.92)... So first unasked = t08. Good, still t08. 

But wait — after Q1 t04 wrong and Q2 t04 correct, in a real session the "due" logic: t04 box 2, next_review = today+2, not due. OK.

Also e2e step: after Q3 wrong on t08... fine.

But wait — new logic Q3 with only-one-weak? In CI dev course, weak = missing/thin topics. t04 missing(25), t08 thin(8.41), t02 thin(7.92), t01?, t05? The user said t02/t01/t05 are in the plan. So Q3 = t08 works.

Now the new selection logic in detail. I'll change `select_topic` signature to take `recent` (list of topic_ids in order, most recent last) and `wrong` (list of topic_ids answered wrong this session, maybe with counts — order by first-wrong or count?). Since quiz_next already has DB access, compute there:

```python
history = learning_store.session_questions(req.session_id)  # ordered oldest→newest
recent_topic_ids = [h["topic_id"] for h in history]
wrong_counts = ordered dict of topic_id → wrong count (answered wrong)
```

Add learning_store function:

```python
def session_questions(session_id: str) -> list[dict]:
    SELECT id, topic_id, question_type, correct, payload FROM quiz_questions WHERE session_id=%s ORDER BY created_at ASC, id ASC
    (parse payload json)
```

Hmm, ORDER BY created_at ASC — created_at has second? DATETIME precision — questions created within same second order ambiguously. Add AUTO_INCREMENT? Table has id VARCHAR PK. Add an index column? Simpler: order by created_at, id — not reliable for ordering within a second. Could add `seq` BIGINT AUTO_INCREMENT column to quiz_questions. The table already exists in dev DB; adding a column via ALTER in ensure_learning_tables `_ensure_columns`-like approach. seekdb has `_ensure_columns` helper but learning_store builds its own tables. I can add a `_ensure_column` call in ensure_learning_tables: check information_schema and ALTER TABLE ADD COLUMN seq BIGINT AUTO_INCREMENT? OceanBase (MySQL-compatible) supports AUTO_INCREMENT columns but adding AUTO_INCREMENT column to existing table requires it be a key? In MySQL, an AUTO_INCREMENT column must be defined as a key. Adding `seq BIGINT AUTO_INCREMENT, ADD INDEX(idx_seq)` might work but for existing table ALTER adds values automatically.

Alternative: order by created_at ASC, id DESC reversed? ids are uuid hex — random, useless for ordering.

Alternative simpler: order by created_at and tie-break by...? Questions within one session are created sequentially; typical quiz flow has seconds between questions, but automated tests can create several within the same second. Ordering errors within same second only matter for adjacent topic gap logic — risky for e2e/browser tests running fast.

Better: track a monotonically increasing sequence per session. Simplest: add column `seq INT` not auto-increment, and set seq = (SELECT COALESCE(MAX(seq),0)+1 ...) at insert. Or use DATETIME(3)/timestamp with microseconds: change created_at to DATETIME(3)? `_utc_now` returns datetime with microseconds — DATETIME (without precision) truncates to second. ALTER to DATETIME(3) preserves microseconds; python datetime has microsecond precision. That's clean: ALTER TABLE quiz_questions MODIFY created_at DATETIME(3). And for new installs, define DATETIME(3). Existing rows truncate — fine, dev DB only has old sessions; our logic only applies to current session.

Hmm wait — but does OceanBase support DATETIME(3)? Yes, MySQL-compatible.

Actually simpler and robust: add `seq` column as BIGINT and compute per-insert with MAX(seq)+1 per session. That needs SELECT then INSERT (race conditions irrelevant — single app, single session usage). But also last_question_of_session orders by created_at DESC — same ambiguity, but it picks "the last" for sig-avoidance; not critical.

I'll go with DATETIME(3) approach: modify CREATE TABLE for new, and ALTER in ensure_learning_tables for existing. Use `SHOW COLUMNS` or information_schema? seekdb._ensure_columns exists — check its implementation and reuse pattern. Let me read seekdb lines 154-168.

Also `payload` needed to know used exam question_no for self-test rotation. session_questions returns payload parsed.

Now design select_topic:

```python
def select_topic(mastery, cov, recent_topic_ids=None, wrong_counts=None):
    """recent_topic_ids: 本会话已出题的知识点（旧→新）；wrong_counts: 本会话答错次数。"""
    recent = list(recent_topic_ids or [])
    last_two = set(recent[-2:])
    wrong_counts = wrong_counts or {}
    asked = set(recent)

    today = ...
    due = [tid for tid sorted by next_review if due]
    for tid in due:
        if tid not in last_two:
            return {..., source: "due"}

    items = cov items
    if items:
        weak = [...]
        pool = weak or items
        pool = sorted(blind desc)  # already sorted by latest, but re-sort safe
        # pass 1: 计划里的知识点先轮一遍
        for it in pool:
            if it["topic_id"] not in asked and it["topic_id"] not in last_two:
                return
        # pass 2: 都出过一遍后，先回到答错的
        for it in pool:
            if it["topic_id"] in wrong_counts and it["topic_id"] not in last_two:
                return
        # pass 3: 其余
        for it in pool:
            if it["topic_id"] not in last_two:
                return
        return dict(pool[0], source="coverage")

    # mastery 轮转（无覆盖数据）
    ...
```

Wait pass 2 ordering: wrong ones — order by pool (blind desc)? or by wrong count? "再回到答错的" — among pool order is fine; maybe order by wrong count desc then pool order. I'll order by (-wrong_count, pool index). 

Edge: pass 1 "topic not in asked" — but also not in last_two (can't be in last_two without being asked). So just `not in asked` suffices for pass 1... wait last_two ⊆ asked, so if not in asked then not in last_two. Yes pass 1 doesn't need last_two check.

Hmm, but there's a subtlety: pool is only weak topics (or all if no weak). "计划里的知识点先轮一遍" — the plan = the coach's rotation pool. If weak pool has only t04+t08 (like maybe in some course), then after both asked, pass 2 returns to wrong ones. But in the user's dev scenario weak pool includes t02, t01, t05 too. Good.

But wait — what if pool has fewer than 3 topics and all are in last_two? pass 3 fails → return pool[0] anyway (old behavior fallback). With pool of 2 topics [A,B]: sequence A,B,A?... last_two after A,B = {A,B}; pass1 none unasked; pass2: if A wrong → A not in last_two? A is in last_two. B in last_two. So pass 2 fails; pass 3 fails; fallback pool[0] = A. Sequence: A,B,A,B,... alternating — satisfies "not consecutive" only when pool ≥2... A,B,A has A at positions 1 and 3: gap of 1 question. Not satisfying gap≥2 but unavoidable with 2 topics. Fine.

For mastery-only fallback (no coverage): similar logic with tids. Keep simple: existing behavior but avoid last_two.

Also due priority: should due topics also respect "先轮一遍"? Due topics by definition are due for review today. Keep priority, exclude last_two.

Now, explicit topic request path (req.topic_id): keep as-is (user explicitly requests).

Self-test rotation: `make_self_test_question(topic, course_id, used_question_nos=())`:

```python
def make_self_test_question(topic, course_id, used_question_nos=None):
    used = list(used_question_nos or [])
    eqs = [eq for eq in topic.get("exam_questions") or [] if eq.get("question_no") is not None]
    if not eqs: return None
    # 优先没出过的原题；都出过则按出题次数轮换（出得最少的优先，次数相同按题号）
    pick = min(eqs, key=lambda eq: (used.count(eq["question_no"]), eq["question_no"]))
```

That rotates deterministically. If used empty → picks min by (0, qno) = lowest qno (第4题 first — matches current). Second time: used=[4] → 第5题 (count 0). Third: used=[4,5] → 第4题 (count 1 each, tie → lowest qno). Hmm rotation 4,5,4,5... fine.

In quiz_next, compute used self-test question numbers for this topic: from session questions with topic_id == topic, payload question_type == "self", source.question_no. Collect in order.

Also fill question repetition ("同一个空"): _rule_fill should avoid sigs already used this session for the topic, not just last question. Compute `used_sigs = [_question_signature(h["payload"]) for h in history if h["topic_id"] == topic_id]` and prefer new sigs. Modify _rule_fill to take used_sigs; loop chunks until sig not in used_sigs; fallback to first available.

Careful: make_fill_question always picks the first candidate term in first chunk that has one — deterministic. To vary, pass a skip set? The requirement only explicitly asks self-test rotation among 原题. For fill, "同一个空" repeats only when t08 comes back before other chunks... with rotation-first, t08 appears again at earliest at question 4+ (after t02, t01). Its fill would be identical (same chunk, same term) unless we avoid used sigs. Improving: in _rule_fill, iterate all (chunk, make_fill_question) and pick first with unused sig. But make_fill_question returns only the first term candidate per chunk. To get different terms from the same chunk we'd need to skip terms. Could pass `exclude_answers` to make_fill_question: skip candidates whose expected answer was already used. Let me extend make_fill_question(topic, chunk, used_answers=None): iterate candidates, skip if term in used_answers, else if sig... Actually simpler: in make_fill_question accept `used_terms: set[str]` — pick first candidate term not in used_terms; if all used, fall back to first. Then _rule_fill collects used expected answers for the topic this session, passes them. That gives different blanks on repeat. 

Now the routes/quiz.py changes:

```python
history = learning_store.session_questions(req.session_id)  # ordered
recent_topics = [h["topic_id"] for h in history]
wrong_counts = {}
for h in history:
    if h.get("correct") == 0 and h.get("answered_at"): wrong_counts[tid] += 1
```

Wait session_questions rows: correct is 1/0/None. Need answered_at not null and correct==0.

But careful: last question might be unanswered (created but not answered) — frontend flow: next → answer → next. But if user requests next without answering (not possible in UI; each next is preceded by answer). Include unanswered in recent (it was shown). Fine.

Then:
- topic = select_topic(mastery, cov, recent_topics, wrong_counts) for auto path.
- For explicit req.topic_id, no change.
- For self-test: used_nos = [payload.source.question_no for h in history if h.topic_id==topic.id and payload.question_type=="self" and payload.source.question_no]. 
- For _rule_fill: used_terms = {payload.expected_answer for h in history if h.topic_id==topic and question_type=="fill" and expected_answer}.

Signature change of select_topic breaks old tests test_quizgen TestSelectTopic using last_topic_id=None keyword. I'll update those tests to new signature. Also anything else calling select_topic? Only quiz route and tests.

Keep param name `last_topic_id` for backwards compat? No — change cleanly, update tests.

New signature: `select_topic(mastery, cov, recent_topic_ids=None, wrong_counts=None)`.

Test additions:
1. 出题顺序: 同一会话同一知识点不连续出现 & 计划知识点先轮一遍 — test select_topic with recent list: e.g. pool [t04, t08, t02, t01, t05]... simulate sequence: repeatedly call select_topic with growing recent list, assert each new topic differs from last two and that first 5 selections cover all pool topics (order = pool order when all wrong). Actually with all-wrong answers, sequence should be exactly pool order for first pass.
2. self-test rotation test: make_self_test_question with used [4] → returns 第5题.
3. opening line: same topic appears once.

Also test for source label dedupe (issue 2) — test _chunk_source or via make_self_test_question label: label "第4题" once and "15 分". Add assertion in TestSelfTestQuestion or new test.

And chunker test: exam chunk trailing section header removed. Add to test_chunker.py — check existing exam chunk tests.

Also check test_mastery.py opening line test to update.

</details>

**Qoder：** 看下 test_mastery.py 的开场白测试、test_chunker.py 的试卷切题测试，以及 seekdb 的 `_ensure_columns`。

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_mastery.py`

🔧 **Bash** ```bash
grep -n "exam\|section\|三、" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_chunker.py | head -30
```

<details><summary>结果</summary>

```
80	
81	
82	# ------------------------------------------------------------- review plan
83	
84	class TestReviewPlan:
85	    def test_roundtrip(self):
86	        text = build_review_plan(ReviewPlanData(
87	            opening="上次你在『隔离级别与 MVCC』上错了 2 次，先复习它",
88	            wrong_recent=["t08:2"], due_today=["t03"], blind_missing=["t04"],
89	            updated="2026-10-28T01:00:00Z"))
90	        plan = parse_review_plan(text)
91	        assert plan.opening == "上次你在『隔离级别与 MVCC』上错了 2 次，先复习它"
92	        assert plan.wrong_recent == ["t08:2"]
93	        assert plan.due_today == ["t03"]
94	        assert plan.blind_missing == ["t04"]
95	
96	    def test_opening_line_parts(self):
97	        line = build_opening_line(
98	            wrong_recent=[("t08", "隔离级别与 MVCC", 2)],
99	            due_today=[("t03", "索引：B+树与哈希索引")],
100	            blind_missing=[("t04", "函数依赖与范式（3NF、BCNF）", 25.0)])
101	        assert "上次你在『隔离级别与 MVCC』上错了 2 次，先复习它" in line
102	        assert "『索引：B+树与哈希索引』今天到期" in line
103	        assert "『函数依赖与范式（3NF、BCNF）』往年考 25 分但笔记里没有" in line
104	
105	    def test_opening_line_empty(self):
106	        assert "复习" in build_opening_line([], [], [])
107	
108	
109	# ---------------------------------------------------------------- session text
110	
111	class TestSessionSummary:
112	    def test_summary_contains_stats(self):
113	        text = format_session_summary(
114	            12.5, 6, 4, [("t08", "隔离级别与 MVCC", 2)],
115	            started_at="2026-10-28T01:00:00+00:00")
116	        assert "12 分钟" in text or "13 分钟" in text
117	        assert "做题 6 道" in text
118	        assert "正确率 67%" in text
119	        assert "隔离级别与 MVCC" in text
… （共 70 行，此处省略 30 行，完整内容见 .jsonl）
```

</details>

<details><summary>结果</summary>

```
2:from examradar.chunker import (
3:    chunk_markdown, chunk_text, chunk_exam_pdf, Chunk,
15:Content of section 1.1.
19:Content of section 1.2.
43:    def test_long_section_split(self):
93:三、查询处理与事务（共 50 分）
101:        chunks = chunk_exam_pdf("", [text])
116:        chunks = chunk_exam_pdf("", [text])
122:        from examradar.cleaner import join_exam_lines
124:        joined = join_exam_lines(text)
128:        from examradar.cleaner import join_exam_lines
130:        joined = join_exam_lines(text)
136:    def test_section_header_starts_new_block(self):
137:        from examradar.cleaner import join_exam_lines
139:        joined = join_exam_lines(text)
145:        from examradar.cleaner import join_exam_lines
147:        joined = join_exam_lines(text)
152:    def test_english_section_heading_stays_standalone(self):
153:        from examradar.cleaner import join_intra_paragraph_lines
163:        from examradar.cleaner import join_intra_paragraph_lines
169:        from examradar.cleaner import join_intra_paragraph_lines
175:        from examradar.cleaner import join_intra_paragraph_lines
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/seekdb.py`

<details><summary>结果</summary>

```
130	                    best_sem_score  DECIMAL(6,4),
131	                    best_kw_score   DECIMAL(10,4),
132	                    best_content    TEXT,
133	                    best_heading    TEXT,
134	                    best_page       INT,
135	                    best_doc_name   VARCHAR(256),
136	                    exam_weight     DECIMAL(6,1) DEFAULT 0,
137	                    exam_qs_json    TEXT,
138	                    blind_spot_score DECIMAL(10,4),
139	                    reason          TEXT,
140	                    INDEX idx_run (run_id),
141	                    INDEX idx_course_topic (course_id, topic_id)
142	                ) ORGANIZATION HEAP
143	            """)
144	            # existing installations: add columns introduced in session 05
145	            _ensure_columns(conn, "coverage_items", {
146	                "terms_json": "terms_json TEXT",
147	                "support_chunks": "support_chunks INT",
148	                "support_chars": "support_chars INT",
149	            })
150	    finally:
151	        conn.close()
152	
153	
154	def _ensure_columns(conn, table: str, columns: dict[str, str]):
155	    """Idempotently add missing columns (MySQL/seekdb has no ADD COLUMN IF
156	    NOT EXISTS)."""
157	    with conn.cursor() as cur:
158	        cur.execute(
159	            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
160	            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
161	            (table,),
162	        )
163	        existing = {r["COLUMN_NAME"] for r in cur.fetchall()}
164	        for col, ddl in columns.items():
165	            if col not in existing:
166	                cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
167	
168	
169	def import_document(
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_chunker.py`

<details><summary>结果</summary>

```
78	    def test_single_paragraph(self):
79	        chunks = chunk_text("Just one paragraph.")
80	        assert len(chunks) == 1
81	
82	
83	class TestChunkExamPdf:
84	    def test_question_splitting(self):
85	        text = """2025—2026 学年第一学期《数据库系统原理》期末考试试卷（A 卷）
86	一、关系模型与 SQL（共 25 分）
87	1.（5 分）设有关系学生S(Sno, Sname, Dept)。用关系代数表达式写出查询。
88	2.（10 分）用 SQL 写出查询平均成绩高于85分的学生学号。
89	3.（10 分）一棵阶数为4的B+树。
90	二、关系数据库设计（共 25 分）
91	4.（15 分）设关系模式R(A, B, C, D, E)，函数依赖集F。
92	5.（10 分）将上题的R分解为满足BCNF的关系模式集合。
93	三、查询处理与事务（共 50 分）
94	6.（5 分）查询优化中为什么要尽早执行选择操作？
95	7.（5 分）事务的ACID特性中，原子性和持久性分别由什么机制保证？
96	8.（10 分）什么是两阶段锁协议？
97	9.（10 分）比较读已提交和可重复读两种隔离级别。
98	10.（10 分）简述ARIES恢复算法的三个阶段。
99	11.（10 分）在分布式事务中，两阶段提交协议的两个阶段分别做什么？"""
100	
101	        chunks = chunk_exam_pdf("", [text])
102	        assert len(chunks) == 11, f"Expected 11 questions, got {len(chunks)}"
103	
104	        for c in chunks:
105	            assert c.question_no is not None
106	            assert c.points is not None
107	
108	        q4 = [c for c in chunks if c.question_no == 4][0]
109	        assert q4.points == 15.0
110	
111	        total_points = sum(c.points for c in chunks)
112	        assert total_points == 100.0, f"Expected 100 total points, got {total_points}"
113	
114	    def test_no_questions_fallback(self):
115	        text = "This is just a regular text without any question markers."
116	        chunks = chunk_exam_pdf("", [text])
117	        assert len(chunks) >= 1
… （共 75 行，此处省略 35 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now I have a full picture. Let me start implementing.

### Task 5 (chunker): strip trailing section-title lines from exam question chunks

In chunk_exam_pdf, after `content = full_text[start:end].strip()`, strip trailing lines matching section title pattern:

```python
_EXAM_SECTION_TITLE_RE = re.compile(
    r"^[一二三四五六七八九十]+\s*[、.．].*共\s*\d+(?:\.\d+)?\s*分")
```

Strip from end:
```python
lines = content.split("\n")
while lines and _EXAM_SECTION_TITLE_RE.match(lines[-1].strip()):
    lines.pop()
content = "\n".join(lines).strip()
```

Note: the question content in the user's scenario — question 5's chunk ends with "三、查询处理与事务（共 50 分）" — it's the last line. Also note question 1's chunk would end with "二、关系数据库设计（共 25 分）" etc. Wait — actually question 3 ends with "二、..." line. Since these are on their own lines (join_exam_lines keeps section headers standalone), stripping trailing lines works.

But wait — could the section header be the only content after stripping? No, each question chunk starts with the question header.

Edge: also strip section header lines that are NOT trailing? E.g., if the exam has a section header in the middle of a question's range (can't happen since next question starts a new match... actually section 三 header comes after question 5 and before question 6; question 5's range includes it at the end). Only trailing. But what if the last question (11) is followed by nothing? fine.

Also should we drop section titles that appear at the START of chunk 1's content? Chunk 1 starts at "1.（5 分）" so no. The title line "2025—2026 学年…试卷（A 卷）" and "一、关系模型与 SQL（共 25 分）" before question 1 are not in any chunk (chunk 1 starts at match of Q1). OK.

### Task 2 (_chunk_source)

```python
def _chunk_source(chunk):
    parts = []
    if chunk.get("document_name"):
        parts.append(chunk["document_name"])
    if chunk.get("page"):
        parts.append(f"第{chunk['page']}页")
    if chunk.get("heading"):
        parts.append(chunk["heading"])
    q_no = chunk.get("question_no")
    if q_no:
        pts = f"{chunk['points']:g} 分" if chunk.get("points") else None
        if chunk.get("heading") == f"第{q_no}题":
            # 试卷块的 heading 就是“第N题”，不再重复题号，只补分值
            if pts:
                parts.append(pts)
        else:
            parts.append(f"第{q_no}题" + (f"（{pts}）" if pts else ""))
    ...
```

Result for t04: "2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15 分". Hmm — "分值写成'15 分'" — yes.

Wait check: does the exam chunk heading equal "第4题"? chunk_exam_pdf sets heading=f"第{q_no}题". Yes. And make_self_test_question fetches chunk from DB where heading is "第4题". Good.

### Task 3 (build_opening_line)

Rewrite with dedupe as planned. Format for wrong+blind merged:
- first wrong: f"上次你在『{name}』上错了 {count} 次，先复习它" + (f"（往年考 {w:g} 分但笔记里没有）" if blind)
- other wrong: f"『{name}』错了 {count} 次" + blind paren
- due (not mentioned): f"『{name}』今天到期" + blind paren if blind
- blind (not mentioned): f"『{name}』往年考 {w:g} 分但笔记里没有"

Wait the existing test asserts "『函数依赖与范式（3NF、BCNF）』往年考 25 分但笔记里没有" in line — that test has t04 only in blind_missing (t08 wrong, t03 due, t04 blind, no overlap), so unchanged parts still pass. Good — with paren appended only when overlap.

### Task 1 (selection logic)

coach.select_topic new signature:

```python
def select_topic(mastery, cov, recent_topic_ids=None, wrong_counts=None):
    """选题：到期复习 > 覆盖 thin/missing（盲区分）> 其余。

    recent_topic_ids：本会话已出过题的知识点（按出题顺序，旧→新）。
    - 刚出过的知识点（最近 2 题）不再出；
    - 计划池里的知识点先各出一遍，再回到本会话答错的，最后才重复其余。
    wrong_counts：本会话各知识点答错次数（回到答错的时按错次排序）。
    """
    recent = list(recent_topic_ids or [])
    last_two = set(recent[-2:])
    asked = set(recent)
    wrong_counts = wrong_counts or {}

    today = datetime.now(timezone.utc).date()
    due = [tid for tid, info in mastery.items()
           if info["state"].next_review
           and info["state"].next_review <= today]
    if due:
        due.sort(key=lambda tid: mastery[tid]["state"].next_review)
        for tid in due:
            if tid not in last_two:
                return {"topic_id": tid, "topic_name": mastery[tid]["state"].topic_name,
                        "coverage_level": None, "source": "due"}

    items = (cov or {}).get("items") or []
    if items:
        weak = [it for it in items if it["coverage_level"] in ("thin", "missing")]
        pool = weak or items
        pool = sorted(pool, key=lambda it: -it["blind_spot_score"])
        # 1) 计划里的知识点先轮一遍
        for it in pool:
            if it["topic_id"] not in asked:
                return dict(it, source="coverage")
        # 2) 都出过一遍后，先回到答错的（错次多的先）
        wrong_pool = sorted(
            (it for it in pool if it["topic_id"] in wrong_counts),
            key=lambda it: (-wrong_counts[it["topic_id"]], -it["blind_spot_score"]))
        for it in wrong_pool:
            if it["topic_id"] not in last_two:
                return dict(it, source="coverage")
        # 3) 其余
        for it in pool:
            if it["topic_id"] not in last_two:
                return dict(it, source="coverage")
        return dict(pool[0], source="coverage")

    tids = sorted(mastery.keys())
    for tid in tids:
        if tid not in last_two:
            return {...source="mastery"}
    if tids:
        tid = tids[0] if tids[0] != (recent[-1] if recent else None) else tids[-1]
        return {...}
    return None
```

Hmm wait: due topic within last_two — old code just returned due[0]. Now if all due in last_two, fall to coverage. Reasonable.

Note pass 1: "not in asked" — what if the pool's first unasked topic is in last_two? Can't be (asked includes last_two).

Wait, subtle issue: pass 1 iterates pool in blind order and returns first unasked — that gives pool-order rotation for the first len(pool) questions. With all-wrong 6 questions in dev: t04, t08, t02, t01, t05, (pool next unasked, e.g. t03...) — good, matches "计划里的知识点先轮一遍".

Hmm, but wait — pool = weak or items. What are the coverage levels in dev DB? Missing t04; thin t08, t02, t01?; t05? The user says plan mentions t02/t01/t05. If some are "covered" they wouldn't be in weak pool. The review-plan blind list at session start is thin/missing sorted by blind. The user's complaint "复习计划里的 t02、t01、t05 一直没轮到" suggests they're in the rotation. I'll verify against dev DB later with the 6-question test.

Now `routes/quiz.py` quiz_next changes:

```python
history = learning_store.session_questions(req.session_id)  # 旧→新
recent_topic_ids = [h["topic_id"] for h in history]
wrong_counts: dict[str, int] = {}
for h in history:
    if h.get("answered_at") and h.get("correct") == 0:
        wrong_counts[h["topic_id"]] = wrong_counts.get(h["topic_id"], 0) + 1
last_q = history[-1] if history else None
```

replaces last_question_of_session call (keep last_q for question_type rotation and last_sig).

last_sig = signature of last_q payload — but with used_sigs we can drop last_sig for fill; keep for LLM question_type rotation (last_q["question_type"]).

For self-test:
```python
used_nos = [((h["payload"].get("source") or {}).get("question_no"))
            for h in history
            if h["topic_id"] == topic["topic_id"]
            and (h["payload"].get("question_type") == "self")]
used_nos = [n for n in used_nos if n is not None]
payload = make_self_test_question(topic, course_id, used_nos)
```

For fill:
```python
used_terms = {(h["payload"].get("expected_answer"))
              for h in history
              if h["topic_id"] == topic["topic_id"]
              and h["payload"].get("question_type") == "fill"}
used_terms.discard(None)
```

_rule_fill:
```python
def _rule_fill():
    chunks = _topic_material_chunks()
    for chunk in chunks:
        q = make_fill_question(topic, chunk, used_terms)
        if q:
            return q
    return None
```

Wait but original also avoided identical question as last (last_sig). With used_terms covering topic's used answers, same blank won't repeat. But different chunks might produce same sig? Sig includes chunk_id so no. Also explicit requested topic (req.topic_id) where user re-drills same topic — used_terms gives a new blank. Good. But careful: if used_terms contains all candidates in all chunks, make_fill_question falls back to first candidate (repeat). Acceptable.

make_fill_question signature: `make_fill_question(topic, chunk, used_terms=None)`:

```python
candidates = _blank_candidates(topic, content, heading)
first_fallback = None
for term in candidates:
    fragment, occurrences = _sentence_with(content, term)
    if occurrences < 1:
        continue
    blanked = fragment.replace(term, "＿＿＿", 1)
    if blanked == fragment:
        continue
    q = {...}
    if first_fallback is None:
        first_fallback = q
    if term not in (used_terms or set()):
        return q
return first_fallback
```

Hmm, but this changes behavior when used_terms is None/empty: first candidate returned immediately — same as before. Good.

make_self_test_question with rotation:

```python
def make_self_test_question(topic, course_id, used_question_nos=None):
    """missing 知识点：给往年原题自测，提示先补笔记。

    同一知识点有多道往年原题时在它们之间轮换：优先没出过的，
    都出过则出得次数最少的（同次数按题号升序）。
    """
    used = list(used_question_nos or [])
    eqs = [eq for eq in topic.get("exam_questions") or []
           if eq.get("question_no") is not None]
    if not eqs:
        return None
    eqs.sort(key=lambda eq: (used.count(eq["question_no"]), eq["question_no"]))
    for eq in eqs:
        chunk = _fetch_exam_chunk(course_id, eq["question_no"])
        if not chunk:
            continue
        ...return payload
    return None
```

Hmm but original iterated exam_questions in order and returned first fetchable. Now sorting by used count. When used empty → sorted by question_no → first fetchable = lowest qno. Same as before (original preserved exam_questions order which is presumably by question_no from assignment order — get_exam_chunks order). OK.

But wait: if the first-fetchable logic — sorting then iterating, skipping unfetchable. If lowest-qno chunk unfetchable, continue to next. Fine.

Now learning_store.session_questions + ordering precision. Change quiz_questions.created_at to DATETIME(3) in CREATE TABLE + ensure existing table altered. ensure_learning_tables runs at startup — add a check:

```python
with conn.cursor() as cur:
    cur.execute("SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='quiz_questions' AND COLUMN_NAME='created_at'")
    row = cur.fetchone()
    if row and "datetime(3)" not in (row["COLUMN_TYPE"] or "").lower():
        cur.execute("ALTER TABLE quiz_questions MODIFY created_at DATETIME(3)")
```

Hmm, is DATETIME(3) supported in their seekdb (OceanBase MySQL mode)? Should be. But risk: existing tests use SQLite? Let me check conftest.py — tests probably use a fake DB or real? test_integration marked integration uses real DB. Unit tests for learning_store? Check where ensure_learning_tables is tested. Actually maybe simpler to avoid schema change: order by created_at ASC, id ASC won't work. Alternative: add `seq BIGINT` column with per-session MAX+1:

```python
def create_question(...):
    seq = next value
```

needs SELECT MAX(seq) WHERE session_id first. Two statements. And _ensure_columns for existing table. That avoids DATETIME(3) uncertainty but adds a query per question. Both fine. I'll go with DATETIME(3) — cleaner, single column type change, and also improves answered_at ordering? Not needed.

Hmm wait, actually also last_question_of_session ORDER BY created_at DESC benefits from millisecond precision too.

Actually, let me check what test harness does for learning_store tests (test_usage? test_m3_integration?). Search tests referencing session_questions/learning_store.

</details>

**Qoder：** 实现开始。先查 learning_store 相关测试和 conftest，确认测试环境怎么处理数据库。

🔧 **Bash** ```bash
grep -rn "learning_store\|session_questions\|last_question" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/ | grep -v test_m3_integration
```

<details><summary>结果</summary>

```
No matches found
```

</details>

🔧 **Bash** ```bash
grep -n "integration\|DB\|database\|seekdb" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/conftest.py
```

<details><summary>结果</summary>

```
3:# Integration tests run against a separate database. The switch happens here
6:# the test database. conftest is imported before any examradar module, so
9:    os.environ["SEEKDB_DATABASE"] = os.environ.get(
10:        "SEEKDB_TEST_DATABASE", "examradar_test")
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/conftest.py`

<details><summary>结果</summary>

```
1	import os
2	
3	# Integration tests run against a separate database. The switch happens here
4	# and only here: application code never reads EXAMRADAR_IT, so a shell that
5	# still has the flag set can never silently point the CLI or the server at
6	# the test database. conftest is imported before any examradar module, so
7	# get_settings() picks up the override.
8	if os.environ.get("EXAMRADAR_IT"):
9	    os.environ["SEEKDB_DATABASE"] = os.environ.get(
10	        "SEEKDB_TEST_DATABASE", "examradar_test")
11
```

</details>

<details><summary>Qoder 思考</summary>

So integration tests use a real seekdb test database. Unit tests don't touch DB. OK.

Now write the code. Start with coach.py changes (select_topic, make_fill_question, make_self_test_question, _chunk_source).

</details>

**Qoder：** 开始改代码。先改 coach.py（选题、出题、出处）。

🔧 **TaskUpdate** ```json
{
 "status": "in_progress",
 "taskId": "1"
}
```

<details><summary>结果</summary>

```
Updated task #1 status
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py`（替换 1295 → 2463 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

**Qoder：** 现在是 `make_fill_question`、`_chunk_source` 和 `make_self_test_question`：

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py`（替换 1028 → 1315 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Wait — _rule_fill in quiz.py iterates chunks and calls make_fill_question per chunk. With used_terms passed per chunk, chunk 1 might have all terms used → fallback to chunk1's first candidate, but chunk 2 might have a fresh term. So _rule_fill needs to try all chunks preferring fresh ones. I'll restructure _rule_fill: first pass over all chunks with used_terms (make_fill_question returns q only if fresh? No — my implementation returns fallback even when used). Hmm. Need make_fill_question to signal "fresh" vs fallback. Simpler: in _rule_fill, call make_fill_question(chunk, used_terms) twice? Let me redesign: make_fill_question returns the question; _rule_fill first pass: for each chunk, get q; if q and q["expected_answer"] not in used_terms → return. Second pass: return first q. That works without changing make_fill_question's contract:

```python
def _rule_fill():
    chunks = _topic_material_chunks()
    fallback = None
    for chunk in chunks:
        q = make_fill_question(topic, chunk, used_terms)
        if q is None:
            continue
        if fallback is None:
            fallback = q
        if q["expected_answer"] not in used_terms:
            return q
    return fallback
```

Hmm but make_fill_question with used_terms prefers a fresh term within the chunk already (returns early on fresh term). So q["expected_answer"] in used_terms only when the chunk has no fresh candidate. Good.

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py`（替换 1690 → 2218 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Wait, one detail: `_chunk_source` for non-exam chunks (notes) — question_no is None, unchanged. For exam chunks from `_term_matched_chunks` — question_no is None there. Only exam chunks have question_no. Good.

Now mastery.py build_opening_line rewrite.

</details>

**Qoder：** 现在改 mastery.py 的开场白去重。

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/mastery.py`（替换 846 → 1416 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/mastery.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Wait, there's a subtle bug: wrong_recent truncation to first 3 and blind to first 2 — if wrong_recent[0..2] include a topic also in blind_missing[:2], mentioned prevents duplicate. But if a topic is wrong_recent[3+] (truncated) and also in blind[:2]... then it appears only once (as blind) — fine.

But there's also a case: due_today topic that's also blind gets merged — good.

Edge: `wrong_recent[1:3]` might mention a blind topic whose blind entry wasn't in top-2 — then _blind_note finds nothing (blind_by_tid built from full blind_missing list, not truncated!). blind_by_tid includes all entries. Note appended even if entry beyond top 2 — that's fine, still one mention.

Now chunker.py fix (task 5).

</details>

**Qoder：** 现在改 chunker.py，切题时去掉末尾的大题标题行。

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/chunker.py`（替换 83 → 449 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/chunker.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/chunker.py`（替换 153 → 185 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/chunker.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

**Qoder：** 现在更新 `learning_store.py`（添加 `session_questions`，`created_at` 毫秒精度），并调整 `quiz.py` 的调用。

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py`（替换 826 → 1431 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

The create_question insert uses _utc_now() which returns datetime with microseconds — DATETIME(3) keeps milliseconds. Good.

Now add session_questions function after last_question_of_session.

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py`（替换 508 → 1042 字符）

<details><summary>结果（出错）</summary>

```
Error: Failed to edit, 0 occurrences found for old_string in /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py. Ensure you're not escaping content incorrectly and check whitespace, indentation, and context. Use Read tool to verify.
```

</details>

<details><summary>Qoder 思考</summary>

The original has "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,)) — let me re-check the exact original text. Lines 204-216:

```
def last_question_of_session(session_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

Wait line 212-213: `"SELECT * FROM quiz_questions WHERE session_id = %s " "ORDER BY created_at DESC, id DESC LIMIT 1"` — I wrote "ORDER BY created_at DESC, id DESC LIMIT 1" in old_string, and the file has... let me check: line 212-213 in my read: 

```
                cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
                            "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

Hmm, that's what I wrote. Oh wait — I see, the actual file line 211-212: `cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s " "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))`. In my read earlier: 

```
212	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
213	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

That matches... Actually wait, no. Line 210-211:
```
210	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
211	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```
Hmm, in my earlier Read, lines 204-216 show:

```
204	def last_question_of_session(session_id: str) -> Optional[dict]:
205	    conn = get_connection()
206	    try:
207	        with conn.cursor() as cur:
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

Hmm no, it was:
```
207	        with conn.cursor() as cur:
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
210	            row = cur.fetchone()
```

Wait actually from the Read: lines 204-216:
```
204	def last_question_of_session(session_id: str) -> Optional[dict]:
205	    conn = get_connection()
206	    try:
207	        with conn.cursor() as cur:
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
210	            row = cur.fetchone()
211	            if row and isinstance(row.get("payload"), str):
212	                row["payload"] = json.loads(row["payload"])
213	            return row
214	    finally:
215	        conn.close()
```

Hmm, but in the original read it showed "ORDER BY created_at DESC, id DESC LIMIT 1"? Let me look again at the actual read output above: 

"cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s " "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))" — the read output showed:

```
209	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
210	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

Hmm, no. Actually from the Read output earlier:

```
204	def last_question_of_session(session_id: str) -> Optional[dict]:
205	    conn = get_connection()
206	    try:
207	        with conn.cursor() as cur:
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

Wait, the actual text in the Read output was:

```
206	    try:
207	        with conn.cursor() as cur:
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

I can't recall precisely — it said `"ORDER BY created_at DESC, id DESC LIMIT 1"`. Actually looking at the original Read output at the top: lines 204-214:

```
204	def last_question_of_session(session_id: str) -> Optional[dict]:
205	    conn = get_connection()
206	    try:
207	        with conn.cursor() as cur:
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
210	            row = cur.fetchone()
```

Hmm — actually it said `ORDER BY created_at DESC, id DESC LIMIT 1`? The Read output earlier showed:

"cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s " "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))"

No wait, scrolling up: it was

```
207	        with conn.cursor() as cur:
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

Ugh. Actually the original read says:

```
208	            cur.execute("SELECT * FROM quiz_questions WHERE session_id = %s "
209	                        "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
```

I genuinely don't remember whether it's "created_at DESC, id DESC". Let me just re-read that section of the file.

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py`

<details><summary>结果</summary>

```
210	            )
211	    finally:
212	        conn.close()
213	
214	
215	def last_question_of_session(session_id: str) -> Optional[dict]:
216	    conn = get_connection()
217	    try:
218	        with conn.cursor() as cur:
219	            cur.execute(
220	                "SELECT * FROM quiz_questions WHERE session_id = %s "
221	                "ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,))
222	            row = cur.fetchone()
223	            if row and isinstance(row.get("payload"), str):
224	                row["payload"] = json.loads(row["payload"])
225	            return row
226	    finally:
227	        conn.close()
228	
229	
230	def session_question_stats(session_id: str) -> dict:
231	    """{asked, answered, correct, wrong_by_topic: {topic_id: (name, count)}}"""
232	    conn = get_connection()
233	    try:
234	        with conn.cursor() as cur:
235	            cur.execute(
236	                "SELECT topic_id, topic_name, correct FROM quiz_questions "
237	                "WHERE session_id = %s AND answered_at IS NOT NULL", (session_id,))
238	            rows = cur.fetchall()
239	    finally:
240	        conn.close()
241	    asked = len(rows)
242	    correct = sum(1 for r in rows if r["correct"])
243	    wrong_by_topic: dict[str, tuple[str, int]] = {}
244	    for r in rows:
245	        if not r["correct"]:
246	            tid = r["topic_id"]
247	            name, count = wrong_by_topic.get(tid, (r["topic_name"], 0))
248	            wrong_by_topic[tid] = (name, count + 1)
249	    return {"asked": asked, "correct": correct, "wrong_by_topic": wrong_by_topic}
… （共 41 行，此处省略 1 行，完整内容见 .jsonl）
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py`（替换 264 → 807 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/learning_store.py (1 replacements).
```

</details>

**Qoder：** 现在我来重写 `quiz.py` 中的选择逻辑：

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`（替换 502 → 768 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`（替换 1106 → 1679 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Now `last_sig` is unused — check: it was used in _rule_fill only. The LLM rotation uses last_q["question_type"]. Remove last_sig and the _question_signature helper? _question_signature still used? In quiz.py, after my change, last_sig is defined but unused. Remove both last_sig assignment and _question_signature function (check other usages). Grep.

</details>

🔧 **Bash** ```bash
grep -n "_question_signature\|last_sig" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/*.py
```

<details><summary>结果</summary>

```
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py:52:def _question_signature(payload: dict) -> tuple:
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py:120:    last_sig = _question_signature(last_q["payload"]) if last_q else None
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`（替换 430 → 243 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`（替换 112 → 37 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Update the quiz.py module docstring to reflect new behavior (line 1-5). Also update memory.html nowrap (task 4). Then update tests.

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`（替换 125 → 164 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

**Qoder：** 现在是 memory.html 表格（任务 4）：

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/static/memory.html`（替换 324 → 523 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/static/memory.html (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Tasks 2, 3, 4, 5 code changes done. Now update existing tests (TestSelectTopic signature, self-test tests) and add new tests. Update test_quizgen.py:

1. TestSelectTopic: change calls to new signature.
2. TestSelfTestQuestion: make_self_test_question now sorts eqs; add rotation test with two exam questions and used=[4].
3. Add source label dedupe test.
4. Add selection order tests (rotation, gap ≥2).
5. test_mastery opening line dedupe test.
6. test_chunker: section title stripped test.

Let me write the test edits.

</details>

**Qoder：** 代码改完，现在更新和新增单测。先改 test_quizgen.py。

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py`（替换 1376 → 3811 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Wait: in test_exam_source_label_no_duplicate_question_no, _fetch_exam_chunk returns "heading": "第4题" — real exam chunks have heading "第4题" from chunker. Good.

Now the TestSelectTopic rewrite. Design tests:

```python
class TestSelectTopic:
    def test_due_first(self):
        # update call signature
        topic = coach.select_topic(mastery, cov)  # recent=None
        assert t03

    def test_blind_spot_by_exam_weight(self): ...

    def test_no_data_returns_none(self): ...

    def _cov_items(self, ids):
        return {"items": [
            {"topic_id": tid, "topic_name": f"知识点{tid}", "keywords": [],
             "coverage_level": "thin", "coverage_score": 0.3,
             "exam_weight": weight, "exam_questions": [],
             "blind_spot_score": blind} ...]}
```

Let me define pool of 5: t04(blind 22.5), t08(8.4), t02(7.9), t01(7.0), t05(6.0).

Test rotation: simulate session where all answers wrong. recent=[] → t04. recent=[t04] wrong{t04:1} → t08 (first unasked). recent=[t04,t08] → t02. ... after all 5 asked: recent=[t04,t08,t02,t01,t05] → pass1 none; pass2 wrong all 5, exclude last_two {t01,t05} → sorted by (-count, -blind): t04 count1 blind22.5 → t04. So 6th = t04.

Test non-consecutive: assert over simulated 8 picks that new topic not in last two.

Also test "wrong ones prioritized by wrong count": e.g., after rotation, t08 wrong twice → preferred.

Write:

```python
class TestSelectTopic:
    POOL = [
        {"topic_id": "t04", "topic_name": "范式", "keywords": [],
         "coverage_level": "missing", "coverage_score": 0.0,
         "exam_weight": 25.0, "exam_questions": [], "blind_spot_score": 22.5},
        {"topic_id": "t08", ... 8.4},
        {"topic_id": "t02", ... 7.9},
        {"topic_id": "t01", ... 7.0},
        {"topic_id": "t05", ... 6.0},
    ]

    def test_due_first(self): (existing, updated call)
    def test_blind_spot_by_exam_weight(self): (existing)
    def test_no_data_returns_none(self): (existing)
    def test_plan_topics_rotate_before_repeats(self):
        recent, wrong = [], {}
        order = []
        for _ in range(6):
            t = coach.select_topic({}, {"items": self.POOL}, recent, wrong)
            order.append(t["topic_id"])
            recent.append(t["topic_id"])
            wrong[t["topic_id"]] = wrong.get(t["topic_id"], 0) + 1
        assert order[:5] == ["t04", "t08", "t02", "t01", "t05"]
        assert order[5] == "t04"

    def test_same_topic_not_within_two_questions(self):
        recent, wrong = [], {}
        order = []
        for _ in range(10):
            t = coach.select_topic({}, {"items": self.POOL}, recent, wrong)
            order.append(t["topic_id"])
            if len(order) >= 3:
                assert order[-1] not in order[-3:-1]
            recent.append(...); wrong ...
        # also each adjacent different
        for a, b in zip(order, order[1:]): assert a != b

    def test_returns_to_most_wrong_after_rotation(self):
        # rotate all 5 with t08 wrong 2 times
        ...
```

Hmm test_same_topic_not_within_two_questions over 10 iterations — after all 5 asked, wrong_pool sorted by -count then -blind, excluded last_two. Sequence: t04,t08,t02,t01,t05 → next t04 (wrong1 each; sorted by blind desc, t04 first, not in last_two) → recent last2={t01,t05}, t04 ok. Then last2={t05,t04} → wrong_pool: all count... t04 count2 → first, but in last_two → skip → t08. Then t02, t01, then last2={t02,t01}? let's simulate: order = [t04,t08,t02,t01,t05,t04,t08,t02,t01,t05...]. Wait after t04,t08: last2={t04,t08}, wrong_pool sorted: t04(2? no t04 count=2 after 6th). Let me recount wrong counts: after 6 picks: t04:2, t08:1, t02:1, t01:1, t05:1. wrong_pool sort: t04(-2), then t08,t02,t01,t05 (blind desc). 7th pick: last2={t05,t04}: t04 excluded → t08. counts: t08:2. 8th: last2={t04,t08}: t04(2) excluded, t08(2) excluded → t02. 9th: last2={t08,t02}: t04 → t04 (count3). 10th: last2={t02,t04}: t08. Sequence: t04,t08,t02,t01,t05,t04,t08,t02,t04,t08. Check gap: t04 at 1,6,9: positions 6 and 9 → gap 2 questions (positions 7,8 are others). OK. Constraint "new not in last two" holds by construction (except when fallback). Fine.

Also add test due-topic excluded when in last_two? Optional. Keep the three new tests.

Also: due_first test — mastery has t03 due. select_topic(mastery, cov) with recent None. Update calls.

Now write the replacement for TestSelectTopic.

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py`（替换 1498 → 4280 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Wait — test_due_within_two_questions_skipped: mastery has t03 due; recent [t03, t08]. last_two={t03,t08}; t03 due but in last_two → skipped; falls to coverage pool pass 1: unasked topics — t04 not in asked={t03,t08} → returns t04. Good.

test_returns_to_most_wrong_topic: recent=[all 5 asked]; wrong t08:2 highest. wrong_pool sorted by (-count,-blind): t08 first, not in last_two {t01,t05} → t08. Good.

Now add fill-question used_terms test and mastery opening-line dedupe test, and chunker test.

Add to TestFillQuestion:

```python
def test_fill_rotates_blank_when_term_used(self):
    topic = {...terms 隔离级别 found, MVCC found}
    chunk = make_chunk("隔离级别由低到高……MVCC 通过快照……")
    q1 = make_fill_question(topic, chunk)  # 隔离级别
    q2 = make_fill_question(topic, chunk, {"隔离级别"})  # MVCC
    assert q2["expected_answer"] == "MVCC"
```

Content: "隔离级别由低到高有读未提交、读已提交等；MVCC 通过快照实现读写不阻塞。" candidates: found terms 隔离级别 (in content), MVCC (in content) → q2 picks MVCC. And used both → fallback 隔离级别.

test_mastery opening line dedupe:

```python
def test_opening_line_topic_mentioned_once(self):
    line = build_opening_line(
        wrong_recent=[("t04", "函数依赖与范式（3NF、BCNF）", 2)],
        due_today=[],
        blind_missing=[("t04", "函数依赖与范式（3NF、BCNF）", 25.0)])
    assert line.count("函数依赖与范式") == 1
    assert "错了 2 次" in line and "往年考 25 分" in line
```

chunker test:

```python
def test_trailing_section_title_removed(self):
    text = """4.（15 分）求候选码。
5.（10 分）分解为 BCNF。
三、查询处理与事务（共 50 分）
6.（5 分）为什么尽早执行选择？"""
    chunks = chunk_exam_pdf("", [text])
    q5 = [c for c in chunks if c.question_no == 5][0]
    assert "三、" not in q5.content
    q4 = ...
    assert "二、" not in q4.content — no 二、 here. fine.
```

Also check that q4 content ends with its own text.

Where to add: TestChunkExamPdf class in test_chunker.py.

</details>

**Qoder：** 新增填空轮换、开场白去重、大题标题剥离的单测。

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py`（替换 597 → 1529 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_mastery.py`（替换 92 → 944 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_mastery.py (1 replacements).
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_chunker.py`（替换 182 → 624 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_chunker.py (1 replacements).
```

</details>

<details><summary>Qoder 思考</summary>

Now run the unit tests. `cd app && uv run pytest` — but this needs to run without DB. conftest sets SEEKDB_DATABASE only if EXAMRADAR_IT. Unit tests shouldn't need DB. Run.

</details>

**Qoder：** 跑单测。

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && uv run pytest 2>&1 | tail -5
```

<details><summary>结果（出错）</summary>

```
Error: Allow Bash to run: cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && uv run pytest 2>&1 | tail -5?
```

</details>

<details><summary>Qoder 思考</summary>

Right — the permission rules forbid `2>&1` and pipes. Run plain commands.

</details>

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && uv run pytest -q
```

<details><summary>结果</summary>

```
........................................................................ [ 28%]
.............................ssssssssssssssssssssssssssss............... [ 57%]
........................................................................ [ 86%]
...................................                                      [100%]
223 passed, 28 skipped in 1.33s
```

</details>

<details><summary>Qoder 思考</summary>

All unit tests pass (223, up from 213 + 10 new). Now run integration tests. Need dev seekdb running at 127.0.0.1:10800 per environment. EXAMRADAR_IT=1 uses test database examradar_test (default) — wait, `SEEKDB_TEST_DATABASE` env default "examradar_test". Is that in dev seekdb? Session 10 ran "34 passed" with EXAMRADAR_IT=1, so yes.

</details>

**Qoder：** 单测全过（223 passed，新增 10 条）。跑集成测试。

🔧 **Bash** ```bash
uv run pytest -q -m integration
```

<details><summary>结果</summary>

```
ssssssssssssssssssssssssssss......                                       [100%]
6 passed, 28 skipped, 217 deselected in 1.15s
```

</details>

🔧 **Bash** ```bash
export EXAMRADAR_IT=1 && uv run pytest -q -m integration
```

<details><summary>结果</summary>

```
..................................                                       [100%]
34 passed, 217 deselected in 3.52s
```

</details>

<details><summary>Qoder 思考</summary>

Integration tests pass (34). But wait — my learning_store change does an ALTER TABLE on quiz_questions in ensure_learning_tables — that runs at app startup (lifespan), not in these tests? test_m3_integration may call ensure_learning_tables. It passed anyway.

Wait — did the ALTER actually run against the test DB? These tests hit examradar_test. Fine either way.

Concern: `cur.fetchone()` after information_schema query — if quiz_questions table doesn't exist yet on first run (fresh DB)? ensure_learning_tables creates the table first (CREATE TABLE IF NOT EXISTS before my check), so table exists. Good.

But one issue: my ALTER check happens inside `with conn.cursor() as cur:` — nested inside the try after creating both tables. Let me verify the edit placement is syntactically valid — tests passed and learning_store imports fine, but ensure_learning_tables may not have been exercised if no test calls it... test_m3_integration likely starts sessions against the test DB — that calls ensure via app lifespan? The route tests use TestClient with lifespan? Let me check that the ensure path runs without error by starting the dev server later anyway.

Now: dev DB tasks — re-import exam paper. First check .env and start dev server? Actually re-import can be done via the dev server API or directly via python. Steps:
1. Delete exam document from dev DB (find document by name like 期末试卷, delete chunks + document rows).
2. Re-import via ingest (python -c or start server and POST). Since e2e re-import check uses API; simpler to use a small python script in .cache/scratch that calls ingest.ingest_bytes or cli import_path with doc_kind exam.
3. Re-run coverage analyze — needs syllabus text. Where's the syllabus? The analyze API takes syllabus_text. There's probably a stored one or the radar page submits it. Check dev-records or how previous sessions ran analyze on dev. Maybe scripts/calibrate.py has the syllabus. Let me check .env and scripts.

Also verify current dev DB state (coverage levels) to understand the pool. Let me write a scratch script to query.

</details>

**Qoder：** 集成测试 34 passed。现在处理开发库：查当前覆盖数据和试卷文档，然后删除重导。先看 .env 和现有数据。

🔧 **Bash** ```bash
cat /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.env
```

<details><summary>结果</summary>

```
# Local development only (gitignored). Containers were started by the product owner.
SEEKDB_HOST=127.0.0.1
SEEKDB_PORT=10800
SEEKDB_USER=root
SEEKDB_PASSWORD=***REDACTED***
SEEKDB_DATABASE=examradar
POWERCONTEXT_URL=http://127.0.0.1:18801
APP_HOST=127.0.0.1
APP_PORT=18800
```

</details>

🔧 **Bash** ```bash
ls /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/samples /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/samples/course-db /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/scripts
```

<details><summary>结果</summary>

```
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/samples:
course-db

/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/samples/course-db:
README.md
_src
exams
notes
papers
slides
syllabus.txt

/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/scripts:
calibrate.py
e2e_verify.py
load_sample.sh
```

</details>

🔧 **Bash** ```bash
ls /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/samples/course-db/exams /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch 2>/dev/null; cat /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/samples/course-db/syllabus.txt
```

<details><summary>结果</summary>

```
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch:
acceptance_dev.py
browser_check.py
browser_verify.py
calibrate_out.txt
calibrate_out2.txt
card_shots.py
check_cov2.py
check_coverage.py
check_exam.py
chrome-profile
chrome-profile2
chunks_dev.json
chunks_dump.txt
drop_test_db.py
dump_chunks.py
dump_new_chunks.py
exam_dev.json
md_test.py
new_chunks.txt
pwvenv
run_cal.py
run_calibrate.sh
run_it.sh
s05_radar.png
s05_radar_t04.png
s05_radar_t09.png
s05_usage.png
s05b_analyze.py
s05b_browser.py
s05b_chart_1440x900.png
s05b_chart_768x1024.png
s05b_radar_1440x900.png
s05b_radar_768x1024.png
s05b_result.json
s05b_table_1440x900.png
s05b_table_768x1024.png
s05b_viewport_1440x900.png
s05b_viewport_768x1024.png
s10-coach-ended.png
… （共 66 行，此处省略 26 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Now write a scratch script to:
1. Inspect dev DB: documents list, current coverage levels (to know the pool).
2. Delete the exam document (chunks + document).
3. Re-import via ingest.
4. Re-run coverage analyze with the syllabus.
5. Verify: 10 judgments, 11 question assignments match design truth; Q5 content has no section title.

But first check current coverage levels to understand the pool for the 6-question test. Design truth — where's the expected truth table? README「设计真值」. Let me check README for the truth table to compare after re-analysis.

</details>

🔧 **Bash** ```bash
grep -n -A 20 "设计真值" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/README.md | head -50
```

<details><summary>结果</summary>

````
163:- 以示例课程《数据库系统原理》为初始数据（含 6 条验收检索和 10 个知识点的设计真值）；
164-- 每步给出界面操作 + 等价 curl / CLI 命令 + 预期结果；
165-- 说明如何核对 seekdb 实际执行的 SQL（`GET_SQL`）与使用记录入库情况。
166-
167-或者用端到端脚本一次跑完（报告写入 `docs/validation/e2e-report.md`）：
168-
169-```bash
170-python3 scripts/e2e_verify.py --app-url http://127.0.0.1:18800
171-```
172-
173-## 配置项
174-
175-`.env`（复制自 `.env.example`）逐项说明。容器内的服务间地址由 `docker-compose.yml` 写死，`.env` 只提供下列变量。
176-
177-| 变量 | 默认值 | 说明 |
178-| --- | --- | --- |
179-| `SEEKDB_HOST` / `SEEKDB_PORT` | 127.0.0.1 / 10800 | seekdb 地址（本地开发连宿主机映射端口；容器内为 `seekdb:2881`，由 compose 写死） |
180-| `SEEKDB_USER` / `SEEKDB_PASSWORD` | root / change-me | 数据库账号；compose 部署务必改掉占位值 |
181-| `SEEKDB_DATABASE` | examradar | 应用使用的库名（自动创建） |
182-| `SEEKDB_TEST_DATABASE` | examradar_test | 集成测试专用库（`EXAMRADAR_IT=1` 时使用，不碰开发库） |
183-| `POWERCONTEXT_URL` | http://127.0.0.1:18801 | PowerContext 地址（容器内为 `http://powercontext:8000`） |
````

</details>

🔧 **Bash** ```bash
grep -n -B2 -A 25 "盲区" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/README.md | sed -n '1,60p'
```

<details><summary>结果</summary>

```
1-# ExamRadar 考前雷达
2-
3:**一句话**：ExamRadar 把期末前零散的课程资料（笔记、课件、往年试卷、阅读材料）变成一个可检索、可量化"复习覆盖度"的知识库——问笔记有出处，考前一眼看清"笔记没记到、但往年试卷分值很高"的盲区。
4-
5-## 解决什么问题
6-
7-期末复习时，学生手里的资料是零散的：笔记记得有的全有的缺、课件一摞 PDF、往年试卷不知道考什么。
8-常见痛点：
9-
10-- 想查一个概念，翻 PDF 太慢，普通全文搜索又搜不到"意思相近但用词不同"的段落；
11-- 不知道自己记的笔记**相对于考试范围**缺什么——尤其那些"试卷占分很高、笔记一个字没写"的知识点；
12-- 复习了几次、效果如何，没有记录。
13-
14-ExamRadar 用 seekdb 的**混合检索**（BM25 关键词 + 向量语义，RRF 融合，全部在数据库内完成）解决第一个问题；
15:用**考点词证据判定** + 往年试卷分值统计解决第二个问题（覆盖雷达和盲区排序）；用使用记录解决第三个问题。
16-
17-## 核心功能
18-
19-| 功能 | 说明 | 页面 |
20-| --- | --- | --- |
21-| 资料导入 | PDF / Markdown 上传，按类型（笔记/课件/试卷/论文）切块入库；试卷按题号切块并提取分值；SHA256 去重，重复导入幂等；中文 PDF 的"康熙部首"兼容字符自动归一化，否则检索搜不到 | `import.html` |
22-| 问笔记 | 输入问题，返回带**出处**（文件·页·题号·标题）的段落，BM25 + 向量双路分数；页面可展开查看 seekdb 实际执行 SQL | `ask.html` |
23-| 覆盖雷达 | 粘贴考试范围 → 解析出知识点 → 判定每个知识点 covered / thin / missing，**判定依据是"考点词是否真的出现在材料里 + 支撑正文量"**（可解释、可展开证据），不是黑盒相似度打分 | `radar.html` |
24:| 盲区排序 | `盲区分 = 试卷分值 × (1 − 覆盖度)`，一眼找出"没记到但分值高"的知识点，直接列出考察它的往年试题原文 | `radar.html` |
25:| 复习教练 | 开始学习会话（跨会话记忆生成开场白）→ 优先复习盲区与到期知识点 → 出题判分（missing 知识点给往年原题自测；thin/covered 从考点词所在段落出题，挖空考点词本身；可选 LLM 出选择题/简答题并判分）→ Leitner 盒子更新掌握度、答错记错题 | `coach.html` |
26-| 我的学习记忆 | 掌握度卡片（含 revision 变化轨迹）、错题本、复习计划、会话小结，全部存在本机 PowerContext 里（应用数据库里只有名字哈希） | `memory.html` |
27-| 使用记录 | 检索/导入/分析/答题自动记事件，区分真实使用与验证脚本（auto）；按天统计（按浏览器时区）、累计学习时长按学习会话计算（30 分钟无事件视为结束）、CSV/JSON 导出（CSV 带 BOM，Excel 打开不乱码） | `usage.html` |
28-
29-### 界面截图
30-
31-| 截图 | 内容 |
32-| --- | --- |
33-| ![首页](docs/images/index.png) | 首页：三服务状态、快捷入口 |
34-| ![问笔记](docs/images/ask.png) | 问笔记：带出处的结果、分数行、seekdb SQL |
35:| ![覆盖雷达](docs/images/radar.png) | 覆盖雷达：雷达图 + 盲区清单 |
36:| ![盲区展开](docs/images/radar-t04.png) | 盲区第一名 t04：判定理由、关联试题 |
37-| ![导入](docs/images/import.png) | 导入页：上传与资料列表 |
38-| ![使用记录](docs/images/usage.png) | 使用记录：统计与导出 |
39-| ![复习教练](docs/images/coach.png) | 复习教练：学习会话、出题与判分（盒号变化、记忆 artifact） |
40-| ![我的记忆](docs/images/memory.png) | 我的记忆：掌握度卡片与 revision 轨迹、错题、复习计划 |
… （共 60 行，此处省略 20 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

The design truth table with 10 judgments / 11 question assignments — probably in docs/VALIDATION.md or the DEVLOG session 05. The e2e script has EXPECTED constants. Let me check e2e_verify.py's expected coverage constants (they encode the design truth). Then I can reuse them in my dev re-check.

</details>

🔧 **Bash** ```bash
grep -n -B2 -A 40 "EXPECTED_COVERAGE\|DESIGN\|设计真值\|COVERAGE_TRUTH" /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/scripts/e2e_verify.py | sed -n '1,80p'
```

<details><summary>结果</summary>

```
91-]
92-
93:# 覆盖雷达设计真值（出处：samples/course-db/README.md「设计真值」表）。
94:DESIGN_LEVELS: dict[str, str] = {
95-    "t01": "missing",
96-    "t02": "thin",
97-    "t03": "covered",
98-    "t04": "missing",
99-    "t05": "missing",
100-    "t06": "covered",
101-    "t07": "covered",
102-    "t08": "thin",
103-    "t09": "covered",
104-    "t10": "covered",
105-}
106-
107-# 每道题归属的知识点与分值（出处：同上表"往年试卷（题号:分值）"列）。
108:DESIGN_ASSIGNMENTS: dict[int, tuple[str, float]] = {
109-    1: ("t01", 5.0),
110-    2: ("t02", 10.0),
111-    3: ("t03", 10.0),
112-    4: ("t04", 15.0),
113-    5: ("t04", 10.0),
114-    6: ("t05", 5.0),
115-    7: ("t06", 5.0),
116-    8: ("t07", 10.0),
117-    9: ("t08", 10.0),
118-    10: ("t09", 10.0),
119-    11: ("t10", 10.0),
120-}
121-
122-# 盲区第一名（出处：README.md —— "最大的盲区是 t04：……往年试卷却占 25 分"）。
123-BLIND_SPOT_TOP_TOPIC = "t04"
124-BLIND_SPOT_TOP_WEIGHT = 25.0
125-
126-
127-# ===========================================================================
128-# HTTP（仅标准库）
129-# ===========================================================================
130-
… （共 80 行，此处省略 40 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Design truth known. Weak pool (thin/missing): t01 (missing), t02 (thin), t04 (missing), t05 (missing), t08 (thin). Blind order: t04 25, t02 7.92, t08 8.41, t01 0?... t01 missing with Q1 (5分) → blind 5. t05 missing with Q6 (5分) → blind 5. So pool sorted by blind desc: t04(25), t08(8.41), t02(7.92), t01(5), t05(5) — t01 before t05? blind_spot_score ties 5.0? t01: exam_weight 5, coverage 0 → blind 5.0. t05: 5.0. Tie → pool sorted by -blind only (stable, keeps latest order which is blind-sort-key with topic_id asc on ties: t01 before t05).

So the 6-question all-wrong sequence should be: t04, t08, t02, t01, t05, t04. The user's example confirms t02, t01, t05 in plan. 

Now dev DB operations. Write a scratch script:

Phase 1 (inspect + delete + reimport + analyze + verify):
- Query documents: find exam doc id.
- DELETE chunks WHERE document_id=X; DELETE documents WHERE id=X.
- ingest the exam PDF (ingest.ingest_bytes with source "auto"? Should use "real"? This is a maintenance re-import — use source "auto" to not pollute real usage stats? Previous dev imports... The user said "先删除再导入" — either is fine; use "auto" to keep usage stats clean? Hmm, but coverage analyze also records usage. I'll use "auto" for both.

Wait — but careful: the dev DB coverage run also exists; re-analyze will create a new run. Fine.

- analyze(course_id="db101", syllabus_text=..., source="auto") — embeddings needed; uses local embedding model (bge-small-zh-v1.5) — available since previous sessions ran it.
- Verify: compare against DESIGN_LEVELS and DESIGN_ASSIGNMENTS; check Q5 content.

Check ingest signature: ingest_bytes(content, filename, course_id, doc_kind, source). Let me check quickly.

</details>

**Qoder：** 写个脚本做开发库的删除重导 + 重跑分析 + 核对真值。先确认 ingest 接口。

🔧 **Bash** ```bash
grep -n "def ingest_bytes\|def import_path" -A 15 /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/ingest.py
```

<details><summary>结果</summary>

```
34:def ingest_bytes(
35-    content: bytes,
36-    filename: str,
37-    course_id: str,
38-    doc_kind: str,
39-    source: str = "real",
40-) -> dict:
41-    """Ingest raw file content. Returns {document_id, chunk_count, skipped}.
42-
43-    Everything (chunking, embedding) happens before any DB write; the DB
44-    write itself is a single transaction, so a failure never leaves a
45-    half-imported document behind.
46-    """
47-    validate_input(filename, doc_kind, content)
48-    sha = hashlib.sha256(content).hexdigest()
49-
```

</details>

🔧 **Write** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_reimport.py`（写入 3862 字符）

<details><summary>结果</summary>

```
File created successfully at: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_reimport.py The file state is current in your context; no need to read it back.
```

</details>

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder && app/.venv/bin/python .cache/scratch/s10b_reimport.py
```

<details><summary>结果</summary>

```
documents: [{"id": 61, "name": "02-SQL速记.md", "doc_kind": "notes"}, {"id": 65, "name": "2025-2026-1-期末试卷A.pdf", "doc_kind": "exam"}, {"id": 64, "name": "第7讲-故障恢复.pdf", "doc_kind": "slides"}, {"id": 62, "name": "03-索引与B+树.md", "doc_kind": "notes"}, {"id": 63, "name": "05-事务与并发控制.md", "doc_kind": "notes"}, {"id": 66, "name": "two-phase-commit-primer.pdf", "doc_kind": "paper"}]
deleted document 65 2025-2026-1-期末试卷A.pdf (11 chunks)
re-import: {"document_id": 68, "chunk_count": 11, "skipped": false}
--- 第4题 (chunk 403, 15.0分) ---
4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。 （1）求 R 的所有候选码；（2）求属性集闭包 (A) +；（3）判断 R 最高属于第几范式，说明理由。
--- 第5题 (chunk 404, 10.0分) ---
5.（10 分）将上题的 R 分解为满足 BCNF 的关系模式集合，并判断你的分解是否无损连接、是否保持函数依赖。
analyze run_id: 10
10 个判定与设计真值一致: True
11 道题归属与设计真值一致: True
第5题原文结尾: 5.（10 分）将上题的 R 分解为满足 BCNF 的关系模式集合，并判断你的分解是否无损连接、是否保持函数依赖。
第5题不带大题标题: True

盲区分排序（教练选题池，thin/missing）:
  t04 函数依赖与范式（3NF、BCNF） missing weight=25.0 blind=25.0
  t08 隔离级别与 MVCC thin weight=10.0 blind=8.41
  t02 SQL 查询与视图 thin weight=10.0 blind=7.92
  t01 关系模型与关系代数 missing weight=5.0 blind=5.0
  t05 查询处理与优化 missing weight=5.0 blind=5.0
```

</details>

<details><summary>Qoder 思考</summary>

Dev DB re-import done:
- Q5 no longer contains the section title; the original text is correct.
- 10 judgments + 11 assignments match design truth.
- Pool order: t04, t08, t02, t01, t05 — exactly the plan topics the user mentioned.

Tasks 2, 3, 4, 5 code done and verified at DB level. Now the 6-question live test on the dev server (all wrong / self-rated "不会"). Start dev server on 18800 in background.

First verify e2e coach step compatibility — actually let me think about the e2e flow with the new code:

Q1: auto → select_topic with recent=[] → pool pass1 → t04 missing → make_self_test_question with used=[] → Q4 (第4题). Answer "不会" → wrong. wrong_counts={t04:1}.

Q2: explicit topic_id=t04 → make_self_test_question(topic, used=[4]) → 第5题. Answer "会" → correct.

Q3: auto, fill → recent=[t04,t04], last_two={t04}; pool pass1: first unasked = t08 → t08 fill. Answer wrong.

OK — but wait, e2e check for Q2 expects "同知识点答对（会）：盒 1→2" — fine.

The e2e report line "会话 1：3 题（t04 自测答错 → t04 自测答对 → t08 填空答错）" still accurate, but Q2 is now 第5题 instead of 第4题 — the report doesn't assert Q2's question_no. Check: q2 check asserts mistake_hist recall and box. And prepare recall happens on explicit topic t04 — history contains the Q4 mistake. Good.

One more: e2e `q1` self question text — with chunker fix, Q4 content unchanged (it never had the section title since Q5 follows). Good.

Also session start in e2e asserts opening_line is None for new learner — fine.

Now check coach.html for anything that depends on question order... The browser flow does Q1, answer, next — no explicit topic. Fine.

Now start dev server and run the 6-question test with a new learner name with timestamp. The 6 questions, all answered wrong or self "不会":
- Q1: t04 self → "不会"
- Q2: t08 fill → wrong answer
- Q3: t02 fill → wrong
- Q4: t01 missing → self "不会" (t01 is missing! pool pass1 order: t04, t08, t02, t01, t05)

Wait t01 is missing → make_self_test_question for t01 → Q1 (第1题, 5分, t01). t05 missing → Q6. Good.

- Q5: t05 self → "不会"
- Q6: pool all asked → wrong_pool sorted by (-count, -blind): all count 1 → t04 → self-test with used=[4] → 第5题!

Collect for DEVLOG: 知识点、题型、出处 for each of 6 questions.

Write an API script for this. Start server first.

</details>

**Qoder：** 开发库重导完成：第5题不再带大题标题，10 个判定、11 道归属全部与设计真值一致，盲区池顺序 t04 > t08 > t02 > t01 > t05。现在启动开发服务器做 6 题实测。

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800
```

<details><summary>结果</summary>

```
Command running in background with ID: bbozpq7nj. Output is being written to: /var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-qoder/aa07df25-90a3-495e-bbaf-22c2ed429508/tasks/bbozpq7nj.output You will be notified when it completes. To check interim output, use Read on that file path.
```

</details>

🔧 **Bash** ```bash
sleep 8 && curl -s http://127.0.0.1:18800/api/health
```

<details><summary>结果</summary>

```
{"seekdb":{"ok":true},"embedding":{"ok":true,"model":"BAAI/bge-small-zh-v1.5 (512d)"},"powercontext":{"ok":true,"detail":"ok"}}
```

</details>

🔧 **Write** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_six.py`（写入 2556 字符）

<details><summary>结果</summary>

```
File created successfully at: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_six.py The file state is current in your context; no need to read it back.
```

</details>

🔧 **Bash** ```bash
app/.venv/bin/python .cache/scratch/s10b_six.py
```

<details><summary>结果（出错）</summary>

```
Exit code 1
learner: 10b验收同学011047
session: f548817b794b408d
opening_line(应为空): None
blind_topics: [('t04', 'missing', 25.0), ('t08', 'thin', 8.41), ('t02', 'thin', 7.92), ('t01', 'missing', 5.0), ('t05', 'missing', 5.0)]
Q1: t04 函数依赖与范式（3NF、BCNF） | self | 2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15.0 分 | correct=False box=1->1
     题目: 4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。
Q2: t08 隔离级别与 MVCC | fill | 05-事务与并发控制.md · 第5章 事务与并发控制（课堂笔记） > 5.5 隔离级别（只记了个大概，课上讲得快） | correct=False box=1->1
     题目: 填空：SQL 标准定义了四个＿＿＿：读未提交、读已提交、可重复读、可串行化。（4 个字）
Q3: t02 SQL 查询与视图 | fill | 02-SQL速记.md · 第2章 SQL（速记，没整理完） > 基本查询 | correct=False box=1->1
     题目: 填空：- `＿＿＿ 列 FROM 表 WHERE 条件`，`DISTINCT` 去重。
Traceback (most recent call last):
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_six.py", line 27, in <module>
    q = post("/api/quiz/next", {"session_id": s["session_id"]})
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_six.py", line 13, in post
    with urllib.request.urlopen(req, timeout=60) as r:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/miniconda3/lib/python3.12/urllib/request.py", line 215, in urlopen
    return opener.open(url, data, timeout)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/miniconda3/lib/python3.12/urllib/request.py", line 521, in open
    response = meth(req, response)
               ^^^^^^^^^^^^^^^^^^^
  File "/opt/miniconda3/lib/python3.12/urllib/request.py", line 630, in http_response
    response = self.parent.error(
               ^^^^^^^^^^^^^^^^^^
  File "/opt/miniconda3/lib/python3.12/urllib/request.py", line 559, in error
    return self._call_chain(*args)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/miniconda3/lib/python3.12/urllib/request.py", line 492, in _call_chain
    result = func(*args)
             ^^^^^^^^^^^
  File "/opt/miniconda3/lib/python3.12/urllib/request.py", line 639, in http_error_default
    raise HTTPError(req.full_url, code, msg, hdrs, fp)
urllib.error.HTTPError: HTTP Error 500: Internal Server Error
```

</details>

<details><summary>Qoder 思考</summary>

Q4 (t01, missing) failed with HTTP 500. Check server log. Likely `make_self_test_question` — t01's exam question is 第1题 (chunk exists). Or the ALTER TABLE for created_at failing? No — Q1-Q3 worked (create_question succeeded). Wait — Q3 was created fine, answered fine. Q4 next → 500.

Look at server output.

</details>

**Qoder：** Q1–Q3 正常（顺序 t04→t08→t02 已对），Q4 报 500。查服务器日志。

🔧 **Bash** ```bash
tail -40 /var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-qoder/aa07df25-90a3-495e-bbaf-22c2ed429508/tasks/bbozpq7nj.output
```

<details><summary>结果</summary>

```
File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 2894, in handle
    await included_router._handle_selected(scope, receive, send)
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 1865, in _handle_selected
    await original_route.handle(scope, receive, send)
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 1328, in handle
    await effective_context.app(scope, receive, send)
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 166, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 152, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 745, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 374, in run_endpoint_function
    return await run_in_threadpool(
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/starlette/concurrency.py", line 34, in run_in_threadpool
    return await anyio.to_thread.run_sync(func)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/anyio/to_thread.py", line 65, in run_sync
    return await get_async_backend().run_sync_in_worker_thread(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 2706, in run_sync_in_worker_thread
    return await future
           ^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 1100, in run
    result = context.run(func, *args)
             ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/.venv/lib/python3.12/site-packages/fastapi/telemetry/_api.py", line 244, in _run_sync_endpoint
    return function(**arguments)
           ^^^^^^^^^^^^^^^^^^^^^
  File "/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py", line 119, in quiz_next
    topic_history = [h for h in history if h["topic_id"] == topic["topic_id"]]
                                           ~^^^^^^^^^^^^
KeyError: 'topic_id'
```

</details>

<details><summary>Qoder 思考</summary>

The exam chunk rows from DB — `_fetch_exam_chunk` returns row dict... no wait, `history` rows come from `session_questions` — SELECT * FROM quiz_questions. Rows should have topic_id. Hmm, KeyError 'topic_id' on h — so some row lacks 'topic_id'? Wait — the issue: `history` — I used `learning_store.session_questions(req.session_id)`. Wait, in quiz_next, history variable name collision! Look at quiz.py: later in the function there's `history: list[dict] = []` for mistake history (prepare recall), defined BEFORE my topic_history? Order: session lookup → cov → client → mastery → history/session_questions → ... wait let me re-read the current quiz_next flow.

Original order:
1. session checks, cov, client, mastery
2. last_q ... my new history block
3. topic selection
4. `history: list[dict] = []` — mistake recall history! This REBINDS history to the prepare recall list!

So my `topic_history` computed after step 4? No — I inserted `topic_history` where `last_sig` was, which is AFTER the prepare-recall `history` assignment (line ~114 originally: last_sig was after history recall). Yes! Original code: history (prepare recall) defined at line 104-112, then last_sig at 114. So my new code references `history` = prepare recall items (which have "text" key, not "topic_id").

Fix: rename my session history variable. Let me read current quiz.py around quiz_next to fix properly.

</details>

**Qoder：** 问题找到：`history` 变量与召回错题的 `history` 重名。看当前代码修正。

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`

<details><summary>结果</summary>

```
64	    source = "auto" if x_examradar_source == "auto" else "real"
65	    session = learning_store.get_session(req.session_id)
66	    if not session:
67	        return JSONResponse({"error": "会话不存在"}, status_code=404)
68	    if session.get("ended_at"):
69	        return JSONResponse({"error": "会话已结束，请重新开始会话"}, status_code=409)
70	
71	    course_id = session["course_id"]
72	    scope_id = session.get("scope_id")
73	    cov = coverage_snapshot(course_id)
74	
75	    client = PowerContextClient()
76	    # scope_id 为空说明会话创建时 PowerContext 就不可用，直接进入降级
77	    memory_ok = scope_id is not None
78	    mastery: dict[str, dict] = {}
79	    if scope_id:
80	        try:
81	            mastery = load_mastery_states(client, scope_id)
82	        except PowerContextUnavailable:
83	            memory_ok = False
84	
85	    history = learning_store.session_questions(req.session_id)
86	    last_q = history[-1] if history else None
87	    recent_topic_ids = [h["topic_id"] for h in history]
88	    wrong_counts: dict[str, int] = {}
89	    for h in history:
90	        if h.get("answered_at") and h.get("correct") == 0:
91	            tid = h["topic_id"]
92	            wrong_counts[tid] = wrong_counts.get(tid, 0) + 1
93	
94	    if req.topic_id:
95	        topic = _topic_from_cov(cov, req.topic_id)
96	        if not topic and req.topic_id in mastery:
97	            st = mastery[req.topic_id]["state"]
98	            topic = {"topic_id": st.topic_id, "topic_name": st.topic_name,
99	                     "coverage_level": None, "keywords": []}
100	    else:
101	        topic = select_topic(mastery, cov, recent_topic_ids, wrong_counts)
102	    if not topic:
103	        return JSONResponse(
… （共 85 行，此处省略 45 行，完整内容见 .jsonl）
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`（替换 376 → 391 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py (1 replacements).
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py`（替换 134 → 158 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/routes/quiz.py (1 replacements).
```

</details>

<details><summary>Qoder 思考</summary>

Also `last_q` is used later for question_type rotation ("short" if last_q["question_type"] == "choice") — fine, still defined.

Restart server. Kill background task and restart. The bg task is bbozpq7nj.

</details>

**Qoder：** 重启开发服务器再跑 6 题实测。

🔧 **TaskStop** ```json
{
 "task_id": "bbozpq7nj"
}
```

<details><summary>结果</summary>

```
{"message":"Successfully stopped task: bbozpq7nj (cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800)","task_id":"bbozpq7nj","task_type":"local_bash","command":"cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800"}
```

</details>

**指令：** <task-notification>
<task-id>bbozpq7nj</task-id>
<tool-use-id>call_16c81a8c5def4e02ba7124ee</tool-use-id>
<output-file>/var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-qoder/aa07df25-90a3-495e-bbaf-22c2ed429508/tasks/bbozpq7nj.output</output-file>
<status>killed</status>
<summary>Background command "Start dev server on 18800" was stopped</summary>
</task-notification>

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800
```

<details><summary>结果</summary>

```
Command running in background with ID: bdirxz8n8. Output is being written to: /var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-qoder/aa07df25-90a3-495e-bbaf-22c2ed429508/tasks/bdirxz8n8.output You will be notified when it completes. To check interim output, use Read on that file path.
```

</details>

🔧 **Bash** ```bash
sleep 8 && curl -s http://127.0.0.1:18800/api/health && app/.venv/bin/python .cache/scratch/s10b_six.py
```

<details><summary>结果</summary>

```
{"seekdb":{"ok":true},"embedding":{"ok":true,"model":"BAAI/bge-small-zh-v1.5 (512d)"},"powercontext":{"ok":true,"detail":"ok"}}learner: 10b验收同学011136
session: 89356cd0a37e4111
opening_line(应为空): None
blind_topics: [('t04', 'missing', 25.0), ('t08', 'thin', 8.41), ('t02', 'thin', 7.92), ('t01', 'missing', 5.0), ('t05', 'missing', 5.0)]
Q1: t04 函数依赖与范式（3NF、BCNF） | self | 2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15.0 分 | correct=False box=1->1
     题目: 4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。
Q2: t08 隔离级别与 MVCC | fill | 05-事务与并发控制.md · 第5章 事务与并发控制（课堂笔记） > 5.5 隔离级别（只记了个大概，课上讲得快） | correct=False box=1->1
     题目: 填空：SQL 标准定义了四个＿＿＿：读未提交、读已提交、可重复读、可串行化。（4 个字）
Q3: t02 SQL 查询与视图 | fill | 02-SQL速记.md · 第2章 SQL（速记，没整理完） > 基本查询 | correct=False box=1->1
     题目: 填空：- `＿＿＿ 列 FROM 表 WHERE 条件`，`DISTINCT` 去重。
Q4: t01 关系模型与关系代数 | self | 2025-2026-1-期末试卷A.pdf · 第1页 · 第1题 · 5.0 分 | correct=False box=1->1
     题目: 1.（5 分）设有关系学生 S(Sno, Sname, Dept)、选课 SC(Sno, Cno, Grade)。用关系
Q5: t05 查询处理与优化 | self | 2025-2026-1-期末试卷A.pdf · 第2页 · 第6题 · 5.0 分 | correct=False box=1->1
     题目: 6.（5 分）查询优化中为什么要尽早执行选择操作（"选择下推"）？结合查询树说明它如何减少中间结果的大小。
Q6: t04 函数依赖与范式（3NF、BCNF） | self | 2025-2026-1-期末试卷A.pdf · 第1页 · 第5题 · 10.0 分 | correct=False box=1->1
     题目: 5.（10 分）将上题的 R 分解为满足 BCNF 的关系模式集合，并判断你的分解是否无损连接、是否保持函数依赖。
     第6题完整原文: 5.（10 分）将上题的 R 分解为满足 BCNF 的关系模式集合，并判断你的分解是否无损连接、是否保持函数依赖。
end: 6 题 0 对
新会话开场白: 上次你在『函数依赖与范式（3NF、BCNF）』上错了 2 次，先复习它（往年考 25 分但笔记里没有）；『隔离级别与 MVCC』错了 1 次；『SQL 查询与视图』错了 1 次；『关系模型与关系代数』往年考 5 分但笔记里没有
  「函数依赖与范式」出现 1 次
  「隔离级别」出现 1 次
  「SQL 查询」出现 1 次
  「关系模型」出现 1 次
```

</details>

<details><summary>Qoder 思考</summary>

6-question test passes perfectly:
- Q1 t04 self (第4题) → Q2 t08 fill → Q3 t02 fill → Q4 t01 self → Q5 t05 self → Q6 t04 self (第5题 — rotated to question 5!)
- Source labels: "第1页 · 第4题 · 15.0 分" — hmm, "15.0 分" not "15 分". My `_chunk_source` uses `{chunk['points']:g}` which should give "15"... but it shows "15.0 分". Wait — points comes from DB as DECIMAL → float 15.0 → `:g` → "15". But output shows "15.0 分". Let me check: the source label in the payload... The output shows "2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15.0 分". Hmm, `f"{15.0:g}"` = "15". So why "15.0 分"?

Wait — maybe DB returns Decimal("15.0"), and `f"{Decimal('15.0'):g}"` → Decimal doesn't support `:g`? Actually Decimal supports format spec 'g'? Decimal.__format__ supports 'g'? Decimal supports format specs like 'f' and 'g'? Yes, Decimal supports 'g'. `format(Decimal('15.0'), 'g')` → '15.0'! Decimal keeps significant digits: Decimal('15.0') with 'g' gives '15.0' (6 significant digits → '15.0' preserved exponent). Right: Decimal formatting with g preserves the exponent. So need float conversion: `float(chunk['points']):g`.

Fix: in `_chunk_source`, convert points to float.

Also Q1 label lacks heading "第4题" duplication — good, label is "…第1页 · 第4题 · 15.0 分". With fix → "15 分".

Also note Q4 label: "第1页 · 第1题 · 5.0 分" → will become "5 分". Good.

Fix and restart server. Also re-run unit tests (test uses float 10.0 → ':g' → "10"... wait my unit test asserts label == "…第4题 · 15 分" with points 15.0 float → :g gives "15" ✓).

Also check test_missing_topic_uses_past_exam_question: heading None, label has "第4题（25 分）"? points=25.0 → :g → "25" → "第4题（25 分）" — test only checks "第4题" in label ✓.

Now also opening line: "『隔离级别与 MVCC』错了 1 次" — t08 is thin not missing, no blind note. Good. And t01: mentioned as blind only. Good, each topic once.

Q6 t04 rotated to question 5 ✓. Plan rotation t04→t08→t02→t01→t05 then back to t04 ✓.

Fix the points format.

</details>

**Qoder：** 6 题实测全部符合预期（t04→t08→t02→t01→t05→回到 t04 且自测题从第4题轮换到第5题；开场白每个知识点只出现一次）。但出处分值显示 “15.0 分”——DB 返回 Decimal，`Decimal('15.0'):g` 保留 "15.0"。修一下转 float。

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py`（替换 114 → 121 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/examradar/coach.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

<details><summary>Qoder 思考</summary>

Add a unit test for Decimal points to lock this in. Modify test_exam_source_label_no_duplicate_question_no to use Decimal.

</details>

**Qoder：** 加一条 Decimal 分值的单测，然后重启服务器复跑一次确认出处格式。

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py`（替换 978 → 1081 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app/tests/test_quizgen.py (1 replacements). The file state is current in your context; no need to read it back.
```

</details>

🔧 **TaskStop** ```json
{
 "task_id": "bdirxz8n8"
}
```

<details><summary>结果</summary>

```
{"message":"Successfully stopped task: bdirxz8n8 (cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800)","task_id":"bdirxz8n8","task_type":"local_bash","command":"cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800"}
```

</details>

**指令：** <task-notification>
<task-id>bdirxz8n8</task-id>
<tool-use-id>call_63106fad900248dd86f2e37c</tool-use-id>
<output-file>/var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-qoder/aa07df25-90a3-495e-bbaf-22c2ed429508/tasks/bdirxz8n8.output</output-file>
<status>killed</status>
<summary>Background command "Restart dev server on 18800" was stopped</summary>
</task-notification>

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800
```

<details><summary>结果</summary>

```
Command running in background with ID: b0ovi4cjx. Output is being written to: /var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-qoder/aa07df25-90a3-495e-bbaf-22c2ed429508/tasks/b0ovi4cjx.output You will be notified when it completes. To check interim output, use Read on that file path.
```

</details>

🔧 **Bash** ```bash
sleep 8 && app/.venv/bin/python .cache/scratch/s10b_six.py
```

<details><summary>结果</summary>

```
learner: 10b验收同学011227
session: 595f301509c94dad
opening_line(应为空): None
blind_topics: [('t04', 'missing', 25.0), ('t08', 'thin', 8.41), ('t02', 'thin', 7.92), ('t01', 'missing', 5.0), ('t05', 'missing', 5.0)]
Q1: t04 函数依赖与范式（3NF、BCNF） | self | 2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15 分 | correct=False box=1->1
     题目: 4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。
Q2: t08 隔离级别与 MVCC | fill | 05-事务与并发控制.md · 第5章 事务与并发控制（课堂笔记） > 5.5 隔离级别（只记了个大概，课上讲得快） | correct=False box=1->1
     题目: 填空：SQL 标准定义了四个＿＿＿：读未提交、读已提交、可重复读、可串行化。（4 个字）
Q3: t02 SQL 查询与视图 | fill | 02-SQL速记.md · 第2章 SQL（速记，没整理完） > 基本查询 | correct=False box=1->1
     题目: 填空：- `＿＿＿ 列 FROM 表 WHERE 条件`，`DISTINCT` 去重。
Q4: t01 关系模型与关系代数 | self | 2025-2026-1-期末试卷A.pdf · 第1页 · 第1题 · 5 分 | correct=False box=1->1
     题目: 1.（5 分）设有关系学生 S(Sno, Sname, Dept)、选课 SC(Sno, Cno, Grade)。用关系
Q5: t05 查询处理与优化 | self | 2025-2026-1-期末试卷A.pdf · 第2页 · 第6题 · 5 分 | correct=False box=1->1
     题目: 6.（5 分）查询优化中为什么要尽早执行选择操作（"选择下推"）？结合查询树说明它如何减少中间结果的大小。
Q6: t04 函数依赖与范式（3NF、BCNF） | self | 2025-2026-1-期末试卷A.pdf · 第1页 · 第5题 · 10 分 | correct=False box=1->1
     题目: 5.（10 分）将上题的 R 分解为满足 BCNF 的关系模式集合，并判断你的分解是否无损连接、是否保持函数依赖。
     第6题完整原文: 5.（10 分）将上题的 R 分解为满足 BCNF 的关系模式集合，并判断你的分解是否无损连接、是否保持函数依赖。
end: 6 题 0 对
新会话开场白: 上次你在『函数依赖与范式（3NF、BCNF）』上错了 2 次，先复习它（往年考 25 分但笔记里没有）；『查询处理与优化』错了 1 次（往年考 5 分但笔记里没有）；『SQL 查询与视图』错了 1 次；『关系模型与关系代数』往年考 5 分但笔记里没有
  「函数依赖与范式」出现 1 次
  「SQL 查询」出现 1 次
  「关系模型」出现 1 次
  「查询处理」出现 1 次
```

</details>

**Qoder：** 全部符合要求（出处“15 分”格式正确）。跑一遍完整单测确认 Decimal 修复没破坏其他，然后做浏览器验证。

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && uv run pytest -q
```

<details><summary>结果</summary>

```
........................................................................ [ 28%]
.............................ssssssssssssssssssssssssssss............... [ 57%]
........................................................................ [ 86%]
...................................                                      [100%]
223 passed, 28 skipped in 1.48s
```

</details>

🔧 **TaskUpdate** ```json
{
 "status": "completed",
 "taskId": "1"
}
```

🔧 **TaskUpdate** ```json
{
 "status": "completed",
 "taskId": "2"
}
```

🔧 **TaskUpdate** ```json
{
 "status": "completed",
 "taskId": "3"
}
```

🔧 **TaskUpdate** ```json
{
 "status": "completed",
 "taskId": "5"
}
```

<details><summary>结果</summary>

```
Updated task #1 status
```

</details>

<details><summary>结果</summary>

```
Updated task #5 status
```

</details>

<details><summary>结果</summary>

```
Updated task #2 status
```

</details>

🔧 **TaskUpdate** ```json
{
 "status": "in_progress",
 "taskId": "4"
}
```

<details><summary>结果</summary>

```
Updated task #4 status
```

</details>

<details><summary>结果</summary>

```
Updated task #3 status
```

</details>

<details><summary>Qoder 思考</summary>

Now browser verification: memory.html at 1440×900, ?source=auto, mastery table header & date cells single line height. Use .cache/scratch/pwvenv/bin/python, channel="chrome", screenshot to .cache/scratch/. The learner from the 6-question test has mastery cards (t04, t08, t02, t01, t05). Use that learner name. The last run's learner name is printed... I need it — the script printed it. Let me use the learner name from the last run. It printed "learner: 10b验收同学011227". I'll write a playwright script that fills the name, clicks 查看记忆, waits, screenshots, and checks row heights of the table cells.

Actually the script can also assert: measure the height of the th "盒号" and td date cells — compare element bounding box height vs line-height. Simpler: check each target cell's height ≤ 40px (single line ~ 22-24px) and assert its clientHeight equals height of a single text line? Just measure and screenshot, then Read the screenshot to visually verify. I'll record the heights to stdout too.

</details>

**Qoder：** 现在浏览器验证记忆页表格。写 Playwright 脚本（1440×900，`?source=auto`，用刚才 6 题实测的学习者）。

🔧 **Write** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_browser.py`（写入 1589 字符）

<details><summary>结果</summary>

```
File created successfully at: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_browser.py The file state is current in your context; no need to read it back.
```

</details>

🔧 **Bash** ```bash
.cache/scratch/pwvenv/bin/python .cache/scratch/s10b_browser.py
```

<details><summary>结果（出错）</summary>

```
Exit code 127
(eval):1: no such file or directory: .cache/scratch/pwvenv/bin/python
```

</details>

🔧 **Bash** ```bash
pwd && ls .cache/scratch/pwvenv/bin 2>/dev/null
```

<details><summary>结果（出错）</summary>

```
Exit code 1
/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app
```

</details>

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder && .cache/scratch/pwvenv/bin/python .cache/scratch/s10b_browser.py
```

<details><summary>结果</summary>

```
每行各单元格高度(px)：
  row0: [39, 39, 39, 39, 39, 39]
  row1: [71, 71, 71, 71, 71, 71]
  row2: [71, 71, 71, 71, 71, 71]
  row3: [71, 71, 71, 71, 71, 71]
  row4: [71, 71, 71, 71, 71, 71]
  row5: [71, 71, 71, 71, 71, 71]
单行文本高度基准: 25.59375px
screenshot: .cache/scratch/s10b-memory-1440.png 和 .cache/scratch/s10b-memory-table.png
JS errors: 无
```

</details>

<details><summary>Qoder 思考</summary>

Rows are 71px high — but that's the row height, dominated by the tallest cell (知识点 name might wrap, or the 轨迹 details/summary). The question is whether "盒号" / "对/错" header cells and date cells are single-line. Row height being uniform doesn't tell which cell wrapped. I need per-cell content height. Better: measure each target cell's text line count via client height of an inner span, or use element.scrollHeight vs line-height. Simplest robust check: create a range over the cell's text and count client rects — getClientRects() length on a Range equals number of line boxes.

Let me evaluate: for header cells (th index 1,2,3) and date td (index 3), count line boxes via range.getClientRects().length.

</details>

**Qoder：** 行高 71px 是被“知识点/轨迹”列撑起来的，需检查目标单元格本身是否单行。用 Range.getClientRects() 数行框。

🔧 **Write** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_lines.py`（写入 1206 字符）

<details><summary>结果</summary>

```
File created successfully at: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b_lines.py The file state is current in your context; no need to read it back.
```

</details>

🔧 **Bash** ```bash
.cache/scratch/pwvenv/bin/python .cache/scratch/s10b_lines.py
```

<details><summary>结果</summary>

```
['知识点', '盒号', '对/错', '下次复习', 'artifact', '轨迹'] [1, 1, 1, 1, 1, 1]
['t01 关系模型与关系代数', '1', '0/1', '2026-10-30', 'art_689b2c4e9a', '1 个 revision'] [1, 1, 1, 1, 4, 13]
['t02 SQL 查询与视图', '1', '0/1', '2026-10-30', 'art_48fa02e996', '1 个 revision'] [1, 1, 1, 1, 4, 13]
['t04 函数依赖与范式（3N', '1', '0/2', '2026-10-30', 'art_b1cbf00fa1', '2 个 revision'] [2, 1, 1, 1, 4, 27]
['t05 查询处理与优化', '1', '0/1', '2026-10-30', 'art_4710dd092c', '1 个 revision'] [1, 1, 1, 1, 4, 13]
['t08 隔离级别与 MVCC', '1', '0/1', '2026-10-30', 'art_6db0df8f18', '1 个 revision'] [1, 1, 1, 1, 4, 13]
盒号/对/错/下次复习列全部单行: True
```

</details>

**Qoder：** 表头和日期单元格全部单行。用 Read 看一遍截图确认。

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/.cache/scratch/s10b-memory-table.png`

<details><summary>结果</summary>

```
[image]
```

</details>

<details><summary>Qoder 思考</summary>

Screenshot confirms: headers 盒号/对/错/下次复习 all on single line, dates on single line. Task 4 done.

Now e2e: docker compose up -d --build for examradar-ci, then run scripts/e2e_verify.py --app-url http://127.0.0.1:18807. The e2e step_coach still depends on old question order? Let's check: session 1 in step_coach: Q1 auto → t04 (first question — still t04 ✓), answer 不会. Q2 explicit topic_id t04 → same topic, self-test rotation now gives question 5 (Q1 used 4). Hmm — session 10's e2e: Q2 = explicit t04, answered "会" (correct). With rotation, Q2 is now 第5题 instead of 第4题 — the check only asserts box 1→2 and revision increase, so still fine. Q3 auto with question_type=fill: order now t08 (first unasked thin/missing by blind desc) — matches. Also "prepare 召回" assertion on Q2 — fine.

The report body text: "3 题（t04 自测答错 → t04 自测答对 → t08 填空答错）" still accurate.

But wait — e2e CI stack: is the exam chunker change going to affect coverage checks? Should be same as dev. The e2e script re-imports in fresh stack — fine.

Also the CI stack imports docs fresh; e2e also asserts things about search — unchanged.

One consideration: step_coach Q2 explicit t04 — used_exam_nos=[4], so question 5. The assertion for Q2 doesn't check question number. OK.

Also check `docker-compose.yml` and `.env.ci` exist. Then run stack. The build may take a while. Let me do that.

</details>

**Qoder：** 任务 4 完成。现在起 examradar-ci 栈跑 e2e。

🔧 **TaskUpdate** ```json
{
 "status": "completed",
 "taskId": "4"
}
```

<details><summary>结果</summary>

```
Updated task #4 status
```

</details>

🔧 **TaskUpdate** ```json
{
 "status": "in_progress",
 "taskId": "6"
}
```

<details><summary>结果</summary>

```
Updated task #6 status
```

</details>

🔧 **Bash** ```bash
docker compose -p examradar-ci --env-file .env.ci down -v
```

<details><summary>结果</summary>

```
time="2026-10-29T01:13:54-04:00" level=warning msg="Warning: No resource found to remove for project \"examradar-ci\"."
```

</details>

🔧 **Bash** ```bash
docker compose -p examradar-ci --env-file .env.ci up -d --build
```

<details><summary>结果</summary>

```
Image examradar-ci-app Building 
 Image examradar-ci-powercontext Building 
#1 [internal] load local bake definitions
#1 reading from stdin 1.29kB done
#1 DONE 0.0s

#2 [app internal] load build definition from Dockerfile.app
#2 DONE 0.0s

#2 [app internal] load build definition from Dockerfile.app
#2 transferring dockerfile: 1.52kB done
#2 DONE 0.1s

#3 [powercontext internal] load build definition from Dockerfile.powercontext
#3 transferring dockerfile: 402B done
#3 DONE 0.1s

#4 [powercontext internal] load metadata for docker.io/library/python:3.12-slim
#4 ...

#5 [app internal] load metadata for ghcr.io/astral-sh/uv:0.8.15
#5 DONE 0.3s

#4 [powercontext internal] load metadata for docker.io/library/python:3.12-slim
#4 DONE 0.4s

#6 [powercontext internal] load .dockerignore
#6 transferring context: 2B done
#6 DONE 0.0s

#7 [app internal] load .dockerignore
#7 transferring context: 2B done
#7 DONE 0.0s

#8 [app internal] load build context
#8 transferring context: 78.98kB 0.0s done
#8 DONE 0.0s

#9 [powercontext 1/2] FROM docker.io/library/python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
#9 resolve docker.io/library/python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 0.1s done
… （共 136 行，此处省略 96 行，完整内容见 .jsonl）
```

</details>

🔧 **Bash** ```bash
docker compose -p examradar-ci --env-file .env.ci ps
```

<details><summary>结果</summary>

```
NAME                          IMAGE                                       COMMAND                  SERVICE        CREATED          STATUS                    PORTS
examradar-ci-app-1            examradar-ci-app                            "uv run --no-sync uv…"   app            57 seconds ago   Up 5 seconds (healthy)    127.0.0.1:18807->18800/tcp
examradar-ci-powercontext-1   examradar-ci-powercontext                   "powercontext server…"   powercontext   57 seconds ago   Up 57 seconds (healthy)   127.0.0.1:18806->8000/tcp
examradar-ci-seekdb-1         oceanbase/seekdb:1.4.0-100000172026082615   "/root/start.sh"         seekdb         57 seconds ago   Up 57 seconds (healthy)   127.0.0.1:18805->2881/tcp
```

</details>

🔧 **Bash** ```bash
python3 scripts/e2e_verify.py --app-url http://127.0.0.1:18807
```

<details><summary>结果</summary>

```
✅ 健康检查
✅ 导入样例资料
✅ 验收检索
✅ 覆盖雷达
✅ 复习教练
报告已写入 /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/docs/validation/e2e-report.md
```

</details>

🔧 **Bash** ```bash
grep -c "✅" docs/validation/e2e-report.md; grep -n "❌" docs/validation/e2e-report.md; tail -3 docs/validation/e2e-report.md
```

<details><summary>结果</summary>

```
66

- 【错题】t04 函数依赖与范式（3NF、BCNF）：题目「4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。 （1）求 R 的所有候选码；（2）求属性集闭包 (A) +；（3）判断 R 最高属于第几范式，说明理由。」
```

</details>

🔧 **Bash** ```bash
grep -n "总结\|全部通过\|66 项" docs/validation/e2e-report.md | tail -3; grep -n "出处：2025\|出处：" docs/validation/e2e-report.md | head -5
```

<details><summary>结果</summary>

```
19:**总结：全部通过 ✅**
7:- 期望值出处：samples/course-db/README.md（设计真值）、dev-records/prompts/02-m1-ingest-search.md（验收检索表）
85:- ✅ 第一条出处：03-索引与B+树.md · 第3章 索引：B+树与哈希索引（课堂笔记） > 3.3 B+树的查找、插入与删除
97:- ✅ 第一条出处：第7讲-故障恢复.pdf · 第7页 · ARIES 恢复算法的三个阶段
109:- ✅ 第一条出处：第7讲-故障恢复.pdf · 第4页 · 先写日志原则（WAL）
121:- ✅ 第一条出处：two-phase-commit-primer.pdf · 第2页 · 5. Handling Failures
```

</details>

<details><summary>Qoder 思考</summary>

e2e 全绿（66 项检查全部 ✅，总结"全部通过"）。注意 e2e 的 step_coach 没有依赖旧出题顺序——检查通过无需改动。

Now, wait — the report has 66 ✅ and no ❌. Also verify that e2e report has the coach step question source with new label. Check quickly the coach section's "出处：" line.

</details>

**Qoder：** e2e 全绿（66 项检查全部 ✅）。看下报告里教练步骤的出处格式确认新格式生效。

🔧 **Bash** ```bash
grep -n "第4题\|第5题\|15 分" docs/validation/e2e-report.md | head -10
```

<details><summary>结果</summary>

```
145:- ✅ 第一条出处：2025-2026-1-期末试卷A.pdf · 第4题(15分) · 第4题
149:| 1 | 2025-2026-1-期末试卷A.pdf · 第4题(15分) · 第4题 | 3.8539 | 0.8506 | 0.0328 |
150:| 2 | 2025-2026-1-期末试卷A.pdf · 第5题(10分) · 第5题 | 2.8515 | 0.7828 | 0.032 |
193:- Q4（15 分）→ t04，依据考点词：函数依赖、范式
211:| 第 1 题自动选题 = 盲区第一 t04，missing 走往年原题自测 | ✅ | topic=t04，题型=self，出处=2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15 分 |
213:| context/prepare 召回上次答错的错题（「你之前在这里错过」材料） | ✅ | 召回 1 条，第一条：【错题】t04 函数依赖与范式（3NF、BCNF）：题目「4.（15 分）设关系模式 R(A, B, |
234:4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。 （1）求 R 的所有候选码；（2）求属性集闭包 (A) +；（3）判断 R 最高属于第几范式，说明理由。
237:- 出处：2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15 分
273:- 【错题】t04 函数依赖与范式（3NF、BCNF）：题目「4.（15 分）设关系模式 R(A, B, C, D, E)，函数依赖集 F = { A→B, B→C, AD→E }。 （1）求 R 的所有候选码；（2）求属性集闭包 (A) +；（3）判断 R 最高属于第几范式，说明理由。」
```

</details>

<details><summary>Qoder 思考</summary>

Coach step source label is now "第4题 · 15 分" — good (line 145/149/150 are the search step's exam-chunk source labels, which use a different format from seekdb/search — that's the search API, not the coach; fine, not in scope).

Now remaining acceptance items:
1. ✅ uv run pytest (223 passed)
2. ✅ integration 34 passed
3. ✅ new unit tests
4. ✅ 6-question dev test (recorded)
5. ✅ browser verification
6. ✅ e2e full green + report written
7. Tear down CI stack: docker compose down -v
8. Stop dev server
9. Append DEVLOG session 10b section
10. git status check

Also rerun pytest once more? Already done after final code change (Decimal fix) — yes, 223 passed after that. Integration tests were run before the Decimal fix and quiz.py rename fix... wait, integration tests ran BEFORE the history/session_qs rename fix? Let me check the timeline:

1. Code changes (coach.py, mastery.py, chunker.py, learning_store.py, quiz.py, memory.html)
2. Unit tests: 223 passed ✓ (this was after all main edits including quiz.py changes)
3. Integration: 34 passed ✓ — this ran BEFORE the bug fix (history→session_qs rename) and before Decimal fix.

The Decimal fix and the session_qs rename happened after integration run. Unit tests were re-run after (223 passed). But integration tests weren't re-run after the rename fix. The rename fix affects quiz_next route — integration tests may cover it (test_m3_integration). Must re-run integration to be safe. Also should re-run unit + integration at the end as final acceptance. Let me re-run both.

Note the CI stack is running; dev server is running. Integration tests use examradar_test database on dev seekdb (10800), not CI stack. Fine.

Also — one issue: the e2e report at docs/validation/e2e-report.md is regenerated; report line 145 etc show old search format "第4题(15分) · 第4题" — that's the search API's source label format (from seekdb.py get_documents or search label building), which duplicates "第4题" too! Look at line 145: "2025-2026-1-期末试卷A.pdf · 第4题(15分) · 第4题". Hmm — this is the 检索 (search) step's source display, also showing 题号 twice. Was that in the task scope? The task says "出处里题号写了两遍：自测题的出处是..." — specifically about the self-test question source. The search result source label duplication is a different code path (search.py / seekdb label). The user's issue #2 was specifically about the self-test question. But the search output also shows "第4题(15分) · 第4题" — that's presumably heading + question_no label from search route. Hmm, should I fix that too? The task says only the self-test question source. E2e passed regardless (it was passing before with this format). Out of scope — don't fix; keep focus. Actually wait — let me check whether this duplication existed before my change... The search label comes from routes/search.py label building, untouched by me. It was like that in session 10's report too presumably. Out of scope.

Now re-run tests, then teardown, then DEVLOG.

</details>

**Qoder：** 集成测试是在 quiz.py 最后的改名修复和 Decimal 修复之前跑的，重新跑一遍两组测试作为最终验收。

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && uv run pytest -q
```

<details><summary>结果</summary>

```
........................................................................ [ 28%]
.............................ssssssssssssssssssssssssssss............... [ 57%]
........................................................................ [ 86%]
...................................                                      [100%]
223 passed, 28 skipped in 1.06s
```

</details>

🔧 **Bash** ```bash
export EXAMRADAR_IT=1 && uv run pytest -q -m integration
```

<details><summary>结果</summary>

```
..................................                                       [100%]
34 passed, 217 deselected in 2.78s
```

</details>

<details><summary>Qoder 思考</summary>

All green. Now tear down CI stack and stop dev server, then write DEVLOG.

</details>

**Qoder：** 全部通过。收尾：关掉 CI 栈和开发服务器。

🔧 **Bash** ```bash
cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder && docker compose -p examradar-ci --env-file .env.ci down -v
```

<details><summary>结果</summary>

```
Container examradar-ci-app-1 Stopping 
 Container examradar-ci-app-1 Stopped 
 Container examradar-ci-app-1 Removing 
 Container examradar-ci-app-1 Removed 
 Container examradar-ci-seekdb-1 Stopping 
 Container examradar-ci-powercontext-1 Stopping 
 Container examradar-ci-powercontext-1 Stopped 
 Container examradar-ci-powercontext-1 Removing 
 Container examradar-ci-powercontext-1 Removed 
 Container examradar-ci-seekdb-1 Stopped 
 Container examradar-ci-seekdb-1 Removing 
 Container examradar-ci-seekdb-1 Removed 
 Volume examradar-ci_pc-data Removing 
 Volume examradar-ci_seekdb-data Removing 
 Network examradar-ci_default Removing 
 Volume examradar-ci_seekdb-data Removed 
 Volume examradar-ci_pc-data Removed 
 Network examradar-ci_default Removed
```

</details>

🔧 **TaskStop** ```json
{
 "task_id": "b0ovi4cjx"
}
```

<details><summary>结果</summary>

```
{"message":"Successfully stopped task: b0ovi4cjx (cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800)","task_id":"b0ovi4cjx","task_type":"local_bash","command":"cd /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800"}
```

</details>

**指令：** <task-notification>
<task-id>b0ovi4cjx</task-id>
<tool-use-id>call_97d5b55b624d40c59dbb5bcb</tool-use-id>
<output-file>/var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-qoder/aa07df25-90a3-495e-bbaf-22c2ed429508/tasks/b0ovi4cjx.output</output-file>
<status>killed</status>
<summary>Background command "Restart dev server on 18800" was stopped</summary>
</task-notification>

🔧 **Bash** ```bash
docker compose -p examradar-ci --env-file .env.ci ps; curl -s -m 3 http://127.0.0.1:18800/api/health; git -C /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder status --short
```

<details><summary>结果（出错）</summary>

```
Error: Allow Bash to run: docker compose -p examradar-ci --env-file .env.ci ps; curl -s -m 3 http://127.0.0.1:18800/api/health; git -C /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder status --short?
```

</details>

🔧 **Bash** ```bash
docker compose -p examradar-ci --env-file .env.ci ps
```

<details><summary>结果</summary>

```
NAME      IMAGE     COMMAND   SERVICE   CREATED   STATUS    PORTS
```

</details>

🔧 **Bash** ```bash
git status --short
```

<details><summary>结果</summary>

```
M app/examradar/chunker.py
 M app/examradar/coach.py
 M app/examradar/learning_store.py
 M app/examradar/mastery.py
 M app/examradar/routes/quiz.py
 M app/static/memory.html
 M app/tests/test_chunker.py
 M app/tests/test_mastery.py
 M app/tests/test_quizgen.py
 M docs/validation/e2e-report.md
?? dev-records/sessions/10b-coach-polish.jsonl
?? dev-records/sessions/10b-coach-polish.started
?? dev-records/sessions/10b-coach-polish.stderr
```

</details>

**Qoder：** CI 栈已清空、dev-records/sessions 未改动。最后写 DEVLOG 会话 10b 一节。

🔧 **Bash** ```bash
tail -5 docs/DEVLOG.md
```

<details><summary>结果</summary>

```
### E. 留给后续

- `docs/images/` 的 coach.png / memory.png 截图文件本身待补（本会话截图在 `.cache/scratch/`，不入库；README 截图表已按文件名引用，补齐即生效）。
- LLM 出题/判分路径（choice/short 题型、LLM 判分、误区分析）在有 `LLM_BASE_URL` 的环境下未实测，本会话验证的是无模型规则路径 + 自评路径。
```

</details>

🔧 **Bash** ```bash
wc -l docs/DEVLOG.md
```

<details><summary>结果</summary>

```
1071 docs/DEVLOG.md
```

</details>

🔧 **Bash** ```bash
cat >> docs/DEVLOG.md << 'DEVEOF'

---

## 会话 10b — 修复复习教练与我的记忆页的五个问题（2026-10-29）

**参与者**：产品负责人（任务输入）、Qoder（修复与验证）
**模型**：GLM-5.3。开发栈（seekdb 10800 / PowerContext 18801）全程未动；本会话只用 18800（开发服务器）与 18805–18807（examradar-ci 栈）。

### A. 做了什么

1. **出题顺序（`coach.select_topic` / `routes/quiz.py` / `learning_store.py`）**
   - `select_topic` 签名从 `last_topic_id` 改为 `(recent_topic_ids, wrong_counts)`：本会话最近 2 题出过的知识点跳过（同一知识点至少隔 2 道别的题）；计划池（thin/missing 按盲区分）先各出一遍，再回到本会话答错的（答错次数降序、同次数按盲区分），最后才重复其余；到期复习同样受"隔 2 题"约束。
   - quiz/next 读 `learning_store.session_questions()`（新增，按 created_at 升序全量取本会话题目）拿出题历史；`last_question_of_session` 保留（answer 路由未用，无其他调用方依赖）。
   - **自测题轮换**：`make_self_test_question(topic, course_id, used_question_nos)` 按已出次数升序、同次数按题号选往年原题——t04 第 4 题出过，下次出第 5 题。
   - **填空挖空轮换**：`make_fill_question(…, used_terms)` 优先换一个没挖过的术语，都挖过了才重复第一个。
   - `learning_store`：quiz_questions 建表改 `DATETIME(3)` 并对旧表幂等 MODIFY——连续两题落在同一秒时秒级 DATETIME 排不出先后，轮换逻辑会读错历史。
2. **出处题号去重 + 分值格式（`coach._chunk_source`）**：试卷块 heading 本身是"第N题"时不再重复追加题号，只补"15 分"（`float(points):g`——DB DECIMAL 读回是 Decimal，直接 `:g` 会输出 "15.0 分"）；非试卷块保持"第N题（15 分）"。
3. **开场白去重（`mastery.build_opening_line`）**：按 topic_id 记录已提过的知识点，既错了又是盲区的合成一句——"上次你在『函数依赖与范式（3NF、BCNF）』上错了 2 次，先复习它（往年考 25 分但笔记里没有）"；"今天到期"同样可并盲区括注。
4. **记忆页表格不折行（`static/memory.html`）**："盒号""对/错""下次复习"三列的表头和单元格加 `white-space:nowrap`，1440px 下不再折成两行。
5. **切题去掉大题标题（`chunker.py`）**：新增 `_strip_trailing_section_titles`——大题标题行（"一、/二、…"开头且带"共 N 分"）不再留在上一题原文末尾（第 5 题曾带上"三、查询处理与事务（共 50 分）"）。
6. **开发库重导试卷 + 重跑分析**（脚本 `.cache/scratch/s10b_reimport.py`）：删旧试卷文档（11 块）→ 重导（11 块）→ analyze run_id 10。第 4/5 题原文各自干净；10 个判定、11 道题归属全部仍与设计真值一致（t04/t01/t05 missing，t02/t08 thin，其余 covered；第 5 题→t04 10 分）；盲区池顺序 t04(25) > t08(8.41) > t02(7.92) > t01(5) > t05(5)。
7. **e2e 脚本**：复习教练步骤的既有序列（t04→t04 指定→t08 填空）与新出题顺序天然兼容，零改动全绿。

### B. 新增单测（10 条，`test_quizgen.py` / `test_mastery.py` / `test_chunker.py`）

- 出题顺序：`test_plan_topics_rotate_once_before_repeats`（计划池先轮一遍再回到答错的）、`test_returns_to_most_wrong_topic`、`test_same_topic_keeps_two_question_gap`（10 连选题，任何题的知识点不出现在前两题里）、`test_due_within_two_questions_skipped`；
- 自测题轮换：`test_self_test_rotates_between_past_exam_questions`（第4题→第5题→回到第4题）；
- 出处：`test_exam_source_label_no_duplicate_question_no`（含 Decimal 分值）；
- 开场白：`test_opening_line_topic_mentioned_once`、`test_opening_line_due_and_blind_merged`；
- 填空轮换：`test_fill_rotates_blank_when_term_used`；
- 切题：`test_trailing_section_title_not_in_question_content`。

### C. 开发库 6 题实测（学习者 `10b验收同学011227`，全部答错/自评"不会"）

| # | 知识点 | 题型 | 出处 |
| --- | --- | --- | --- |
| 1 | t04 函数依赖与范式（3NF、BCNF） | 自测（第4题） | 2025-2026-1-期末试卷A.pdf · 第1页 · 第4题 · 15 分 |
| 2 | t08 隔离级别与 MVCC | 填空 | 05-事务与并发控制.md · 第5章 … > 5.5 隔离级别（只记了个大概，课上讲得快） |
| 3 | t02 SQL 查询与视图 | 填空 | 02-SQL速记.md · 第2章 SQL（速记，没整理完） > 基本查询 |
| 4 | t01 关系模型与关系代数 | 自测（第1题） | 2025-2026-1-期末试卷A.pdf · 第1页 · 第1题 · 5 分 |
| 5 | t05 查询处理与优化 | 自测（第6题） | 2025-2026-1-期末试卷A.pdf · 第2页 · 第6题 · 5 分 |
| 6 | t04 函数依赖与范式（3NF、BCNF） | 自测（第5题） | 2025-2026-1-期末试卷A.pdf · 第1页 · 第5题 · 10 分 |

计划池 5 个知识点先轮一遍（t04→t08→t02→t01→t05），第 6 题回到答错次数最多的 t04 且自测题从第 4 题轮换到第 5 题；结束会话（6 题 0 对）后新会话开场白："上次你在『函数依赖与范式（3NF、BCNF）』上错了 2 次，先复习它（往年考 25 分但笔记里没有）；『查询处理与优化』错了 1 次（往年考 5 分但笔记里没有）；『SQL 查询与视图』错了 1 次；『关系模型与关系代数』往年考 5 分但笔记里没有"——每个知识点只出现一次。

### D. 遇到的问题和解决办法

1. **quiz_next 变量遮蔽 bug（本次实测发现）**：选题历史与 prepare 召回的错题都叫 `history`，第二个赋值把题目历史覆盖了，第 4 题起 500（`KeyError: 'topic_id'`）。改名为 `session_qs` 后修复。
2. **DB DECIMAL 读回 Decimal**：`f"{points:g}"` 对 Decimal 输出 "15.0"，与要求 "15 分" 不符——先 `float()` 再 `:g`，并补 Decimal 用例的单测。
3. **秒级 DATETIME 排不出同秒两题的先后**：6 题实测里连续请求常落在同一秒，`created_at` 秒级精度导致"最近 2 题"计算错位——建表/幂等迁移改 `DATETIME(3)`（毫秒）。
4. **表格"单行高"的验证方法**：行高被"知识点/artifact/轨迹"列撑到 71px，不能只看单元格高度——用 `Range.getClientRects().length` 逐单元格数行框，"盒号/对/错/下次复习"四列全部 1 行（截图 `.cache/scratch/s10b-memory-table.png` 已人工核对）。

### E. 验收结果

| 验收项 | 结果 |
| --- | --- |
| `uv run pytest`（单测） | ✅ 223 passed, 28 skipped（基线 213 + 新增 10） |
| `export EXAMRADAR_IT=1 && uv run pytest -m integration` | ✅ 34 passed |
| 新增单测（出题顺序 / 自测轮换 / 开场白） | ✅ 见 B 节 10 条，全部通过 |
| 开发库重导试卷 + 重跑分析 | ✅ 10 个判定、11 道归属仍与设计真值一致；第 5 题原文不再带大题标题 |
| 新学习者 6 题（全错/不会）实测 | ✅ 见 C 节表格；顺序、原题轮换、出处格式、开场白全部符合要求 |
| 浏览器验证（1440×900，`?source=auto`） | ✅ 掌握度卡片表表头与日期单元格全部单行（Range 行框数全为 1）；截图 `.cache/scratch/s10b-memory-1440.png`、`s10b-memory-table.png`，Read 复核过 |
| e2e | ✅ `docker compose -p examradar-ci --env-file .env.ci up -d --build` 后 `python3 scripts/e2e_verify.py --app-url http://127.0.0.1:18807` 5 步 66 项检查全 ✅，报告写入 `docs/validation/e2e-report.md`；复习教练步骤与新出题顺序兼容，脚本零改动 |
| 会话结束清理 | ✅ examradar-ci `down -v`（容器/网络/两卷全删，`ps` 为空）；18800 开发服务器已停；`git status` 只有本会话改动 + harness 会话产物（`dev-records/sessions/10b-*`，未改动） |
DEVEOF
echo done
```

<details><summary>结果（出错）</summary>

```
Error: Allow writing to /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/docs/DEVLOG.md?
```

</details>

🔧 **Read** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/docs/DEVLOG.md`

<details><summary>结果</summary>

```
1063	3. **e2e 导出类型坑（自查）**：`ctx.app.request` 返回已解析的 list 而非 str，`isinstance(export, str)` 分支会漏判；改为 `export if isinstance(export, str) else json.dumps(...)`。
1064	4. **docker-compose 空串透传**：`${LLM_BASE_URL:-}` 未配置时容器里是空串而非 None；核对 `llm.py` 的 `configured = bool(base_url and model)`，空串安全，保留透传。
1065	5. **浏览器脚本两次竞态**：点"下一题"/开始会话后未等新题目渲染就点旧题按钮（自评按钮与"开始学习会话"都含"会"字，`has-text('会')` 还会匹配错按钮）。改为 `text-is` 精确匹配 + `wait_for_function` 等待 `currentQuestion.question_id` 变化后操作，11/11 通过。
1066	6. **权限系统约束**（沿用会话 08b 经验）：shell cwd 持久化坑（`cd` 一律绝对路径）；重定向/管道被拒（验证写 `.cache/scratch/` Python 脚本执行，git 已忽略）；`rm` 不可用（临时文件留在 scratch，不清理仓库）。
1067	
1068	### E. 留给后续
1069	
1070	- `docs/images/` 的 coach.png / memory.png 截图文件本身待补（本会话截图在 `.cache/scratch/`，不入库；README 截图表已按文件名引用，补齐即生效）。
1071	- LLM 出题/判分路径（choice/short 题型、LLM 判分、误区分析）在有 `LLM_BASE_URL` 的环境下未实测，本会话验证的是无模型规则路径 + 自评路径。
1072
```

</details>

🔧 **Edit** `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/docs/DEVLOG.md`（替换 209 → 4782 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder/qoder/docs/DEVLOG.md (1 replacements).
```

</details>

🔧 **TaskUpdate** ```json
{
 "status": "completed",
 "taskId": "6"
}
```

<details><summary>结果</summary>

```
Updated task #6 status
```

</details>

<details><summary>Qoder 思考</summary>

All done. Summarize briefly.

</details>

**Qoder：** 会话 10b 完成。五个问题全部修复并逐项验收通过：

**代码改动**
- `coach.py`：`select_topic` 改为基于本会话出题历史（同一知识点至少隔 2 题、计划池先轮一遍再回到答错的）；`make_self_test_question`/`make_fill_question` 支持在多道原题/多个挖空点间轮换；`_chunk_source` 题号去重、分值写“15 分”
- `mastery.py`：开场白同一知识点合成一句
- `chunker.py`：切题去掉末尾大题标题（第5题不再带“三、查询处理与事务”）
- `learning_store.py`：新增 `session_questions`，`created_at` 升到毫秒精度（同秒两题排序问题）
- `memory.html`：盒号/对/错/下次复习列 `nowrap`

**验收结果**
- 单测 223 passed（新增 10 条：出题顺序×4、自测轮换、出处格式、开场白×2、填空轮换、切题）；集成测试 34 passed
- 开发库删旧试卷重导 + 重跑分析：10 判定、11 归属与设计真值一致，第5题原文干净
- 6 题实测（全部答错）：t04→t08→t02→t01→t05→回到 t04 且自测从第4题换到第5题，已记入 DEVLOG
- 浏览器 1440×900 验证：目标列全部单行（Range 行框数=1，截图已复核）
- e2e 5 步 66 项全 ✅（脚本零改动，新出题顺序天然兼容），报告已写入 `docs/validation/e2e-report.md`
- CI 栈 `down -v`、18800 开发服务器已停，DEVLOG 已追加会话 10b 一节

过程中额外发现并修复两个 bug：quiz_next 变量遮蔽（选题历史被 prepare 召回结果覆盖导致 500）、DB Decimal 分值格式输出 "15.0"。

## 会话结果

会话 10b 完成。五个问题全部修复并逐项验收通过：

**代码改动**
- `coach.py`：`select_topic` 改为基于本会话出题历史（同一知识点至少隔 2 题、计划池先轮一遍再回到答错的）；`make_self_test_question`/`make_fill_question` 支持在多道原题/多个挖空点间轮换；`_chunk_source` 题号去重、分值写“15 分”
- `mastery.py`：开场白同一知识点合成一句
- `chunker.py`：切题去掉末尾大题标题（第5题不再带“三、查询处理与事务”）
- `learning_store.py`：新增 `session_questions`，`created_at` 升到毫秒精度（同秒两题排序问题）
- `memory.html`：盒号/对/错/下次复习列 `nowrap`

**验收结果**
- 单测 223 passed（新增 10 条：出题顺序×4、自测轮换、出处格式、开场白×2、填空轮换、切题）；集成测试 34 passed
- 开发库删旧试卷重导 + 重跑分析：10 判定、11 归属与设计真值一致，第5题原文干净
- 6 题实测（全部答错）：t04→t08→t02→t01→t05→回到 t04 且自测从第4题换到第5题，已记入 DEVLOG
- 浏览器 1440×900 验证：目标列全部单行（Range 行框数=1，截图已复核）
- e2e 5 步 66 项全 ✅（脚本零改动，新出题顺序天然兼容），报告已写入 `docs/validation/e2e-report.md`
- CI 栈 `down -v`、18800 开发服务器已停，DEVLOG 已追加会话 10b 一节

过程中额外发现并修复两个 bug：quiz_next 变量遮蔽（选题历史被 prepare 召回结果覆盖导致 500）、DB Decimal 分值格式输出 "15.0"。

