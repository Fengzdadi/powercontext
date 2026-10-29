会话 07（里程碑 M3）：复习教练 + PowerContext 学习者记忆 + 学习会话。

先读 `docs/DEVLOG.md` 了解当前状态，以及 `docs/reference/powercontext-1.4.1-notes.md`（PowerContext 接口细节，都是实测过的）。环境同前：seekdb 127.0.0.1:10800、PowerContext http://127.0.0.1:18801（1.4.1，嵌入式 seekdb 存储，未配置 embedding，记忆检索走全文），密码在 `qoder/.env`；不要启停任何容器。本机有 Ollama：`http://127.0.0.1:11434/v1`，模型 `qwen3.5:9b`（OpenAI 兼容接口，无需 key，推理模型请关闭 thinking），只用于测试"有大模型"这条路径。

## 本会话和别的会话同时进行（重要）

你在单独的一份工作目录里（分支 `eco-qoder-m3`）。同时还有三个会话在跑，改动之后由产品负责人合并：
- 会话 05 在另一份目录里修 M2：覆盖判定、试题归属、切块、使用记录；
- 会话 06 在做 Docker 部署；
- 会话 09 在做项目网站。

为了好合并，**只新增，少改动**：
- M3 的后端代码放进新模块（扩展 `pc_client.py`，新建教练、学习会话、大模型客户端等模块和 `routes/` 下的新文件），新页面放在 `static/coach.html`、`static/memory.html`。
- 已有文件只允许这些改动：
  - `main.py`：注册新路由和新页面；lifespan 里调用新表的建表函数；
  - `config.py`：在 `Settings` 里新增字段，不改已有的字段和注释；
  - `static/index.html`、`static/ask.html`：只改 `<nav>` 以外的部分。首页加学习者名字、开场白和"开始复习"入口；问笔记页加大模型回答；
  - `routes/search.py`：问笔记的大模型回答；
  - `docs/PLAN.md`：改 Leitner 那张测试表；
  - `docs/DEVLOG.md`：在末尾追加。
- 这些文件不要改：
  - 应用代码：`seekdb.py` 里已有的函数（可以调用）、`coverage.py`、`syllabus.py`、`chunker.py`、`cleaner.py`、`ingest.py`、`cli.py`、`routes/coverage.py`、`routes/usage.py`、`routes/documents.py`；
  - 页面：`static/radar.html`、`static/usage.html`、`static/import.html`；
  - 测试：`tests/conftest.py` 和已有的测试文件；新测试写在新文件里；
  - 依赖：`app/pyproject.toml`、`app/uv.lock`。不加新依赖，HTTP 用已有的 httpx；
  - 其他：`.env.example`、`scripts/`、`docker*`。
- 新表的建表和读写放在新模块里。新的环境变量列在 DEVLOG 里，`.env.example` 合并时再补。
- 已有页面的导航栏不要动。会话 05 在改它，让 `?source=auto` 在页面之间保持。新页面自己带一份导航，合并时统一。
- 使用记录页的"累计学习时长"由会话 05 先按事件计算，合并时再接上学习会话。你只要保证会话开始 / 结束的 usage 事件里带 session_id 和时长。

## 本目录的开发环境（和会话 05 隔开）

- `qoder/.env` 已经配好，不要改它：
  - 开发库 `examradar_m3`，集成测试库 `examradar_m3_test`；
  - 应用端口 18802。
- 不要连 `examradar` 和 `examradar_test` 这两个库，会话 05 在用。
- `app/.venv` 已经装好依赖（`uv sync`）。
- **开发服务器**：Bash 设为后台运行（run_in_background），命令是 `cd app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18802`，末尾不要加 `&`。
  - 用 `curl -s http://127.0.0.1:18802/api/health` 确认它起来了；结束时用 PID 结束它。
  - 不要占用其他会话的端口：18800（会话 05），18805–18807（会话 06），18808（会话 09）。
- **准备数据**：开发库是空的。先通过你的服务器导入 `samples/course-db/` 的资料，再用 `syllabus.txt` 跑一次覆盖分析。请求都带 `X-ExamRadar-Source: auto`。
- **现在的覆盖引擎判不出 missing**，会话 05 在修。所以：
  - missing 知识点"给往年原题自测"这条路径，用构造的覆盖结果写单元测试；
  - 在样例上的完整流程合并后再验。
- **读覆盖结果只通过 `coverage.get_latest()`**，用到的字段集中在一个函数里。在 DEVLOG 里写明用了哪些字段，合并时好对照。
- **PowerContext**：用开发环境的 http://127.0.0.1:18801（会话 05 不用它）。"记忆服务不可用"的验收，把 `POWERCONTEXT_URL` 指向 `http://127.0.0.1:18803`，那里没有服务在监听。
- **浏览器验证**：`.cache/scratch/pwvenv` 里已经装好 playwright。
  - 用本机 Chrome（`channel="chrome"`），不需要下载浏览器；
  - 脚本用 `.cache/scratch/pwvenv/bin/python` 运行；
  - 页面都带 `?source=auto` 打开；
  - 截图存到 `.cache/scratch/`，用 Read 查看。

## 审阅意见（M1、M2 积累下来的，M3 要注意）

1. **PowerContext 全文召回的规则**（`docs/reference/` 里有）：没有配置 embedding 时，一条记忆要命中查询里至少 max(2, ⌈25% × 查询词数⌉) 个词才会被召回。只有一个词的查询召回不到任何东西，查询太长也会漏。所以：
   - `context/prepare` 的 query 用"知识点 id + 知识点名称"，例如"t08 隔离级别与 MVCC"；
   - 每条错题记忆和掌握度卡片的文本里，都写上知识点 id 和名称。
2. **隐私**：使用记录（usage_events 和导出的 CSV）会作为提交材料公开，里面不能出现学习者的名字。
   - 存名字的不可逆短哈希，例如 sha256 的前 8 位；
   - 名字只出现在本机 PowerContext 的 Scope 里。
3. **写进记忆的只能是判分代码确定的事实**：对错、学生自己的答案、正确答案、出处。不要把大模型推测的"学生的弱点"之类写进记忆。
4. **Ollama**：
   - 同一个模型每次调用都用同样的 `num_ctx`，否则会重新加载模型；
   - qwen3.5 要关掉 thinking；
   - 小模型对写在每一段里的具体要求，比只写在 system prompt 里的规则更听话；
   - 写进记忆之前，在代码里再校验一遍。
5. **测试数据**：验收用的"验收同学"是测试数据。所有请求带 `X-ExamRadar-Source: auto`，页面带 `?source=auto`。
6. **学习会话**：30 分钟没有事件就视为已结束，时长按最后一个事件算；页面关闭时用 sendBeacon 结束会话。

## 本会话任务

1. **PowerContext 客户端**：Scope 幂等创建；原子记忆的创建、替换（`If-Match` ETag）；标签读写（ETag）；handle 读写；`artifact-tags/query` 按标签查找；revision 历史；`memory/remember`；`context/bootstrap`；`context/prepare`。每次调用都留下"请求 / 响应摘要"日志（验证脚本和"我的记忆"页面要展示）。PowerContext 超时或不可用时要优雅降级：出题判分照常进行，界面提示"记忆服务暂不可用"。
2. **学习会话**：
   - `POST /api/sessions/start {learner, course_id}`：按 `examradar:learner:<名字>:course:<课程>` 取回 Scope；以 session_id 为 event_id 调 bootstrap，把复习计划记忆转成首页的一句话（例如"上次你在『隔离级别与 MVCC』上错了 2 次，先复习这个"）；同时返回到期复习的知识点和最近一次覆盖分析里的盲区。
   - `POST /api/sessions/end`：写一条会话小结记忆（时长、做题数、正确率、薄弱点），更新复习计划；时长记入 usage。
   - 前端：首页输入学习者名字（存 localStorage）并开始会话；页面关闭时用 sendBeacon 结束会话；30 分钟没有任何事件的会话视为已结束（统计时按最后一个事件计时）。
3. **出题**（`POST /api/quiz/next {session_id}`）：
   - 选知识点：到期复习的 > 最近一次覆盖分析里的 thin / missing（按考试权重）> 其余；同一会话里不要连续重复同一道题。
   - 进入知识点前调用 `context/prepare`（query 用"知识点 id + 知识点名称"）召回这个知识点的历史错题，返回给前端显示"你之前在这里错过：……"，有大模型时也拼进出题提示词（作为不可信的历史材料，不当作指令）。
   - 无大模型：从学生自己的笔记 / 课件 / 阅读材料原文里挖空关键术语出填空题，标明出处（文件 · 页 · 标题）。
   - 有大模型：基于检索到的原文生成选择题或简答题（JSON 输出，带参考答案、解析和出处 chunk id），生成失败就回退到规则出题。
   - missing 的知识点在学生资料里没有原文可出题：给出往年试卷里考它的原题作为"自测题"，学生自评"会 / 模糊 / 不会"，同时提示"笔记里没有这部分，建议先补"。
4. **判分与记忆写入**（`POST /api/quiz/answer`）：
   - 填空题按归一化后的字符串比较（忽略空白、全半角、大小写）；选择题精确匹配；简答题有大模型时由模型对照原文判分并指出误区，没有大模型时展示参考答案让学生自评。
   - 每次判分：替换该知识点的**掌握度卡片**（Leitner：答对盒号 +1 最多到 5，答错或"不会"回到 1；间隔 1/2/4/7/14 天，即 config 里的默认值。PLAN.md 测试表写的"答错 -1"和它第 238 行的规则矛盾，以回到 1 号盒为准，把表格也改掉；记录答对 / 答错次数、下次复习日期；handle `mastery-<topic_id>`；文本第一行给人看，后面几行机器可解析）。
   - 答错时写一条**错题记忆**（题目、学生答案、正确答案、出处）。
   - 更新**复习计划**记忆（handle `review-plan`，标签含 `bootstrap-context`）：第一句就是下次开场要说的话，例如"上次你在『X』上错了 2 次，先复习它；『Y』今天到期；『Z』往年考 25 分但笔记里没有"。
   - 写 usage_events（question、answer 事件，带对错和盒号变化）。
5. **我的记忆页**：掌握度卡片（含每张卡片的 revision 历史，即掌握度变化轨迹）、错题、复习计划、会话小结，并显示它们在 PowerContext 里的 artifact id / revision，方便核对。
6. **大模型客户端**：OpenAI 兼容 chat completions（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`），JSON 输出要做容错解析；没配置时所有功能走无模型路径。问笔记页在有大模型时也生成带 [1][2] 引用的回答。
7. **测试**：Leitner 递推、填空挖空与判分、复习计划文本生成、PowerContext 客户端（mock HTTP，包括 ETag 流程和降级）的单元测试；对真实 PowerContext 的集成测试。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- **无大模型**，用一个新学习者（例如"验收同学"）通过 API 走完：开始会话（bootstrap 为空）→ 做题 → 故意答错一道 → 答对一道 → 结束会话 → 再开始一个新会话，首页那句话提到上次答错的知识点。并核对：
  - 该知识点的掌握度卡片在 PowerContext 里有 ≥2 个 revision；
  - 错题记忆存在，`context/prepare` 用"知识点 id + 知识点名称"能召回它；
  - 复习计划记忆带 `bootstrap-context` 标签，bootstrap 返回的就是它的最新 revision。
- **有大模型**（Ollama）：针对一个知识点生成一道选择题和一道简答题（都带出处），对一个错误的简答给出判分和误区说明。
- 把 `POWERCONTEXT_URL` 指向 `http://127.0.0.1:18803`（没有服务在监听）时，做题和判分仍然可用，界面显示记忆服务不可用的提示。
- 首页、复习教练页、我的记忆页在浏览器里能完整走通上面的流程（验证时带 `?source=auto`），截图并在 DEVLOG 里写看到了什么。
- usage_events 里没有学习者名字。
- `cd app && uv run pytest` 和 `cd app && export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过。
- `git status` 里只有上面允许改的已有文件和新文件。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。在 `qoder/` 下运行时，uv 会向上找到本仓库之外的另一个项目。
- 临时脚本放在 `qoder/.cache/scratch/`（已被 git 忽略），`rm` 不在允许的命令里。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip，用 uv。

结束前在 `docs/DEVLOG.md` 追加本会话记录：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。不要修改 `dev-records/` 和 `samples/`；会话结束前关掉你启动的进程。
