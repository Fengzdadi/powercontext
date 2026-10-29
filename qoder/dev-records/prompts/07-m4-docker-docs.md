会话 06（里程碑 M4）：Docker 一键部署 + 端到端验证样例 + README。

先读 `docs/DEVLOG.md` 了解当前状态。开发用的 seekdb（127.0.0.1:10800）和 PowerContext（127.0.0.1:18801）照常在跑，不要动它们。

{{REVIEW}}

## 本会话任务

1. **compose 修好并实际跑通**（评审会照 README 从零执行 `docker compose up -d --build`）：
   - powercontext 镜像（python:3.12-slim）里没有 curl，现在的健康检查永远失败，app 也就永远起不来。用镜像里有的 python 做健康检查（`urllib.request` 请求 `/health/ready`）。
   - 端口只绑 `127.0.0.1`（PowerContext 没有鉴权，不能暴露到局域网）。
   - PowerContext 用自己的嵌入式 seekdb，不依赖 seekdb 服务：去掉它对 seekdb 的 `depends_on`，在 compose 注释里写清楚。
   - `ghcr.io/astral-sh/uv` 固定到具体版本；去掉 `uv sync --frozen ... || uv sync ...` 这种回退（会掩盖锁文件不一致）。
   - **镜像构建时预下载向量模型**（BRIEF 的要求：运行时不联网）。构建参数支持 `HF_ENDPOINT`（国内网络可以设成 `https://hf-mirror.com`），README 里说明。
   - 本机是 Apple Silicon（arm64）。确认 seekdb、PowerContext（嵌入式 seekdb 的 wheel）和 app 镜像在 arm64 和 amd64 上都能构建运行；如果某个只有 amd64，写清楚并在 compose 里指定 `platform`。
2. **你自己验证 compose**：为了不和开发容器冲突，用单独的项目名和端口：
   - 新建 `qoder/.env.ci`（已被 .gitignore 忽略），内容是 `SEEKDB_PASSWORD` 换一个随机值，`SEEKDB_HOST_PORT=18805`、`POWERCONTEXT_HOST_PORT=18806`、`APP_PORT=18807`；
   - 只用这种写法：`docker compose -p examradar-ci --env-file .env.ci <子命令>`（`up -d --build`、`ps`、`logs <服务>`、`down -v`）。别的 docker 命令不会被允许；
   - 跑通后用 `down -v` 清掉，会话结束时不要留下 examradar-ci 的容器和卷。
3. **导入脚本走 HTTP**：`scripts/load_sample.sh` 改成通过 `POST /api/documents` 导入（`APP_URL` 默认 `http://127.0.0.1:18800`），这样本地开发和 Docker 部署用同一个脚本。脚本打印每份资料的块数，重复运行不重复入库。
4. **端到端验证脚本** `scripts/e2e_verify.py`（只用标准库或 app 已有的依赖；请求都带 `X-ExamRadar-Source: auto`）。按验证样例逐步执行，并把每一步写进一份 Markdown 报告 `docs/validation/e2e-report.md`：
   - 导入样例资料（块数，试卷 11 题合计 100 分）；
   - 6 条检索：检索 JSON、`GET_SQL` 给出的实际 SQL、前 3 条结果的出处和两路分数，和期望出处对照；
   - 覆盖雷达：10 个知识点的判定和证据分数、11 道题的归属，和设计真值对照，盲区第一名；
   - 复习教练：新学习者开始会话（bootstrap 为空）→ 出题 → 答错 → 答对 → 结束 → 新会话的开场白提到上次答错的知识点；列出这一路对 PowerContext 的每次读写（接口、artifact id、revision、标签），以及掌握度卡片的 revision 历史和 `context/prepare` 召回到的错题；
   - 每一步标 ✅ / ❌，最后一行给出总结。脚本退出码：全部通过为 0，否则为 1。
   - 支持 `--app-url`，对本地开发和 Docker 部署都能跑；对 examradar-ci 跑一次，把报告提交进仓库。
5. **README.md**（中文，放在 `qoder/README.md`，给评审看的，要能照着从零跑起来）：
   - 一句话介绍、解决的问题、核心功能、界面截图位置（截图我来补，先留 `docs/images/` 路径）；
   - 版本表：Python、uv、seekdb 镜像 tag、PowerContext 版本、向量模型、ECharts、主要 Python 依赖；
   - 架构图（Mermaid）和 **seekdb / PowerContext 的分工**：各自存什么、在哪个功能里起作用、对应的代码位置；
   - 部署方式 A：`docker compose` 一键启动（复制 `.env.example` → `.env`，改密码，`up -d --build`，等健康检查，导入样例）；
   - 部署方式 B：本地开发（`docker-compose.dev.yml` 起 seekdb + PowerContext，`uv run` 起 app）；
   - 配置项表（每个环境变量的含义和默认值；可选的大模型配置）；
   - **验证样例**：链接到 `docs/VALIDATION.md`；
   - 常见问题（模型下载慢、端口占用、Apple Silicon、PowerContext 启动慢）；
   - 许可证（代码 Apache-2.0，样例资料 CC BY 4.0）和第三方组件来源。
6. **`docs/VALIDATION.md`**：给人手动执行的验证样例：初始数据（`samples/course-db/` 的每份文件）、输入、操作步骤（界面操作和对应的 curl / CLI 命令各一份）、每一步的预期结果，以及怎么核对 seekdb 的查询（`python -m examradar.cli sql ...` 或 `GET_SQL` 输出）和 PowerContext 的记忆读写（具体接口和返回字段）。最后一节说明 `scripts/e2e_verify.py` 能把这些一次跑完。
7. **`qoder/LICENSE`**：Apache-2.0 全文。

## 验收标准

- `docker compose -p examradar-ci --env-file .env.ci up -d --build` 从零起来，三个服务都 healthy；`scripts/e2e_verify.py --app-url http://127.0.0.1:18807` 全部 ✅，报告已写入 `docs/validation/e2e-report.md`。
- `uv run pytest` 和 `export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过。
- README 里的每条命令你都实际跑过（写在 DEVLOG 里）。
- 会话结束前 `down -v` 清掉 examradar-ci，关掉你启动的进程。

结束前在 `docs/DEVLOG.md` 追加本会话记录。不要修改 `dev-records/` 和 `samples/`。
