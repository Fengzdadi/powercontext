会话 08a（里程碑 M4 第二部分之一）：端到端验证脚本。

先读 `docs/DEVLOG.md`：
- 会话 05 修好了覆盖判定和试题归属；
- 会话 06 修好了 Docker 部署，写了 `docs/DEPLOY.md`；
- 复习教练和学习者记忆（M3）由会话 07 在另一份目录里同时开发。完成后由会话 10 合并进来，并把"复习教练"一步加进本脚本。

## 本会话和别的会话同时进行

- 会话 07 在另一份目录里改应用代码；会话 08b 在另一份目录里写 README、VALIDATION 和 `.env.example`。之后由产品负责人合并。
- **只改这些文件**：`scripts/e2e_verify.py`、期望值数据文件（如果单独放）、`docs/validation/`，以及在 `docs/DEVLOG.md` 末尾追加本会话记录。
- **不要改 `app/` 下的任何文件**。验证中发现应用的 bug，写进 DEVLOG 的"发现的问题"一节，写清楚复现步骤，不要自己改。
- 端口：只用 examradar-ci 的 18805–18807。开发栈（10800、18801）和 18800、18802、18804、18808、18809 都是别的会话在用。

## 会话 05、06 之后的现状（写脚本时以这里和代码为准）

- **接口**
  - 健康：应用的 `GET /api/health` 返回 `seekdb`、`embedding`、`powercontext` 三项。PowerContext 自己的 `/health/ready` 在 examradar-ci 栈里是 18806 端口。
  - 导入：`POST /api/documents`，调用方式照 `scripts/load_sample.sh`（会话 06 改成了走 HTTP）。列出资料用 `GET /api/documents?course_id=...`。
  - 检索：`POST /api/search`，JSON 字段是 `query`、`course_id`、`doc_kinds`、`top_k`、`include_exam`。返回里有检索 JSON 和 `GET_SQL` 给出的实际 SQL，见 `routes/search.py`。
  - 覆盖：`POST /api/coverage/analyze`（JSON：`course_id`、`syllabus_text`，考试范围用 `samples/course-db/syllabus.txt`）和 `GET /api/coverage/latest?course_id=...`。
    - 顶层 `config` 里是阈值。
    - `items` 每一项有：`topic_id`、`coverage_level`、`coverage_score`、`support_chunks`、`support_chars`、`terms`（每个考点词的 `found` 和 `chunks`，`chunks` 里有 `doc`、`page`、`heading`）、`exam_questions`（`question_no`、`points`、`matched_terms`）、`blind_spot_score`、`reason`。
- **6 条验收检索**：期望出处见 `dev-records/prompts/02-m1-ingest-search.md` 的验收表（可以读，不要改）。
  - 前 5 条用默认范围（不传 `doc_kinds`，即笔记、课件、阅读材料），最后一条加 `include_exam: true`。
  - `app/tests/test_integration.py` 里的 `ACCEPTANCE_QUERIES` 把每条检索限定到一种资料，比验收标准宽松，不要照搬。
  - 我在开发库上用默认范围跑过，6 条的第一条都对，`keyword_score` 都不为空。
- **设计真值**：在 `samples/course-db/README.md` 的表里：10 个判定，每道题对应的知识点和分值，盲区第一是 t04（25 分）。
  - README 没写各份资料的块数，以第一次导入的实际结果为准，核对重复导入后不变；
  - 试卷 11 题，合计 100 分。
- **会话 05b 同时在修 `get_latest()` 的排序**：
  - `analyze` 的返回已经按 `blind_spot_score` 从高到低排；`latest` 现在按 `topic_id` 排，05b 修好以后两者一致。
  - 脚本对两个接口分别核对：第一名是 t04，整体顺序按盲区分数从高到低。
  - 你这份目录里的代码不含 05b 的修复，所以"`latest` 的顺序"这一项会是 ❌。照实写进报告和 DEVLOG，原因写"会话 05b 修复中"。不要改 `app/`，也不要为这一项反复重跑。
  - 判定理由的措辞 05b 也在改，所以脚本只核对理由的结构（提到了哪些考点词、有没有支撑字数），不要比对原文。
- **会话 10 要在步骤表里加"复习教练"一步**，按步骤组织的接口要留好。

## 任务

写 `scripts/e2e_verify.py`：只用标准库，请求都带 `X-ExamRadar-Source: auto`。脚本按验证样例逐步执行，把每一步写进 Markdown 报告 `docs/validation/e2e-report.md`。

- **按步骤组织**：每步一个函数，再用一张步骤表串起来。会话 10 会在表里加"复习教练"一步，所以接口要留好：每步返回通过与否和要写进报告的内容。
- **步骤**：
  - 健康检查：应用的 `/api/health`，以及 PowerContext 的 `/health/ready`。
  - 导入样例资料：各份资料的块数；试卷 11 题，合计 100 分；重复导入不产生新块。
  - 6 条检索：检索 JSON、`GET_SQL` 给出的实际 SQL、前 3 条结果的出处和两路分数，并和期望出处对照。
  - 覆盖雷达：10 个知识点的判定、每个考点词的证据、11 道题的归属，和设计真值对照；盲区第一名。
- **期望值**以 `samples/course-db/README.md` 为准。集中放在一处（脚本开头的常量表，或单独的数据文件），注明出自哪一节，不要散在代码里。
- 每一步标 ✅ / ❌，最后一行给出总结。退出码：全部通过为 0，否则为 1。
- 支持 `--app-url` 参数，本地开发和 Docker 部署都能跑。连不上时给出清楚的错误信息，不要抛 Python 堆栈。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- 先 `down -v`，再 `docker compose -p examradar-ci --env-file .env.ci up -d --build` 从零启动，三个服务都 healthy。
- `python3 scripts/e2e_verify.py --app-url http://127.0.0.1:18807` 全部 ✅，报告写入 `docs/validation/e2e-report.md`。
- 再跑一次，结果不变（导入是幂等的）。
- 对一个没有服务在监听的地址运行（`--app-url http://127.0.0.1:18803`，这个端口按约定一直空着），脚本给出清楚的错误并以 1 退出。
- 会话结束前 `down -v` 清掉 examradar-ci，关掉你启动的进程。
- `git status` 里只有上面允许改的文件。
- 除"`latest` 的顺序"一项（见上面会话 05b 的说明）以外全部 ✅。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- docker 命令只能这样写：`docker compose -p examradar-ci --env-file .env.ci <子命令>`，子命令为 `up -d --build`、`ps`、`logs <服务>`、`down -v`。`.env.ci` 已经建好。镜像构建可能要几分钟，用 Bash 的后台运行方式执行 `up -d --build`，再用 `ps` 和 `logs` 查看进度。
- 脚本只用标准库，用 `python3 scripts/e2e_verify.py` 运行。如果要跑 `uv`，一律在 `qoder/app/` 下运行。
- 临时脚本放在 `qoder/.cache/scratch/`（已被 git 忽略），`rm` 不在允许的命令里。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip。

结束前在 `docs/DEVLOG.md` 追加本会话记录：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。不要修改 `dev-records/` 和 `samples/`。
