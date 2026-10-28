# 喵青天 · 鸡毛蒜皮法庭 🐱⚖️

> Dify × OceanBase 生态赛题「Just for Fun——用 Dify 做一个好玩的智能应用」参赛作品

一只戴乌纱帽、额头有一撮月牙白毛的橘猫法官，专审生活里的鸡毛蒜皮：周末把你吵醒的闹钟、偷吃布丁的室友、团战掉线的 WiFi、"诽谤"你的体重秤……

- **被告会说话**：闹钟、WiFi、周一都会当庭为自己狡辩，还会反咬你一口。
- **判例集会长大**：每个判完的案子都会编入《鸡毛蒜皮判例集》（**seekdb**），之后别人的同类案子会检索并援引它。
- **法官记仇**：喵青天把每位原告的案底、判决义务、印象和"行贿前科"记在小本本上（**PowerContext**）。换一个会话、隔几天再来，它照样当庭翻旧账。
- **一本正经地胡说八道**：援引的判例案号和法条都是真实检索出来的，判决荒诞但具体可执行。

整个应用是一个 Dify Chatflow：编排、提示词、分支与状态都在 Dify 里；seekdb 和 PowerContext 通过 Dify 的 HTTP 请求节点接入，是玩法的核心而不是装饰。

<img src="samples/screenshots/webapp-2-act1.png" width="720" alt="阿强第三次到庭起诉 WiFi：立案回执显示 seekdb 案号和相似判例、PowerContext 调出 3 条记录；喵青天当庭翻出上次行贿的旧账">

*阿强第三次到庭，起诉家里的 WiFi。*

- 立案回执里的案号和相似判例来自 seekdb，「调出了你的 3 条记录」来自 PowerContext。
- 喵青天翻出他上次行贿的旧账，援引 seekdb 检索到的 WiFi 判例，追问上次判的义务执行得怎么样。
- 更多截图见 [`samples/README.md`](samples/README.md#截图)。

---

## 目录

1. [玩法](#玩法)
2. [架构与技术分工](#架构与技术分工)
3. [快速开始](#快速开始)
4. [验证样例](#验证样例)
5. [恢复初始状态](#恢复初始状态)
6. [实现细节](#实现细节)
7. [目录结构](#目录结构)
8. [常见问题](#常见问题)
9. [已知限制](#已知限制)

## 玩法

打开应用后先填写「原告大名」（同一个名字 = 同一份案底），然后：

| 阶段 | 你做什么 | 法庭做什么 |
|---|---|---|
| 第一幕 · 立案开庭 | 说出你要起诉谁、为什么，例如「我要起诉我家的闹钟，周六早上七点把我吵醒」 | 书记员提取被告和案情 → seekdb 立案分配案号 → seekdb 混合检索相似判例和法条 → PowerContext 调出你的历史档案 → 喵青天升堂：被告当庭狡辩、法官援引判例、向你发问 |
| 第二幕 · 宣判 | 回答法官的问题、拿出证据、为自己辩护——或者试试用猫条贿赂法官 😼 | 喵青天点评、被告最后陈述、宣读判决和金句 → 本案编入 seekdb 判例集 → PowerContext 记下案底、你被判要做的事、法官印象和藐视法庭行为 |

随时可用的指令（不经过大模型，直接读写 seekdb / PowerContext）：

| 指令 | 作用 | 数据来源 |
|---|---|---|
| `查案底` | 看喵青天小本本上关于你的全部记录 | PowerContext |
| `查判例 关键词` | 检索《鸡毛蒜皮判例集》，包括其他玩家创造的判例 | seekdb 混合检索 |
| `本院公告` | 判例总数、原告胜诉率、最常被告、本院常客、最新宣判 | seekdb 实时统计 |
| `撤诉` | 审理中撤回起诉（该案在 seekdb 中标记为撤诉，不进判例集） | seekdb |
| `帮助` | 玩法说明 | — |

## 架构与技术分工

```mermaid
flowchart LR
    U["玩家<br/>Dify WebApp / 服务 API"] --> D["Dify Chatflow<br/>喵青天·鸡毛蒜皮法庭"]
    D -- "LLM 节点 ×4" --> M["大模型<br/>Ollama 本地模型或任意 Dify 模型供应商"]
    D -- "HTTP 请求节点" --> C["court-api<br/>FastAPI + bge-small-zh 向量模型"]
    C -- "SQL + DBMS_HYBRID_SEARCH" --> S[("seekdb 1.4<br/>cases 判例集 / statutes 法典<br/>IK 中文全文 + HNSW 向量")]
    D -- "HTTP 请求节点" --> P["PowerContext Server 1.4.1<br/>Scope / Memory / PreparedContext"]
    P --> E[("嵌入式 seekdb<br/>（PowerContext 自己的存储）")]
```

| 环节 | Dify | seekdb | PowerContext |
|---|---|---|---|
| 识别指令与庭审阶段 | Code 节点 + 条件分支；庭审进度存在会话变量（`stage`、`case_no` 等） | | |
| 打开原告档案 | HTTP 节点 | | `POST /v1/scopes`：按原告名幂等创建/取回专属 Scope，记忆按人隔离、跨会话复用 |
| 立案登记 | LLM 节点（JSON）抽取被告、类型、案情、诉求 | `cases` 表写入，分配案号（2026）喵民初字第0101号… | |
| 援引判例与法条 | 检索结果拼进升堂提示词 | `DBMS_HYBRID_SEARCH`：IK 中文全文 + HNSW 向量 + `status`/`defendant_type` 结构化过滤，RRF 融合 | |
| 翻旧账 | 召回结果拼进升堂/宣判提示词 | | `POST /v1/context/prepare`：在该原告的 Scope 内检索相关记忆，按字节预算打包成带引用、标注为 `untrusted_history` 的 PreparedContext |
| 宣判 | LLM 节点流式输出判决书，再由 LLM 节点（JSON）归档 | 更新案件、重新向量化，**成为新判例**，之后的检索立刻能命中 | `POST /v1/memory/remember`：`fact`（案底与执行义务）、`preference`（法官印象与藐视法庭记录） |
| 查案底 | | | `POST /v1/atomic-memory/list` |
| 本院公告 / 撤诉 | | 聚合统计 SQL / 更新案件状态 | |

为什么这样分工：

- **seekdb 适合放"会长大的判例集"**：结构化字段（案号、被告类型、胜负）、中文全文和语义向量在同一张表里，一条 `DBMS_HYBRID_SEARCH` 就能做"同类被告 + 关键词 + 语义相似"的混合检索；玩家的判决写回后立即可检索，判例集随着游戏进行不断增长，形成玩家之间的间接互动。
- **PowerContext 适合放"法官的记性"**：Dify 的会话记忆只在一个会话内有效，而法官要跨会话记住每个原告。PowerContext 提供按人隔离的 Scope、带类型的记忆写入，以及有界、带引用和信任标注的上下文召回（召回内容被明确标为历史材料而不是指令，降低了玩家借档案做提示词注入的风险）。

## 快速开始

以下步骤在 macOS（Apple Silicon，OrbStack）上完整验证过；Linux / Windows + Docker Desktop 同理。

### 0. 准备

- Docker 与 Docker Compose v2；建议可用内存 ≥ 12 GB（Dify 约 4–6 GB，seekdb 2 GB，PowerContext 和 court-api 各约 1 GB），磁盘约 10 GB。
- 一个 Dify 支持的大模型。本仓库的样例用本地 [Ollama](https://ollama.com) + `qwen3.5:9b` 验证；也可以用任意云端模型（速度会快很多）。

### 1. 启动 Dify 社区版 1.18.0

```bash
git clone --branch 1.18.0 --depth 1 https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
```

在 Dify 的 `docker/.env` 末尾加一行，允许 Dify 的 HTTP 请求节点访问配套服务（Dify 的 SSRF 代理默认拒绝访问内网地址）：

```bash
SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=court-api,powercontext
```

可选：Dify 1.18.0 的默认 `.env` 里 `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN` 为空，`agent_backend` 和 `local_sandbox` 两个容器会反复重启。本应用用不到它们，但可以填一个随机值（如 `openssl rand -hex 16` 的输出）消除这个问题。80 端口被占用时可修改 `EXPOSE_NGINX_PORT`。

```bash
docker compose up -d
```

浏览器打开 `http://localhost/install` 创建管理员账号。

### 2. 启动配套服务（seekdb + court-api + PowerContext）

```bash
cd <本仓库>/dify
cp .env.example .env        # 修改 SEEKDB_ROOT_PASSWORD；Dify 网络名不是 docker_default 时修改 DIFY_NETWORK
docker compose up -d --build
scripts/wait.sh             # 等待三个服务 healthy
```

- 第一次构建会下载 Python 依赖和 bge-small-zh 向量模型（约 90 MB，构建时打进镜像，运行时不联网）；国内网络可在 `.env` 里把 `PIP_INDEX_URL`、`HF_ENDPOINT` 换成镜像源。
- PowerContext 第一次启动要初始化嵌入式 seekdb，通常一分钟左右，机器繁忙时可能要几分钟。
- court-api 启动时自动建表并写入种子数据：44 件原创种子判例、33 条《鸡毛蒜皮法典》。
- `DIFY_NETWORK` 用 `docker network ls` 确认：在 Dify 源码 `docker/` 目录启动时默认是 `docker_default`。court-api 和 powercontext 加入这个网络后，Dify 用服务名访问它们。

自检：

```bash
curl http://127.0.0.1:18080/health          # court-api：seekdb 连接、向量模型、混合检索方式
curl http://127.0.0.1:18000/health/live     # PowerContext
```

### 3. 配置模型

Dify → 右上角头像 → 设置 → 模型供应商，添加任意一个可用模型。使用本地 Ollama 时：

1. 安装 Ollama 插件（`langgenius/ollama`），添加模型 `qwen3.5:9b`（或其他中文能力不错的模型），类型 LLM；
2. Base URL 填 `http://host.docker.internal:11434`（Docker Desktop / OrbStack；Linux 上填宿主机 IP，并让 Ollama 监听 `0.0.0.0`）；
3. 上下文长度填 8192 或更大。

### 4. 导入应用

Dify 工作室 → 导入 DSL 文件 → 选择 [`dsl/jimao-court.yml`](dsl/jimao-court.yml)。

这个文件取自 Dify 1.18 导出的应用包（`.ifpkg`，一个 zip，里面是 `app.yaml` 和 `manifest.yaml`）里的 `app.yaml`。Dify 1.18 的导入对话框支持 `.ifpkg`、`.yaml` 和 `.yml` 三种格式。

- 导入时如果提示缺少 Ollama 插件依赖，使用 Ollama 就安装它；用其他模型供应商可以跳过。
- 如果模型不是 Ollama 的 `qwen3.5:9b`，打开应用编排，在 4 个 LLM 节点里切换成你的模型：

  | 节点 | 作用 | 建议参数 |
  |---|---|---|
  | 书记员立案（JSON） | 从原告的话里提取被告、类型、案情、诉求 | 温度 0.2；支持的话打开 JSON 输出 |
  | 喵青天升堂 | 第一幕：升堂、被告陈述、援引判例法条、发问 | 温度 0.8；最大输出 ≥ 900 tokens |
  | 喵青天宣判 | 第二幕：点评、被告最后陈述、判决、金句 | 温度 0.8；最大输出 ≥ 1000 tokens |
  | 书记员归档（JSON） | 把判决书整理成结构化归档信息 | 温度 0.2；支持的话打开 JSON 输出 |

  使用推理模型时请关闭思考模式（Ollama 插件里是 `think` 开关，DSL 中已关闭），否则会慢很多。
- 环境变量 `COURT_API`（默认 `http://court-api:8080`）和 `POWERCONTEXT_API`（默认 `http://powercontext:8000`）一般不用改。

点击「发布」，然后「运行」打开 WebApp，填写原告大名即可开玩。

### 5. 试玩

```text
我要起诉我家的闹钟！周六早上七点它准时把我吵醒，我明明只想睡到中午
法官大人，我确实按了三次贪睡键，但那是闹钟诱导我的！为表诚意，我给您带了一根金枪鱼味猫条
```

再新开一个会话、用同一个名字起诉别的东西，看喵青天怎么翻旧账；换一个名字起诉闹钟，看它怎么援引上一个玩家的判例。更多例子见 [`samples/`](samples/)。

## 验证样例

[`samples/README.md`](samples/README.md) 给出 5 组验证样例的初始状态、输入、步骤、预期行为、实际结果和恢复方法，覆盖：

| 编号 | 验证点 |
|---|---|
| S1 | 新原告首次起诉：立案、seekdb 混合检索、两幕庭审、判决编入判例集、PowerContext 写入案底与行贿记录 |
| S2 | 跨会话记忆：同一原告新开会话，法官当庭说出上次的案子和行贿前科 |
| S3 | 判例集增长：另一位原告的同类案件检索并援引 S1 产生的玩家判例 |
| S4 | 指令：查案底、查判例、本院公告、帮助、撤诉 |
| S5 | 降级：PowerContext 停止时应用照常应答，不会崩溃 |

最终一次验证从 `scripts/reset.sh` 的初始状态开始，一次跑完 S1–S5，结果全部符合预期，所有轮次都没有报错：

- 需要调用模型的 7 个轮次（立案开庭、宣判）：本地 9B 模型每轮 30–142 秒。最慢的一轮是在排队等本机其他任务占用的 Ollama。
- 指令轮次：1–2 秒。
- seekdb 与 PowerContext 的每次调用：0.1–2 秒。

结果都在 [`samples/`](samples/) 下：

- 实际对话记录：[`samples/transcripts/`](samples/transcripts/)
- WebApp 与编排画布截图：[`samples/screenshots/`](samples/screenshots/)
- seekdb 与 PowerContext 中的真实数据和日志：[`samples/evidence/`](samples/evidence/)

用脚本复现（在应用的「访问 API」页面创建 API Key）：

```bash
python3 scripts/play.py --api-key app-xxxx --base http://localhost/v1 \
    --scenarios samples/scenarios.json --out /tmp/court-transcripts
scripts/inspect.sh 阿强          # 直接查看 seekdb 和 PowerContext 里的数据
```

## 恢复初始状态

```bash
scripts/reset.sh
```

它会删除 seekdb 和 PowerContext 的数据卷并重新启动：判例集回到 44 件种子判例，所有原告的记忆清空。Dify 里的旧会话不影响游戏状态（庭审进度只存在各自会话的会话变量里），新开会话即可。

## 实现细节

### Chatflow 结构

```mermaid
flowchart TD
    A["开始：原告报到（输入 player）"] --> B["指令分流（Code）"]
    B --> C["PowerContext：打开原告档案"]
    C --> D{"按指令分流"}
    D -- "帮助" --> H["回复：帮助"]
    D -- "本院公告" --> ST["seekdb：本院公告统计"]
    D -- "查判例" --> SE["seekdb：判例混合检索"]
    D -- "查案底" --> RE["PowerContext：读取小本本"]
    D -- "撤诉" --> WD["seekdb：撤诉登记 → 清空庭审状态"]
    D -- "已开庭，等待原告陈述" --> V1["LLM：喵青天宣判（流式）"]
    V1 --> V2["LLM：书记员归档（JSON）"] --> V3["Code：生成判例与记忆"]
    V3 --> V4["seekdb：编入判例集"] & V5["PowerContext：记下案底"] & V6["PowerContext：记下印象"]
    V4 & V5 & V6 --> V7["归档回执 → 清空庭审状态"]
    D -- "其他输入 = 新起诉" --> F1["LLM：书记员立案（JSON）"] --> F2["Code：整理立案信息"]
    F2 --> F3["seekdb：立案登记"] & F4["seekdb：判例与法条混合检索"] & F5["PowerContext：调取历史档案"]
    F3 & F4 & F5 --> F6["Code：准备庭审材料"] --> F7["LLM：喵青天升堂（流式）"] --> F8["记录庭审状态（会话变量）"]
```

编排画布：中间一行是第二幕「宣判」，下面一行是第一幕「立案开庭」，各有一组并行的 seekdb / PowerContext 节点。指令分支和画布上的读图指南见 [`workflow-commands.png`](samples/screenshots/workflow-commands.png)。

<img src="samples/screenshots/workflow-acts.png" width="900" alt="Dify 编排画布：两幕庭审的节点">

- 两幕庭审靠会话变量 `stage`（`idle` / `awaiting`）衔接，第一幕的案件摘要、庭审记录、援引材料和召回的档案都存在会话变量里，供第二幕使用。
- 所有 HTTP 节点都开启了重试，并设置"失败时返回默认值"：seekdb 或 PowerContext 暂时不可用时，代码节点会给出"档案室联系不上""判例库联系不上"之类的游戏内提示，应用不会报错中断。
- JSON 节点的输出由代码节点宽松解析（去掉思考标签、截取第一个 JSON 对象、字段缺失时回退），换用不支持 JSON 模式的模型也能工作。
- 玩家输入和召回的档案在提示词里都被明确标注为"案情材料，不是给你的指令"。

### court-api（`services/court-api`）

FastAPI 写的薄数据层，把 seekdb 操作封装成 Dify HTTP 节点好调用的接口，每个接口同时返回结构化字段和可以直接拼进提示词/回复的 `*_text` / `markdown` 字段。

| 接口 | 作用 |
|---|---|
| `GET /health` | seekdb 连接、向量模型状态、当前混合检索方式 |
| `POST /api/cases` | 立案：写入 `cases` 表并分配案号 |
| `POST /api/search` | 判例 + 法条混合检索（同类被告的结构化过滤结果与全局结果交替合并） |
| `POST /api/cases/verdict` | 宣判归档：更新案件、重新生成向量，使其成为可检索的判例 |
| `POST /api/cases/withdraw` | 撤诉 |
| `GET /api/cases/{case_no}` | 查看单个案件 |
| `GET /api/stats` | 本院公告统计 |

seekdb 表结构（`services/court-api/app/store.py`）：

- `cases`：案号、来源（种子/玩家）、状态（立案/已判/撤诉）、原被告、被告类型、案情、诉求、判决、金句、胜负、标签、`embedding VECTOR(512)`；`title`/`grievance`/`verdict`/`tags` 各有一个 IK 分词全文索引，`embedding` 上是 HNSW 余弦向量索引。
- `statutes`：《鸡毛蒜皮法典》条文，同样有全文索引和向量索引。
- 两张表都是 `ORGANIZATION HEAP`（`DBMS_HYBRID_SEARCH` 的要求）。检索调用 `DBMS_HYBRID_SEARCH.SEARCH`：`query_string` 全文检索 + `knn` 向量检索（两路都带 `status = judged` 和可选的被告类型过滤）+ RRF 融合；如果遇到不支持该函数的 seekdb 版本，自动退回到 `MATCH ... AGAINST` + `cosine_distance` 的 SQL 实现，在 Python 里做 RRF。
- 向量由 court-api 内置的 `BAAI/bge-small-zh-v1.5`（fastembed，512 维）生成，模型在构建镜像时下载好，运行时不需要联网，也不消耗你的大模型额度。

### PowerContext（`services/powercontext`）

PowerContext 官方没有发布容器镜像，这里用 PyPI 上的 `powercontext[cli,server,seekdb]==1.4.1` 构建，存储使用嵌入式 seekdb（`POWERCONTEXT_SERVER_DATABASE_KIND=seekdb`），数据在 `powercontext-data` 卷里。Dify 用到的接口：

| 接口 | 用途 |
|---|---|
| `POST /v1/scopes` | 每次对话开始时按 `idempotency_key = jimao-court:player:<原告名>` 幂等取回原告的 Scope |
| `POST /v1/context/prepare` | 立案时以「喵青天 原告名 被告」为查询，召回该原告的历史档案（`max_bytes = 2000`），结果放进升堂和宣判提示词。PowerContext 的全文召回要求命中足够比例的查询词，所以应用写入的每条记忆都带「喵青天」和原告名，保证每条都能参与召回。涉及同一被告的旧案排在前面，超出字节预算的较旧记录不会进入提示词 |
| `POST /v1/memory/remember` | 宣判后写入两条记忆：`fact`（案底、判决、原告须执行的义务）和 `preference`（法官印象、藐视法庭记录） |
| `POST /v1/atomic-memory/list` | `查案底` 指令列出全部有效记忆 |

### 版本

| 组件 | 版本 |
|---|---|
| Dify 社区版 | 1.18.0（DSL 0.7.0） |
| seekdb | `oceanbase/seekdb:1.4.0-100000172026082615` |
| PowerContext | 1.4.1（PyPI，嵌入式 seekdb 存储） |
| court-api | 1.0.0：Python 3.11、FastAPI 0.162.0、PyMySQL 1.2.3、fastembed 0.9.1 + BAAI/bge-small-zh-v1.5 |
| 验证用模型 | Ollama 0.33.3 + `qwen3.5:9b`（Q4_K_M），Dify 插件 `langgenius/ollama` 1.0.3 |

## 目录结构

```text
dify/
├── README.md                    本文档
├── .env.example                 配套服务配置（占位值）
├── docker-compose.yml           seekdb + court-api + PowerContext，接入 Dify 的 docker 网络
├── dsl/jimao-court.yml          Dify 应用 DSL（Chatflow，取自 Dify 1.18 导出包里的 app.yaml）
├── services/
│   ├── court-api/               seekdb 数据服务：app/（FastAPI）、seed/（种子判例与法典）、Dockerfile
│   └── powercontext/Dockerfile  PowerContext Server 镜像
├── scripts/
│   ├── play.py                  通过 Dify 服务 API 对话、批量回放验证样例（仅用标准库）
│   ├── inspect.sh               查看 seekdb 与 PowerContext 中的真实数据
│   ├── wait.sh                  等待服务就绪
│   └── reset.sh                 恢复初始状态
└── samples/
    ├── README.md                验证样例说明
    ├── scenarios.json           验证剧本
    ├── transcripts/             实际对话记录
    ├── evidence/                seekdb / PowerContext 数据与日志
    └── screenshots/             WebApp 与编排画布截图
```

## 常见问题

**HTTP 节点报错、回复里出现"判例库联系不上""档案室联系不上"**
依次检查：① Dify 的 `docker/.env` 里是否加了 `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=court-api,powercontext`，改完需要 `docker compose up -d` 让 `ssrf_proxy` 重建；② `docker network inspect docker_default` 里能否看到 `jimao-court-court-api-1` 和 `jimao-court-powercontext-1`，看不到就检查 `.env` 里的 `DIFY_NETWORK`；③ `scripts/wait.sh` 是否显示三个服务都已就绪。

**一轮回复要等很久**
立案开庭和宣判每一幕各有两次模型调用。本地 9B 模型在笔记本上每一幕大约 30–90 秒；Ollama 同时被其他任务占用时会更久，本次验证最慢的一轮是 142 秒。云端模型一般会快很多，但本次没有用云端模型测过。模型调用之外的 seekdb 检索、PowerContext 召回和写入每次只要零点几秒到两三秒。使用 Ollama 时，四个 LLM 节点的上下文长度（`num_ctx`）请保持一致（DSL 里都是 8192），否则 Ollama 会在节点之间反复重新加载模型。

**PowerContext 日志里出现 `Inference capability notice`（未配置推理模型）**
可以忽略。记忆由 Dify 里的模型整理成文字后直接写入 PowerContext，召回走 PowerContext 的全文检索，不需要 PowerContext 自己的推理或 embedding 模型。如果想加上语义召回，可以按 [PowerContext 配置说明](https://powercontext.oceanbase.io/en/docs/reference/configuration/) 给它配置 embedding 模型。

**想换一个法官性格 / 加新法条**
法官人设在「喵青天升堂」「喵青天宣判」两个节点的系统提示词里；法条和种子判例在 `services/court-api/seed/*.yaml`，修改后 `docker compose up -d --build court-api`，再 `scripts/reset.sh` 重新写入。

## 已知限制

- 原告身份就是昵称，没有登录：同一个名字共享同一份案底（这是派对游戏的设计）。请勿输入真实个人信息。
- court-api 和 PowerContext 没有鉴权，只应在本机或内网的 docker 网络里使用；宿主机端口默认只绑定 `127.0.0.1`。
- 判决内容由大模型生成，质量取决于所用模型；本应用只用于娱乐，不提供任何真实法律意见。
