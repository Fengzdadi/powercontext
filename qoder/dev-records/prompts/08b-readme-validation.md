会话 08b（里程碑 M4 第二部分之二）：README、验证样例文档、配置说明。

先读：
- `docs/DEVLOG.md`（会话 01–06）：会话 05 修好了覆盖判定和试题归属，会话 06 修好了 Docker 部署；
- `docs/PLAN.md`、`docs/DEPLOY.md`、`samples/course-db/README.md`；
- `app/examradar/config.py`、`.env.example`。

开发用的 seekdb（127.0.0.1:10800）和 PowerContext（127.0.0.1:18801）照常在跑，不要动它们。

## 本会话和别的会话同时进行

- 会话 07 在另一份目录里做 M3（复习教练、学习者记忆）；会话 08a 在另一份目录里写端到端验证脚本 `scripts/e2e_verify.py`，报告在 `docs/validation/e2e-report.md`。之后会话 10 合并 M3，补上文档里 M3 的部分。
- **只改这些文件**：`README.md`、`docs/VALIDATION.md`、`.env.example`、`docs/images/README.md`（列出要放的截图文件名，截图由我来补），以及在 `docs/DEVLOG.md` 末尾追加本会话记录。`docs/DEPLOY.md` 保留，README 以它为基础并链接它。
- 不要改 `app/`、`scripts/`、`docker*`。发现应用或部署文件的问题，写进 DEVLOG 的"发现的问题"一节，不要自己改。
- README 和 VALIDATION 里 M3 的部分（复习教练、学习者记忆、PowerContext 读写的核对）先只按 PLAN.md 写"做什么"，不写接口和命令。要补的地方用 `<!-- 会话 10：… -->` 标出来。
- **不要运行 `cp .env.example .env`**：`qoder/.env` 是开发环境的配置，覆盖它会断开开发库。要核对 `.env.example`，用 diff 或读文件。
- 端口：开发服务器用 18800。不要用 18802（会话 07）、18805–18807（会话 08a）、18808（会话 09）。

## 会话 05、06 之后的现状（写文档时以这里和代码为准）

- **覆盖判定**（会话 05）：看考点词是否出现在材料里，再看支撑正文的字数。
  - 阈值是 `COVERAGE_TERM_RATIO_COVERED`(0.5)、`COVERAGE_SUPPORT_CHARS`(280)、`COVERAGE_MIN_BODY_CHARS`(50)；
  - 语义分只用来给证据排序，不参与判定；
  - `docs/PLAN.md` 里早期的"0.6×语义 + 0.4×关键词"公式已经不用了。README 介绍功能时按 DEVLOG 会话 05 写。
- **覆盖接口**：`POST /api/coverage/analyze`（JSON：`course_id`、`syllabus_text`），`GET /api/coverage/latest?course_id=...`。`items` 每一项有：
  - `topic_id`、`topic_name`、`coverage_level`、`coverage_score`；
  - `support_chunks`、`support_chars`、`terms`（每个考点词的 `found`、`chunks`、`aliases`）、`best_evidence`；
  - `exam_weight`、`exam_questions`（`question_no`、`points`、`similarity`、`matched_terms`、`content`）；
  - `blind_spot_score`、`reason`。
- **会话 05b 同时在改**：`get_latest()` 的盲区排序（现在按 `topic_id` 排，改完按盲区分数从高到低）和判定理由的措辞。所以 VALIDATION 的预期结果这样写：
  - 盲区第一名按 `blind_spot_score` 最大来写（t04，25 分，覆盖度 0），不要依赖 `items` 的先后顺序；
  - 判定理由写"应该包含什么"：找到和没找到的考点词及出处、支撑段数和字数、离阈值的距离。不要整段照抄理由原文。
- **其他接口和命令**：
  - 导入：`POST /api/documents`，调用方式见 `scripts/load_sample.sh`。它走 HTTP，用 `APP_URL` 指定地址，本地和 Docker 通用。
  - 检索：`POST /api/search`，返回里有检索 JSON 和 `GET_SQL` 给出的实际 SQL，见 `routes/search.py`。
  - CLI：`python -m examradar.cli import|sql|delete-course`。`delete-course` 默认保留使用记录，加 `--include-usage` 才删。
- **使用记录**：
  - 带请求头 `X-ExamRadar-Source: auto` 的请求、页面地址带 `?source=auto` 时的操作，都记为 auto，不算真实使用；
  - 使用记录页按浏览器时区分天；导出的 CSV 带 BOM。
- **Docker**（会话 06、06b）：
  - 以 `docs/DEPLOY.md` 为准；
  - 镜像构建参数是 `HF_ENDPOINT`、`EMBEDDING_MODEL`；
  - `examradar-ci` 那套栈（18805–18807）归会话 08a 用，本会话不要启动 Docker。
- **第三方组件**：在 `app/static/lib/`（ECharts、marked），版本以文件头为准。`LICENSE` 是 Apache-2.0 官方原文。
- **设计真值和 6 条验收检索**：在 `samples/course-db/README.md`。

## 任务

1. **README.md**：中文，放在 `qoder/README.md`。这是给评审看的，要能照着从零跑起来。
   - 一句话介绍、解决的问题、核心功能、界面截图（先留 `docs/images/` 下的路径）；
   - 版本表：Python、uv、seekdb 镜像 tag、PowerContext 版本、向量模型、ECharts、主要 Python 依赖；
   - 架构图（Mermaid），以及 **seekdb 和 PowerContext 的分工**：各自存什么、在哪个功能里起作用、对应的代码位置；
   - 部署方式 A（Docker 一键启动）和部署方式 B（本地开发），以 `docs/DEPLOY.md` 为基础；
   - 配置项表：每个环境变量的含义和默认值，包括可选的大模型配置；
   - **验证样例**：链接到 `docs/VALIDATION.md` 和 `scripts/e2e_verify.py`；
   - 常见问题；
   - 许可证：代码 Apache-2.0，样例资料 CC BY 4.0。另列第三方组件的来源、版本和许可证（ECharts、marked 等）。
2. **`docs/VALIDATION.md`**：给人手动执行的验证样例。
   - 初始数据：`samples/course-db/` 的每份文件；
   - 输入；
   - 操作步骤：界面操作和对应的 curl / CLI 命令各一份；
   - 每一步的预期结果；
   - 怎么核对 seekdb 的查询（`python -m examradar.cli sql ...` 或 `GET_SQL` 的输出）；
   - 怎么核对 PowerContext 的记忆读写（M3 部分先留标记）；
   - 最后一节说明 `python3 scripts/e2e_verify.py --app-url <地址>` 能把这些一次跑完，报告写在 `docs/validation/e2e-report.md`。
3. **`.env.example`**：每个变量都带注释，和 `config.py` 的字段、DEPLOY.md 的变量表一一对应。只放占位值，不放任何真实密码或密钥。M3 新增的配置项由会话 10 补。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- README 里的命令，本会话能跑的都实际跑过，写进 DEVLOG：
  - 部署方式 B 的应用部分（`cd app && uv sync`，起开发服务器）；
  - CLI 和 curl 命令。
- 不能跑的写明原因：
  - 部署方式 A 的 Docker 命令由会话 08a 在 examradar-ci 上验证；
  - 开发栈已经在跑，起开发栈那一步不重跑。
- VALIDATION 里的每个 curl / CLI 命令都对开发服务器（18800）实际跑过，预期结果与实际输出一致，输出贴进 DEVLOG。请求都带 `X-ExamRadar-Source: auto`。
- 版本表里的每个版本号都和仓库里的实际版本一致：`app/uv.lock`、compose 镜像 tag、Dockerfile、ECharts 文件头。在 DEVLOG 里列出每个版本号的出处。
- `.env.example` 和 `config.py` 的字段一一对应，DEVLOG 里列对照表。
- 文档里不出现任何真实密码或密钥。
- 会话结束前关掉你启动的进程。`git status` 里只有上面允许改的文件。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。
- **开发服务器**：Bash 设为后台运行（run_in_background），命令是 `cd app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800`，末尾不要加 `&`。用 `curl -s http://127.0.0.1:18800/api/health` 确认它起来了；结束时用 PID 结束它。README 里给评审的写法可以是 `uv run uvicorn ...`，也要实际跑一次。
- 临时脚本放在 `qoder/.cache/scratch/`（已被 git 忽略），`rm` 不在允许的命令里。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip，用 uv。

结束前在 `docs/DEVLOG.md` 追加本会话记录：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。不要修改 `dev-records/` 和 `samples/`。
