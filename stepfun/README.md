# 端侧知识库：seekdb × 阶跃星辰

一个可运行的小型知识库 Web 应用：

- **文档与查询的向量都在浏览器里计算**。模型是 multilingual-e5-small（中英文），由 Transformers.js 4 + ONNX Runtime Web 在 Web Worker 中运行。优先使用 WebGPU（FP16），WebGPU 不可用时自动降级到多线程 WASM（INT8），界面上始终显示当前后端和降级原因。没有云端推理，也没有预计算的向量或结果。
- **向量、原文和元数据存放在 seekdb**，通过 seekdb-js 访问。默认使用本目录脚本启动的本地 seekdb 容器。
- **混合检索在 seekdb 内完成**。每次查询是一条 `DBMS_HYBRID_SEARCH.SEARCH` 调用，向量路（HNSW）、全文路（IK 分词）和 RRF / 加权融合都由 seekdb 执行，客户端不合并两份结果列表。
- **支持增量导入**。内容未变的文档跳过向量化；内容变化的文档在提交时原子替换旧分块；提交前确认新分块已能被检索到。每个知识库都有版本号，切换知识库或并发导入时，界面不会显示过期结果。

技术说明（模型与量化、端侧运行、seekdb 使用、状态与优化、测量表）见 [TECHNICAL.md](TECHNICAL.md)。完整测量报告见 [bench/results/final__report.md](bench/results/final__report.md)。

## 快速开始

需要：Node.js ≥ 20、Docker、Google Chrome（WebGPU 需要 Chrome 113 及以上；测试使用 Chrome 156），约 1.3 GB 磁盘空间（模型约 820 MB，node_modules 约 500 MB；`npm run quantize` 另需约 350 MB）。

```bash
cd stepfun
npm install
npm run db:start       # 启动独立的 seekdb 容器 stepfun-seekdb（宿主机端口 12881，数据卷 stepfun-seekdb-data）
npm run fetch-model    # 下载固定 revision 的模型文件到 models/（FP32 + FP16 + INT8，约 820 MB）
npm start              # http://localhost:5280
```

用 Chrome 打开 <http://localhost:5280>：

1. 右上角徽标显示推理后端（如“推理后端：WebGPU · FP16”或“WASM · INT8 · 8 线程（自动降级）”）、模型加载耗时和 seekdb 版本。
2. 点“示例文档（9 篇）”导入示例，或拖入 `.txt / .md / .jsonl` 文件，或粘贴文本。“评测语料 A / B”是 908 段 MIRACL 中英文段落的两半，可用来演示增量导入。
3. 输入问题检索。结果卡片会标出该文档在全文路和向量路的名次（RRF 融合）或两路的加权得分（加权求和融合）；结果上方显示查询向量化、seekdb 检索、网络与渲染各阶段的耗时，以及结果对应的知识库版本。

- **无法访问 Hugging Face 时**：`HF_ENDPOINT=https://hf-mirror.com npm run fetch-model`。
- **想看 WASM 路径**：`chrome --disable-gpu`，或打开 <http://localhost:5280/?backend=wasm>。
- **停止数据库**：`npm run db:stop`。

### 模型文件从哪里来

- **默认**：`npm run fetch-model` 从 Hugging Face 下载 [`Xenova/multilingual-e5-small`](https://huggingface.co/Xenova/multilingual-e5-small) 在 revision `761b726d` 下的文件，放到 `models/`，再由本服务以同源静态文件提供给浏览器。首次加载后，浏览器会把文件缓存进 Cache Storage。
- **本地缺文件时**：浏览器会直接从 huggingface.co 下载同一 revision。
- **自己量化**：`npm run quantize`（需要 [uv](https://docs.astral.sh/uv/)）从 FP32 文件生成 INT8 和 FP16 两个变体，写到 `models/local/multilingual-e5-small/`。在设置里把“模型文件”切换为“本地量化”，或使用 URL 参数 `?source=local`，应用就会加载这两个文件。

## 配置

**服务端环境变量**（见 `server/config.mjs`）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` / `HOST` | `5280` / `127.0.0.1` | Web 服务地址 |
| `SEEKDB_HOST` / `SEEKDB_PORT` | `127.0.0.1` / `12881` | seekdb 服务地址 |
| `SEEKDB_USER` / `SEEKDB_PASSWORD` | `root` / 空 | seekdb 账号 |
| `SEEKDB_DATABASE` | `stepfun_kb` | 应用使用的数据库，启动时自动创建 |
| `SEEKDB_PATH` | 空 | 设置后改用 seekdb-js 嵌入式模式，打开该目录，不需要容器。见“已知问题” |
| `VISIBILITY_TIMEOUT_MS` | `5000` | 导入提交时等待异步向量索引的上限；超时后改为显式刷新 |

**数据库脚本**：`scripts/seekdb-docker.sh start|stop|status|logs|reset`，可用 `SEEKDB_CONTAINER`、`SEEKDB_PORT`、`SEEKDB_IMAGE`、`SEEKDB_MEMORY`、`SEEKDB_CPU` 覆盖默认值。默认镜像是测试过的 `oceanbase/seekdb:1.4.0-100000172026082615`。脚本只操作自己创建的容器。

**页面 URL 参数**（也可在页面的“设置”里修改）：

| 参数 | 取值 |
|---|---|
| `backend` | `auto`（默认，WebGPU 优先）、`webgpu`、`wasm` |
| `dtype` | `auto`（WebGPU→FP16，WASM→INT8）、`fp32`、`fp16`、`int8` |
| `source` | `hf`（默认）、`local` |

“设置”里还可以调整向量化批大小、索引刷新方式（探测 / 显式刷新）和检索调用方式（单次 SEARCH / SDK `hybridSearch()`）。

## 测试与测量

先启动数据库和服务（`npm run db:start`、`npm start`），再运行：

```bash
npm test                           # 存储层测试（直接连 seekdb）：跳过、替换、中止、并发导入同一文档（新增 / 变更）、两种融合、删除
node bench/e2e.mjs                 # 界面端到端测试：GPU 可用与 --disable-gpu 各跑一遍
npm run bench -- full --stamp final  # 浏览器测量：加载、批量、质量、导入、查询、降级（Chrome，约 1 小时）
npm run bench:db -- --stamp final    # seekdb 侧测量（需要先跑过 bench 的 query 计划，建立 bench_query 知识库）
npm run model-size                   # 模型文件大小与压缩比
npm run quantize                     # 量化并测 CPU 侧保真度（可选）
npm run report -- --stamp final      # 汇总为 bench/results/final__report.md
```

- **端到端测试**覆盖：后端选择与降级提示、示例导入、中英文与全文检索、RRF 与加权求和两种融合、粘贴新文档后立即可检索、未改动文档重新导入时全部跳过、跨知识库隔离、删除文档。
- **原始测量数据**是 `bench/results/final__*.json`。每次浏览器运行的 Chrome 版本、启动参数、GPU 适配器和机器负载记录在 `final__runs-*.json`。重跑某个计划时，结果文件会被覆盖，运行日志按计划分文件保存。

## 评测集

`eval/data/` 由 `eval/build_eval_set.py` 从 [MIRACL](https://huggingface.co/datasets/miracl/miracl) v1.0 dev 生成（Apache-2.0，段落来自 Wikipedia，CC BY-SA）：

- 随机种子 2026，抽取 60 条中文和 30 条英文查询；
- 语料是这些查询的全部标注段落，共 908 段：594 段中文、314 段英文；
- 共 921 条标注：215 条相关，706 条困难负例。

生成日志见 `eval/data/build.log`。指标是 Recall@10、nDCG@10、MRR@10，在文档级（同一文档的多个分块去重）计算。

## 目录结构

```
server/    Node 服务：静态文件（含 COOP/COEP 跨源隔离头）+ JSON API；store.mjs 是全部 seekdb 访问
web/       页面与 Worker：embed-worker.js（推理）、pipeline.js（导入/检索流程）、app.js（界面）、bench.*（测量页）
scripts/   seekdb 容器、模型下载、量化（quantize.py）、模型体积
bench/     e2e 测试、浏览器测量驱动、seekdb 测量、报告生成；results/ 是测量结果
eval/      评测集与生成脚本
samples/   示例文档（自写）
```

## 已知问题

- **嵌入式模式**：在本机（macOS 26.4，Apple Silicon）上，seekdb-js 嵌入式模式启动时报 `io_adapter pwrite failed`（-4006）后退出，所以默认用 Docker 运行 seekdb 服务端。`SEEKDB_PATH` 路径保留在代码里，但未在本机跑通。
- **`DBMS_HYBRID_SEARCH` 引号问题**：全文查询文本中的引号会被原样拼进 seekdb 生成的 SQL，导致语法错误。服务端在传给 seekdb 前会去掉 `\ ' " \``（`sanitizeFulltext`）。
- **WebGPU 首次推理较慢**：WebGPU 首次推理要编译着色器管线，耗时数百毫秒。模型加载阶段会先做一次预热推理，这段时间不会落到用户的第一次查询上。
