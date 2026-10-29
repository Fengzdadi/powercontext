会话 06（里程碑 M4 第一部分）：Docker 一键部署。

**本会话和会话 05 同时进行**。你在单独的一份工作目录里工作，会话 05 在另一份目录里改应用代码，两边的改动之后由产品负责人合并。所以：

- 本会话**不要改 `app/` 下的任何文件**，只动部署相关的文件：`docker/`、`docker-compose*.yml`、`.env.example` 的部署部分、`scripts/load_sample.sh`、`LICENSE`、`docs/`；
- 不要改 `dev-records/` 和 `samples/`。

先读 `docs/DEVLOG.md`、`docs/PLAN.md` 的部署部分和 `docs/reference/` 了解现状。本机 127.0.0.1:10800 的 seekdb 和 127.0.0.1:18801 的 PowerContext 是开发环境在用，不要动它们。

## 任务

1. **compose 修好并实际跑通**。评审会照 README 从零执行 `docker compose up -d --build`。
   - powercontext 镜像（python:3.12-slim）里没有 curl，现在的健康检查永远失败，app 也就永远起不来。用镜像里有的 python 做健康检查（`urllib.request` 请求 `/health/ready`）。seekdb 的健康检查用的是 `mysqladmin`，也要确认 seekdb 镜像里真的有它。
   - 端口只绑 `127.0.0.1`：PowerContext 没有鉴权，不能暴露到局域网。
   - PowerContext 用自己的嵌入式 seekdb，不依赖 seekdb 服务。去掉它对 seekdb 的 `depends_on`，在 compose 注释里写清楚。
   - `ghcr.io/astral-sh/uv` 固定到具体版本。去掉 `uv sync --frozen ... || uv sync ...` 这种回退，它会掩盖锁文件不一致。
   - **镜像构建时预下载向量模型**（BRIEF 的要求：运行时不联网）。
     - app 用 `fastembed.TextEmbedding(model_name)`，没有传 cache_dir。fastembed 会读环境变量 `FASTEMBED_CACHE_PATH`，所以在镜像里设好它，构建时下载到那里就行，不需要改 app 代码。
     - app 服务设置 `HF_HUB_OFFLINE=1`，证明运行时确实不再下载。
     - 构建参数支持 `HF_ENDPOINT`（国内网络可以设成 `https://hf-mirror.com`）。
   - 本机是 Apple Silicon（arm64）。查清楚 seekdb 镜像、PowerContext 及其嵌入式 seekdb 的 wheel、app 的依赖是否都有 arm64 和 amd64 版本。查镜像 manifest 和 PyPI 的 wheel 列表就可以，不用真的构建 amd64。如果某个只有 amd64，在 compose 里指定 `platform` 并写清楚。
2. **你自己验证 compose**。为了不和开发容器冲突，用单独的项目名和端口：
   - 新建 `qoder/.env.ci`（已被 .gitignore 忽略），`SEEKDB_PASSWORD` 用一个随机值，`SEEKDB_HOST_PORT=18805`、`POWERCONTEXT_HOST_PORT=18806`、`APP_PORT=18807`；
   - docker 命令只能这样写：`docker compose -p examradar-ci --env-file .env.ci <子命令>`，子命令为 `up -d --build`、`ps`、`logs <服务>`、`down -v`、`config`。查平台可以用 `docker manifest inspect <镜像>` 或 `docker buildx imagetools inspect <镜像>`。别的 docker 命令不会被允许；
   - 跑通后用 `down -v` 清掉。会话结束时不要留下 examradar-ci 的容器和卷。
3. **导入脚本走 HTTP**。`scripts/load_sample.sh` 改成通过 `POST /api/documents` 导入，请求带 `X-ExamRadar-Source: auto`；`APP_URL` 默认 `http://127.0.0.1:18800`。这样本地开发和 Docker 部署用同一个脚本。脚本打印每份资料的块数，重复运行不会重复入库。
4. **冒烟验证**，对 examradar-ci（`APP_URL=http://127.0.0.1:18807`）依次执行：
   - 导入样例：6 份资料，试卷 11 题合计 100 分；
   - 一条 `POST /api/search` 检索；
   - 一次 `POST /api/coverage/analyze`；
   - PowerContext 的 `/health/ready`；
   - 首页返回 200。

   请求都带 `X-ExamRadar-Source: auto`。这一步只验证能跑通，不验收覆盖判定的结果，判定由会话 05 修。
5. **`qoder/LICENSE`**：Apache-2.0 全文。
6. **`docs/DEPLOY.md`**：部署说明，之后会并入 README。内容包括：
   - 两种部署方式：Docker 一键启动，以及本地开发（`docker-compose.dev.yml` 起 seekdb 和 PowerContext，`cd app && uv run` 起应用）；
   - 版本表；
   - 端口；
   - 每个环境变量的含义和默认值；
   - `HF_ENDPOINT`；
   - 常见问题：模型下载慢、端口占用、Apple Silicon、PowerContext 首次启动要 1–3 分钟。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。在 `qoder/` 下运行时，uv 会向上找到本仓库之外的另一个项目。可以用 `cd app && uv lock --check` 确认锁文件和 pyproject 一致。
- 临时文件放在 `qoder/.cache/scratch/`，已被 git 忽略。`rm` 不在允许的命令里。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip。
- 镜像构建可能要几分钟。用 Bash 的后台运行方式执行 `up -d --build`，再用 `ps` 和 `logs` 查看进度。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- 先 `down -v`，再 `docker compose -p examradar-ci --env-file .env.ci up -d --build` 从零启动，三个服务都 healthy。
- 冒烟验证每一步的命令和输出写进 DEVLOG。
- app 容器在 `HF_HUB_OFFLINE=1` 下能导入和检索，说明模型已经打进镜像。
- `ps` 显示端口只绑在 127.0.0.1。
- 写清楚每个镜像和 wheel 的平台支持情况。
- 会话结束前 `down -v` 清掉 examradar-ci，不留容器和卷；关掉你启动的进程。
- `app/` 下没有任何改动。

结束前在 `docs/DEVLOG.md` 末尾追加"会话 06"一节：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。
