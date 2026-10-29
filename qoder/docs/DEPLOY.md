# ExamRadar 部署说明

> 本文档描述两种部署方式（Docker 一键启动 / 本地开发），以及全部配置项和常见问题。

## 1. 方式一：Docker 一键启动

前置要求：Docker（含 compose v2）。Apple Silicon（arm64）和 x86（amd64）均可。

```bash
cd qoder
cp .env.example .env          # 按需修改密码和端口
docker compose up -d --build
```

三个服务：

| 服务 | 说明 | 镜像 |
|------|------|------|
| seekdb | 混合检索数据库（MySQL 协议，容器内端口 2881） | `oceanbase/seekdb:1.4.0-100000172026082615` |
| powercontext | 记忆服务，使用**嵌入式 seekdb**（数据在 `pc-data` 卷，不依赖 seekdb 服务） | 自建（`docker/Dockerfile.powercontext`，基于 `python:3.12-slim` + PyPI `powercontext[cli,server,seekdb]==1.4.1`） |
| app | ExamRadar 应用（FastAPI，容器内端口 18800） | 自建（`docker/Dockerfile.app`，基于 `python:3.12-slim` + uv） |

启动顺序由健康检查控制：seekdb healthy → powercontext healthy → app。**PowerContext 首次启动要初始化嵌入式 seekdb，需要 1–3 分钟**，`docker compose ps` 里显示 `health: starting` 是正常现象。

启动完成后：

- 首页：http://127.0.0.1:18800
- 导入样例资料：`bash scripts/load_sample.sh`
- 修改 `APP_URL` 后同一个脚本可用于任何部署实例

> 安全：app、PowerContext 和 seekdb 都没有鉴权，三个端口**只绑定 127.0.0.1**，不要改成 `0.0.0.0` 暴露到局域网。

### 向量模型预下载（运行时不联网）

`BAAI/bge-small-zh-v1.5`（ONNX，约 100 MB）在**镜像构建时**下载进镜像（`FASTEMBED_CACHE_PATH=/opt/fastembed-cache`），运行时容器设置了 `HF_HUB_OFFLINE=1`，不会再访问 huggingface.co。

模型名是构建参数 `EMBEDDING_MODEL`，compose 用 `.env` 里的同一个 `EMBEDDING_MODEL` 变量同时传给构建参数和运行时环境。**换模型必须重新构建镜像**（`docker compose up -d --build`）：运行时是离线模式，只改 `.env` 不重建的话容器里没有新模型的权重，启动后向量化会报错。

构建参数 `HF_ENDPOINT` 用于切换下载源（默认 `https://huggingface.co`）。国内网络下载慢或超时：

```bash
# 方式一：写进 .env（compose 自动传给构建）
echo 'HF_ENDPOINT=https://hf-mirror.com' >> .env
docker compose up -d --build

# 方式二：只传给这一次构建
docker compose build --build-arg HF_ENDPOINT=https://hf-mirror.com
```

## 2. 方式二：本地开发

只起基础设施（seekdb + PowerContext），应用在本机跑，方便热重载和调试：

```bash
cd qoder
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d
```

等 PowerContext healthy（首次 1–3 分钟）后，在本机起应用：

```bash
cd app
uv run uvicorn examradar.main:app --reload --host 127.0.0.1 --port 18800
```

此时应用读取 `qoder/.env` 里的本机地址（`SEEKDB_HOST=127.0.0.1`、`SEEKDB_PORT=10800`、`POWERCONTEXT_URL=http://127.0.0.1:18801`）。本地开发模式下 fastembed 模型下载到系统临时目录下的 `fastembed_cache`（fastembed 源码 `define_cache_dir()`：`os.path.join(tempfile.gettempdir(), "fastembed_cache")`，Linux 上即 `/tmp/fastembed_cache`，macOS 上即 `$TMPDIR/fastembed_cache`），首次使用会联网下载。

开发环境需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)：

```bash
cd app
uv sync                 # 安装依赖（含 dev 组）
uv run pytest           # 单元测试
export EXAMRADAR_IT=1 && uv run pytest -m integration   # 集成测试（需 seekdb 可连）
```

## 3. 版本表

| 组件 | 版本 |
|------|------|
| seekdb 镜像 | `oceanbase/seekdb:1.4.0-100000172026082615` |
| PowerContext（PyPI） | `powercontext[cli,server,seekdb]==1.4.1` |
| 嵌入式 seekdb 驱动 | `pylibseekdb>=1.4.0.post1`（powercontext 依赖，锁 1.4.0.post2） |
| 应用基础镜像 / Python | `python:3.12-slim` / Python 3.12（`>=3.12,<3.13`） |
| uv | `ghcr.io/astral-sh/uv:0.8.15`（固定版本，与应用锁文件兼容） |
| 向量模型 | `BAAI/bge-small-zh-v1.5`（fastembed，ONNX，512 维） |
| fastembed | 0.9.1（uv.lock 锁定） |

## 4. 端口

| 端口 | 服务 | 用途 |
|------|------|------|
| 18800（默认） | app | ExamRadar Web/API（宿主机映射，容器内 18800） |
| 18801（默认） | powercontext | PowerContext API（宿主机映射，容器内 8000） |
| 10800（默认） | seekdb | MySQL 协议连接（宿主机映射，容器内 2881） |

三个端口全部只绑 `127.0.0.1`。端口冲突时改 `.env` 里的 `APP_PORT` / `POWERCONTEXT_HOST_PORT` / `SEEKDB_HOST_PORT`。

## 5. 环境变量

`.env`（compose 用）和 `qoder/.env`（本地开发时应用直接读）共用一套变量；compose 容器内的服务间地址由 `docker-compose.yml` 的 `environment:` 块写死，`.env` 只需要提供下面这些。

### compose 变量（docker-compose.yml 插值）

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `SEEKDB_PASSWORD` | 无（必须设置） | seekdb root 密码，同时传给 app；务必改掉 `change-me` 占位值 |
| `SEEKDB_HOST_PORT` | 10800 | seekdb 映射到宿主机的端口 |
| `POWERCONTEXT_HOST_PORT` | 18801 | PowerContext 映射到宿主机的端口 |
| `APP_PORT` | 18800 | app 映射到宿主机的端口 |
| `SEEKDB_DATABASE` | examradar | app 使用的库名（自动创建） |
| `HF_ENDPOINT` | https://huggingface.co | 向量模型构建期下载源（如 `https://hf-mirror.com`） |
| `CORS_ORIGINS` | http://localhost:18800 | 允许的跨域来源 |
| `EMBEDDING_PROVIDER` | local | `local`（fastembed 离线）或 `openai`（OpenAI 兼容 API） |
| `EMBEDDING_MODEL` | BAAI/bge-small-zh-v1.5 | 向量模型名（同时作为构建参数预下载进镜像，换模型要重新 `--build`） |
| `EMBEDDING_DIM` | 512 | 向量维度（必须与模型一致） |

### 应用变量（本地开发时写在 `qoder/.env`）

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `SEEKDB_HOST` | 127.0.0.1 | seekdb 地址（compose 内为 `seekdb`） |
| `SEEKDB_PORT` | 10800 | seekdb 端口（compose 内为 2881） |
| `SEEKDB_USER` | root | 数据库用户 |
| `SEEKDB_TEST_DATABASE` | examradar_test | 集成测试专用库（`EXAMRADAR_IT=1` 时使用） |
| `POWERCONTEXT_URL` | http://127.0.0.1:18801 | PowerContext 地址（compose 内为 `http://powercontext:8000`） |
| `APP_HOST` / `APP_PORT` | 127.0.0.1 / 18800 | 应用监听地址（compose 内为 0.0.0.0 / 18800） |
| `EMBEDDING_QUERY_INSTRUCTION` | 空 | BGE 查询指令前缀（默认关闭，见 DEVLOG 会话 03 的对照实验） |
| `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` | 空 | 仅 `EMBEDDING_PROVIDER=openai` 时需要 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 空 | 可选 LLM（出题/判分增强；base_url 和 model 都配置才生效，未配置走规则出题 + 自评判分）。OpenAI 兼容 API，本地 Ollama 可用 `http://127.0.0.1:11434/v1` |
| `POWERCONTEXT_TIMEOUT_SECONDS` | 8.0 | PowerContext HTTP 超时（判分等记忆写路径的超时上限；超时进入降级，答题不受影响） |
| `SESSION_IDLE_MINUTES` | 30 | 学习会话空闲判定：超过该分钟数无事件，会话视为结束（时长按最后一个事件计） |
| `PC_CONTEXT_MAX_BYTES` | 2000 | 单次读回 PowerContext 上下文（bootstrap / prepare）的字节上限 |
| `LLM_MAX_CONTEXT_BYTES` | 6000 | 发给 LLM 的出题材料（正文 + 历史错题）字节上限 |
| `COVERAGE_TERM_RATIO_COVERED` | 0.5 | covered 要求的考点词找到比例 |
| `COVERAGE_SUPPORT_CHARS` | 280 | covered 要求的支撑正文字数（介于两者之间为 thin） |
| `COVERAGE_MIN_BODY_CHARS` | 50 | 正文短于该值的块（目录页等）不算覆盖证据 |
| `LEITNER_INTERVALS` | 1,2,4,7,14 | Leitner 复习间隔（天，1–5 号盒子） |

### 脚本变量

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `APP_URL` | http://127.0.0.1:18800 | `scripts/load_sample.sh` 导入目标地址 |

## 6. 常见问题

**模型下载慢 / 构建超时**
镜像构建要从 huggingface.co 下载 `BAAI/bge-small-zh-v1.5`（约 100 MB）。国内网络设 `HF_ENDPOINT=https://hf-mirror.com`（见上文）。下载失败会导致 `docker compose build` 报错，重跑即可（已下载的层有缓存）。

**端口占用**
`docker compose up` 报 `port is already allocated` 时，在 `.env` 里把对应端口改掉（`APP_PORT` / `POWERCONTEXT_HOST_PORT` / `SEEKDB_HOST_PORT`）。

**Apple Silicon（arm64）**
seekdb 镜像、PowerContext 及其嵌入式 seekdb（pylibseekdb wheel）、应用全部原生依赖均提供 linux arm64 和 amd64 版本，无需 Rosetta，也无需在 compose 里指定 `platform`。如果 Docker Desktop 配置了强制 amd64 模拟，建议关掉，ONNX 推理在模拟下会慢很多。

**PowerContext 首次启动慢（1–3 分钟）**
首次启动要初始化嵌入式 seekdb 存储，`docker compose ps` 显示 `health: starting`、`docker compose logs powercontext` 无 HTTP 日志都是正常的。健康检查放宽到 `start_period: 180s`，不要在初始化完成前重启容器。之后的重启只需几秒。

**PowerContext 和 seekdb 的关系**
PowerContext 用自己的嵌入式 seekdb（数据在 `pc-data` 卷），**不依赖** compose 里的 seekdb 服务（1.4.1 的服务端模式连 seekdb 报 `OceanBase maintenance requires a MySQL user tenant.`，见 `docs/reference/powercontext-1.4.1-notes.md`）。两份数据互不相干，`down -v` 会同时清掉。

**健康检查为什么用 python 而不是 curl**
`python:3.12-slim` 里没有 curl，PowerContext/app 的健康检查用 `python -c "import urllib.request; ..."` 实现；seekdb 官方镜像自带 `mysqladmin`，用 `mysqladmin ping`。

**彻底清空重来**
```bash
docker compose down -v        # 停止并删除容器、卷（seekdb 和 PC 的数据都没了）
docker compose up -d --build
```
