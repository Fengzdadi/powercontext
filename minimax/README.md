# 规有所依：面向软件持续演进的 SDD 上下文管理系统（MiniMax × OceanBase）

`sddctx` 是一个给 AI 开发助手用的 SDD（规格驱动开发）上下文模块：

1. 把业务工程的规格、代码和测试切成片段导入 **seekdb**（IK 全文索引 + HNSW 向量索引 + 追溯关系表）；
2. 根据开发任务，用 seekdb 混合检索和追溯关系查询选出适用的规格条目、需要修改的代码符号、目标测试和回归测试，生成开发上下文；
3. 把上下文交给使用 **MiniMax** 的开发助手，由 MiniMax 通过工具调用读代码、改代码、跑测试，完成实际修改；
4. 运行修改前后的目标测试和回归测试；
5. 每一步的进展和验证结果写进 **PowerContext**，模块重启后读回，用于后续上下文和流程续跑。

模块结构、上下文选择方式和各项技术的分工见 [TECHNICAL_NOTE.md](TECHNICAL_NOTE.md)；验证样例见 [samples/T-101](samples/T-101/README.md)；
一次完整运行的记录见 [evidence/T-101](evidence/T-101/README.md)。

## 目录

| 路径 | 内容 |
|---|---|
| `sddctx/` | 上下文模块（Python 包 `sddctx`）和它的镜像 |
| `project/` | 业务工程：校园图书馆借阅服务（原创，Python 标准库 + pytest），含规格 `specs/`、代码 `library/`、测试 `tests/` |
| `samples/T-101/` | 验证样例：任务定义、上下文必须包含的来源、操作步骤和预期结果 |
| `evidence/T-101/` | 一次完整运行的产物：MiniMax 开发记录、代码差异、修改前后快照、测试日志、seekdb 查询记录、PowerContext 调用记录 |
| `services/powercontext/` | PowerContext Server 镜像（从 PyPI 发布包构建） |
| `docker-compose.yml`、`sdd`、`scripts/` | 运行环境、命令入口和辅助脚本 |

## 组件与版本

| 组件 | 版本 | 接入方式 |
|---|---|---|
| seekdb | 镜像 `oceanbase/seekdb:1.4.0-100000172026082615`（`SELECT version()`：`5.7.25-OceanBase seekdb-v1.4.0.0`） | MySQL 协议，PyMySQL 1.2.3；检索用 `DBMS_HYBRID_SEARCH.SEARCH` |
| PowerContext | 1.4.1（API 契约 1.4），PyPI `powercontext[cli,server]==1.4.1`，默认 SQLite 存储 | HTTP API：Scope、Work Contract、Task Outcome、Scope Sources |
| MiniMax | `MiniMax-M3.1-Flash`（Token Plan），`https://api.minimax.cn/anthropic` | Anthropic 兼容 Messages API（`POST /v1/messages`，`anthropic-version: 2023-06-01`）+ 工具调用，Python 标准库 urllib 直接调用 |
| sddctx | 1.0.0，Python 3.12（`python:3.12-slim-bookworm`），pytest 9.1.1 | 命令行（`./sdd <子命令>`，即 `python -m sddctx`） |
| 业务工程 | Python ≥ 3.11，只依赖标准库；测试用 pytest | — |
| 运行环境 | Docker Engine + Docker Compose v2（在 OrbStack、linux/arm64、Compose v5.5.0 上验证；镜像同时提供 amd64） | — |

## 快速开始

```bash
cd minimax
./sdd up                 # 构建镜像，启动 seekdb（127.0.0.1:10900）和 PowerContext（127.0.0.1:18900），等待健康检查
./sdd import             # 把 project/ 的规格、代码、测试导入 seekdb
./sdd run T-101          # context → verify-before → develop（MiniMax）→ verify-after
./sdd state T-101        # 查看 PowerContext 中保存的任务状态
```

`./sdd run T-101` 的 develop 步骤需要 MiniMax 密钥（见“配置”）。没有密钥时可以回放提交的开发记录：
`./sdd run T-101 --replay evidence/T-101/minimax/session.json`（MiniMax 的修改调用按记录重放，其他步骤照常实时执行）。

完整的验证流程（从空状态开始，中途重启服务后续跑，并收集全部产物）：`scripts/run-sample.sh`，或 `scripts/run-sample.sh --replay`。

## 配置

`./sdd` 第一次运行时会把 `.env.example` 复制为 `.env`。所有配置都是占位值，按需修改：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SEEKDB_ROOT_PASSWORD` | `change-me-local` | 本机 seekdb 容器的 root 密码 |
| `MINIMAX_API_KEY` | 空 | MiniMax Token Plan 密钥；也可以不写进 `.env`，运行前在 shell 中 `export MINIMAX_API_KEY=...` |
| `MINIMAX_REGION` | `cn` | `cn`：`https://api.minimax.cn/anthropic`；`intl`：`https://api.minimax.io/anthropic`。也可用 `MINIMAX_BASE_URL` 直接指定 |
| `MINIMAX_MODEL` | `MiniMax-M3.1-Flash` | 也可以用 `./sdd run T-101 --model MiniMax-M3` 临时指定 |
| `SDD_SEEKDB_HOST_PORT` / `SDD_POWERCONTEXT_HOST_PORT` | `10900` / `18900` | 宿主机端口，只绑定 127.0.0.1 |
| `SEEKDB_MEMORY_LIMIT` | `2G` | seekdb 容器的内存上限（可选） |
| `PIP_INDEX_URL` | PyPI | 构建镜像时的 PyPI 镜像 |

密钥只通过环境变量传给 sddctx 容器，只出现在请求头 `x-api-key` 里；所有记录文件写盘前会把密钥原值和 `sk-…` 形式的字符串替换成 `<redacted>`。

## 数据初始化

- `./sdd up` 创建两个数据卷：`seekdb-data`（工程资料和索引）、`powercontext-data`（任务状态）。
- `./sdd import` 读取 `project/sdd.toml`（工程标识、资料位置、只读规则），在 seekdb 的 `sdd` 库中建表并导入：
  - `sdd_chunks`：每个规格条目、规格说明小节、代码符号（模块头部、顶层函数和类）、测试函数一个片段；
    IK 分词（`max_word`）的全文索引建在 `title`、`keywords`、`content` 上，256 维向量建 HNSW 索引（cosine）；
  - `sdd_links`：追溯关系，`references`（规格之间的“关联”）、`implements`（代码 docstring 中的 `实现: ID`）、
    `verifies`（测试上的 `@pytest.mark.spec(...)`）、`calls`；
  - `sdd_chunk_revisions`：每个片段的修订历史；`sdd_import_runs`：导入批次。
- 导入是增量的：按内容指纹判断新增、更新（修订号 +1）、移动和删除。修改规格后再执行一次 `./sdd import`，上下文就会使用新内容。

## 调用入口

命令行：`./sdd <子命令>`（在一次性容器里执行 `python -m sddctx <子命令>`；不用 Docker 时可在装好依赖的 Python 3.11+ 环境里设置
`PYTHONPATH=sddctx/src` 和 `SDD_*` 环境变量后运行 `python -m sddctx`）。

| 子命令 | 输入 | 输出 |
|---|---|---|
| `import` | `project/`（按 `sdd.toml`） | seekdb 中的片段、追溯关系和修订；终端打印导入批次与变化 |
| `context <任务>` | 任务 ID（读 `samples/<ID>/task.toml`）或 task.toml 路径 | Markdown 上下文（终端 + `runs/<任务>/context.md`）和 JSON（`context.json`）；PowerContext 中没有记录时写入 Work Contract 和第一条 Task Outcome |
| `run <任务> [--stop-after 步骤] [--replay 记录] [--model 模型]` | 任务 | 从 PowerContext 记录的下一步继续执行 `context → verify-before → develop → verify-after`；每步写一条 Task Outcome |
| `verify <任务> --phase before\|after` | PowerContext 中记录的目标测试 | 测试日志和 junit 报告（`runs/<任务>/tests/<phase>/`），验证结论写入 PowerContext |
| `develop <任务> [--replay 记录] [--force]` | 上下文（现场从 seekdb 和 PowerContext 生成） | MiniMax 在 `runs/<任务>/snapshots/after/` 中修改代码；开发记录 `runs/<任务>/develop/session-*.json/.md`；差异 `runs/<任务>/change.patch` |
| `state <任务> [--json]` | 任务 ID | PowerContext 中的任务状态：已完成事项、验证结果、待办、记录历史 |
| `check-context <任务>` | `samples/<任务>/expected.json` | 逐项核对上下文必须包含的规格、代码、测试，以及来源真实性 |
| `check-record <任务> [--session 记录] [--patch 差异]` | MiniMax 开发记录 | 核对记录包含任务和上下文、来自 MiniMax 接口，重放修改调用得到与差异文件一致的结果 |
| `spec-update-demo <任务>` | `expected.json` 中的 `spec_update` | 修改规格 → 重新导入 → 上下文使用新内容 → 恢复规格 → 再导入 |
| `search <文本> [--kind spec,code,test]`、`db-inspect`、`info` | — | 一次混合检索的结果、seekdb 中的数据概况、组件版本 |

上下文（`context.md`）的结构：0 任务（含必须保持的行为）；1 适用规格（1.1 本次要实现的条目，全文；1.2 必须遵守的约束，全文；
1.3 同一接口的已实现条目）；2 代码（2.1 需要修改的符号，全文；2.2 可复用的相关代码）；3 测试（3.1 目标测试，全文和运行命令；
3.2 相关回归测试）；4 任务状态（来自 PowerContext）；5 工程约定；附录是 seekdb 检索结果（RRF 分数、全文和向量名次）。
每一处来源都写明 `路径:起止行`、修订号和内容指纹，生成时逐行回到工程文件核对。

`./sdd` 本身的管理命令：`up`、`restart`（重启 seekdb 和 PowerContext 容器）、`down`、`reset`、`ps`、`logs`。

## 测试命令

- 业务工程（不经过 sddctx，评审可以直接运行）：
  ```bash
  scripts/project-tests.sh project                          # 修改前：目标测试 25 failed（全部断言失败），回归测试 91 passed
  scripts/project-tests.sh evidence/T-101/snapshots/after   # 修改后（提交的快照）：目标测试 25 passed，回归测试 91 passed
  ```
  等价于在工程目录里执行 `python -m pytest -q tests/test_api_books_filters.py`（目标）和
  `python -m pytest -q --deselect tests/test_api_books_filters.py`（回归）。也可以复制 `project/` 后用
  `patch -p1 -d <副本> < evidence/T-101/change.patch` 应用 MiniMax 的修改再运行。
- 模块内的验证：`./sdd verify T-101 --phase before|after`。日志第一行起记录命令、工作目录、代码版本（git 提交号）、
  工程目录指纹（sha256）、开始时间、耗时和退出码。

## 技术使用记录

运行时自动写入 `runs/records/`：

- `seekdb-queries.jsonl`：每条 SQL（含 `DBMS_HYBRID_SEARCH.SEARCH` 的检索请求）、参数、返回行数、耗时；混合检索另记命中列表；
- `powercontext-calls.jsonl`：每次 PowerContext 调用的方法、路径、请求体、状态码和响应（读取任务记录时只记 source_id、位置和摘要）；
- MiniMax 开发记录：`runs/<任务>/develop/session-*.json`（每一轮的响应 ID、用量、思考摘要、工具调用和结果、最终差异）和同名 `.md`。

`evidence/T-101/` 中是一次完整运行（实时调用 MiniMax）的这些记录。

## 重置

```bash
./sdd reset     # 删除容器和数据卷（seekdb 资料、PowerContext 任务状态）以及 runs/，回到空状态
```

`project/` 不会被流程修改（MiniMax 在 `runs/` 下的工程副本里工作）；`spec-update-demo` 临时修改的规格文件在结束时恢复。

## 已知限制

- 向量是本地计算的 256 维特征哈希向量（英文词和中文 2/3 字片段），不依赖外部嵌入模型，保证离线可复现；语义能力有限，
  检索主要依靠 IK 全文检索和追溯关系，向量起补充作用。
- PowerContext 使用默认的 SQLite 存储（PowerContext 1.4.1 的 OceanBase 后端要求 MySQL 用户租户，seekdb 单机版不满足）。
- 一个任务对应一个 PowerContext Scope（标题 `sddctx/<工程>/<任务>`），PowerContext 没有删除接口；要从空状态重新开始，执行 `./sdd reset`。
- MiniMax 的输出不确定，每次实时运行生成的补丁可能不同。`evidence/T-101` 的完整运行和另外 5 次实时运行
  （`MiniMax-M3.1-Flash` 3 次、`MiniMax-M3` 2 次，`scripts/trials.sh`）都通过了全部测试，写出了 5 种不同的补丁，见
  [evidence/T-101/README.md](evidence/T-101/README.md)；评审按开发记录核对（`check-record`）。
  记录中思考内容只保存前 4000 字的摘要，签名不保存。
- 代码切分基于 Python `ast`，只支持 Python 工程；规格需要遵守 `specs/README.md` 的条目格式（`### ID 标题` + 状态/接口/关联）。
- PowerContext 没有开启认证，所有端口只绑定 127.0.0.1，按单机单用户使用设计。
- `docker-compose.yml` 固定了 Compose 项目名 `sddctx-minimax`，同一台机器上的另一份副本会使用同名的容器和数据卷：
  换用另一份副本前先在原来的副本执行 `./sdd reset`（或 `./sdd down`），不要同时运行两份。
- `spec-update-demo` 会临时修改 `project/specs/catalog.md`，运行期间不要同时编辑这个文件。

## 来源说明

业务工程、规格、测试和 sddctx 全部为本作品原创，采用 Apache-2.0（与仓库一致）。PowerContext 镜像从 PyPI 的 `powercontext==1.4.1`
发布包构建，未修改；seekdb 使用官方镜像。
