会话 10：把 M3 合并进来，接上导航和使用记录，补全端到端验证和文档。

背景：
- 会话 07 在另一份目录里做完了 M3：复习教练、学习者记忆、学习会话。它用的还是 M2 版本的覆盖引擎。
- 与此同时：
  - 会话 05 修好了覆盖判定和试题归属；
  - 会话 06 做了 Docker 部署；
  - 会话 08a 写了验证脚本 `scripts/e2e_verify.py`，复习教练一步留给本会话；
  - 会话 08b 写了 README、VALIDATION 和 `.env.example`，M3 的部分用 `<!-- 会话 10：… -->` 标出来留给本会话。
- 现在的状态：上面这些分支我都已经合并进 `eco-qoder` 并提交了（会话 05b 也在里面：两个覆盖接口都按盲区分数排序，雷达标签和判定理由也改好了）。合并 M3 时只有 `docs/DEVLOG.md` 冲突，已经按会话顺序拼好；`config.py`、`static/index.html`、`static/ask.html` 是 git 自动合并的。合并后 `cd app && uv run pytest` 是 205 passed / 28 skipped；集成测试（`export EXAMRADAR_IT=1 && uv run pytest -m integration`）是 34 passed。

先读 `docs/DEVLOG.md` 里会话 05–08b 的记录。环境同前：seekdb 127.0.0.1:10800，PowerContext 127.0.0.1:18801，密码在 `qoder/.env`；不要启停开发用的容器。本机 Ollama 同会话 07。

## 审阅说明

### 会话 05、05b 之后覆盖结果的格式（复习教练读覆盖结果要照这个改）

- `coverage.get_latest(course_id)` 返回 `run_id`、`course_id`、`created_at`、`config`、`topics`、`items`。`items` 已经按 `blind_spot_score` 从高到低排好（会话 05b）。
- `items` 每一项的字段：
  - `topic_id`、`topic_name`；
  - `coverage_level`（missing / thin / covered）、`coverage_score`（0–1）；
  - `support_chunks`、`support_chars`；
  - `terms`：每个考点词的 `term`、`aliases`、`found`，以及 `chunks`（`doc`、`page`、`heading`）；
  - `best_evidence`：missing 时为 null；
  - `exam_weight`；
  - `exam_questions`：`question_no`、`points`、`similarity`、`matched_terms`、`content`；
  - `blind_spot_score`、`reason`。
- 会话 07 的 DEVLOG 列了教练用到的旧字段（M2 版）。对不上的都要改，字段映射只放在一个函数里。

### 导航和 auto 模式

- 会话 05 的 `static/js/source.js`：URL 带 `?source=auto` 时写进 sessionStorage，并给导航链接补上这个参数。
- `coach.html`、`memory.html` 引入同一个脚本。
- 导航顺序：首页、导入资料、问笔记、覆盖雷达、复习教练、我的记忆、使用记录。

### 使用记录

- `routes/usage.py` 的 `compute_usage_stats` 现在按事件间隔估算学习时长（会话 05），改成按学习会话算。

### Docker

- `docker/Dockerfile.app` 复制的是整个 `app/examradar/` 和 `app/static/`，M3 的新模块会自动带上。
- M3 新增的配置项（大模型、PowerContext 超时等）在 `docker-compose.yml` 的 app 服务里按需透传。
- examradar-ci 栈里不配大模型，所以 e2e 的复习教练一步走无模型的路径：填空题，以及 missing 知识点的往年原题自测。

### 端口

- 本会话只用 18800（开发服务器）和 18805–18807（examradar-ci）。
- 会话 07 用过 18802 和 18804，已经结束，不要再用。

### 审阅会话 07 时看到的问题（本会话要处理）

- **出题的原文必须属于这个知识点**：会话 07 验收时（还是 M2 的覆盖引擎）t04 出了一道填空题，挖空是"GROUP"，原文来自 SQL 笔记，和函数依赖、范式无关。现在：
  - missing 的知识点（t01、t04、t05）走"往年原题自测"，不出填空题；
  - thin / covered 的知识点只从找到考点词的段落里出题（`terms[].chunks` 指向的段落，或 `best_evidence`），挖空优先挖考点词本身。
  - 用 t04（missing，往年原题 Q4、Q5 共 25 分）和 t08（thin，证据只有"5.5 隔离级别"一段）各走一遍，把题目原文贴进 DEVLOG。
- **`docs/DEPLOY.md` 和会话 05 的现状不一致**（会话 08b 的 DEVLOG"发现的问题"里有）：旧的阈值变量名，还有一句草稿里的疑问句。照现在的 `config.py` 改。
- **favicon**：每个页面都有一个 favicon 的 404，顺手消掉（例如每页加一个内联的空图标），浏览器控制台要干净。
- **截图文件名**：`docs/images/README.md` 里 M3 的两张截图用 `coach.png` 和 `memory.png`（截图由我来补），不要用 `quiz.png`。

## 本会话任务

1. **合并收尾**：没有剩下的冲突，但要检查自动合并的结果：
   - `config.py`、`static/index.html`、`static/ask.html` 里会话 05 和会话 07 的改动都在，没有重复或者顺序错乱（例如 `index.html` 的快捷入口、`ask.html` 引入的 `source.js` 和大模型回答）；
   - 会话 07 的代码是在会话 04 的版本上写的。查一下有没有用到会话 05 删掉或改名的东西，例如 `effective_database`、旧的覆盖字段。
2. **M3 接上会话 05 的覆盖结果**：
   - 教练读覆盖结果的那个函数，对照现在 `coverage.get_latest()` 的字段改好。会话 07 的 DEVLOG 写了它用到哪些字段。
   - missing 知识点"给往年原题自测"这条路径，在样例上实际走一遍：现在 t04 是 missing。
3. **导航**：所有页面（包括 `coach.html`、`memory.html`）用同一套导航，`?source=auto` 在页面之间保持，沿用会话 05 的做法。
4. **使用记录接上学习会话**：
   - 使用记录页的"累计学习时长"改为按学习会话计算：会话开始 / 结束事件；30 分钟没有事件视为结束，按最后一个事件计时。
   - 使用记录和导出里不出现学习者名字。
5. **`.env.example`**：补上 M3 的配置项（大模型、PowerContext 超时等），带注释。
6. **验证脚本**：在 `scripts/e2e_verify.py` 的步骤表里加上复习教练一步（会话 08a 留好了接口）。
   - 流程：新学习者开始会话（bootstrap 为空）→ 出题 → 答错 → 答对 → 结束 → 开始新会话，开场白提到上次答错的知识点。
   - 学习者名字每次运行都用新的（例如带上时间），保证"bootstrap 为空"成立。
   - 列出这一路对 PowerContext 的每次读写：接口、artifact id、revision、标签。
   - 列出掌握度卡片的 revision 历史，以及 `context/prepare` 召回到的错题。
7. **README 和 VALIDATION**：补上会话 08b 用 `<!-- 会话 10：… -->` 标出的 M3 部分：接口、命令、PowerContext 的核对方法、代码位置。补完删掉这些标记。VALIDATION 里新加的 curl 命令都对开发服务器实际跑一遍。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- `cd app && uv run pytest` 和 `cd app && export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过。
- 6 条验收检索、10 个知识点的判定、11 道题的归属仍与设计真值一致（集成测试里有）。
- 先 `down -v`，再 `docker compose -p examradar-ci --env-file .env.ci up -d --build` 从零启动，三个服务都 healthy。
- `scripts/e2e_verify.py --app-url http://127.0.0.1:18807` 全部 ✅，包括复习教练一步；报告写入 `docs/validation/e2e-report.md`。
- 浏览器验证（页面都带 `?source=auto`）：
  - 从首页开始一次学习会话；
  - 在复习教练页做两道题，其中一道答错；
  - 在我的记忆页看到掌握度卡片的 revision 变化；
  - 点导航进入使用记录页，仍是 auto 模式，累计学习时长里有这次会话。

  截图，并在 DEVLOG 里写看到了什么。
- 使用记录导出里没有学习者名字。
- 会话结束前 `down -v` 清掉 examradar-ci，关掉你启动的进程。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。
- **开发服务器**：Bash 设为后台运行（run_in_background），命令是 `cd app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800`，末尾不要加 `&`。用 `curl -s http://127.0.0.1:18800/api/health` 确认它起来了；结束时用 PID 结束它。
- docker 命令只能这样写：`docker compose -p examradar-ci --env-file .env.ci <子命令>`，子命令为 `up -d --build`、`ps`、`logs <服务>`、`down -v`。
- **浏览器验证**：`.cache/scratch/pwvenv` 里已经装好 playwright，用本机 Chrome（`channel="chrome"`），脚本用 `.cache/scratch/pwvenv/bin/python` 运行。截图存到 `.cache/scratch/`，用 Read 查看。
- 临时脚本放在 `qoder/.cache/scratch/`（已被 git 忽略），`rm` 不在允许的命令里。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip，用 uv。

结束前在 `docs/DEVLOG.md` 追加本会话记录：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。不要修改 `dev-records/` 和 `samples/`。
