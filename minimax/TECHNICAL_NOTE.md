# 技术说明

## 模块结构

```
samples/T-101/task.toml ─┐                       ┌──────────── seekdb（sdd 库）────────────┐
project/（sdd.toml）─────┼─ ingest ── import ──→ │ sdd_chunks：片段 + IK 全文索引 ×3 + HNSW 向量 │
                         │                       │ sdd_links：references/implements/verifies │
                         │                       │ sdd_chunk_revisions、sdd_import_runs      │
                         │                       └───────────────┬──────────────────────────┘
                         └─ ContextBuilder ←── 混合检索 + 追溯查询 ┘   ←── 任务状态 ── PowerContext
                                  │ render                                          ↑ Task Outcome
                                  ↓                                                 │
                    context.md ──→ MiniMax 开发助手（agent）── 工具调用 ──→ 工程副本 ──→ verify（pytest）
```

| 文件 | 职责 |
|---|---|
| `ingest.py` | 按 `sdd.toml` 切片：规格条目（`### ID 标题` + 状态/接口/关联）、规格说明小节、代码符号（`ast`）、测试函数；抽取追溯关系 |
| `store.py` | seekdb 建表、增量导入（内容指纹 → 新增/更新/移动/删除，保留修订）、`DBMS_HYBRID_SEARCH`、追溯查询；每条 SQL 写记录 |
| `context.py` / `render.py` | 选择规格、代码、测试，合并任务状态，逐行核对来源，输出 Markdown/JSON |
| `state.py` | PowerContext：每个任务一个 Scope；Work Contract（目标、范围、完成标准）；每步一条 Task Outcome（已完成、验证结果、待办 + 机器可读状态） |
| `agent.py` / `minimax.py` | MiniMax 工具调用循环（read_file、search、edit_file、write_file、run_tests、finish），只读路径拦截，开发记录与回放 |
| `pipeline.py` / `cli.py` | 步骤编排（按 PowerContext 记录续跑）、修改前后验证、核对命令 |

## 上下文选择方式

1. **规格**：任务文本做一次混合检索（IK 全文 `title^3, keywords^2, content` + 向量 kNN，RRF 融合）。全文分数归一化后 ≥0.3，
   或 ≥0.15 且向量名次前三的为强命中；任务文本中直接写出的规格 ID 也算命中。命中中状态为“待实现/变更中”的是**目标**。
2. **扩展**：查 `sdd_links.references`，目标引用的条目是**约束**（T-101：API-002/003/004、CAT-004、DATA-001）；
   与目标同一能力分组（同一接口）的已实现条目进入回归范围。
3. **代码**：查 `implements` 找到实现这些条目的符号，再用目标条目的分组、标题、接口和代码标识做一次代码混合检索。
   实现同一接口已有条目最多的符号（至少达到最多者的一半）是**需要修改**的（`search_books`、`list_books`）；
   实现约束条目的符号是可复用的相关代码（`parse_bool`、`parse_int`、`available_copies`……）。
4. **测试**：查 `verifies`。验证目标条目的测试是目标测试，其余验证所选条目的测试是相关回归测试；验证时回归范围取全部非目标测试。
5. **状态**：从 PowerContext 读回最新 Task Outcome，列出已完成事项、验证结果和待办；把记录中的规格指纹与 seekdb 当前内容比较，
   规格被修改并重新导入后提示“之前的验证结果不再代表当前规格”，`run` 会重新执行后续步骤。
6. **核对**：每一处引用回到工程文件逐行比较，确认文件存在、内容与索引一致。

所有选择都来自 seekdb 的实际查询结果（每次 `context` 约 10 条 SQL，见 `seekdb-queries.jsonl`）；修改规格后不重新导入，
来源核对会报告不一致。

## 各项技术的分工

| 技术 | 在任务中的作用 |
|---|---|
| **seekdb** | 保存工程资料和索引（片段、全文与向量索引、追溯关系、修订历史）；`DBMS_HYBRID_SEARCH` 和追溯查询的结果直接决定上下文中的规格、代码和测试 |
| **MiniMax** | `MiniMax-M3.1-Flash` 读上下文，自主调用工具查看代码、修改 `library/`、运行目标与回归测试并迭代，最后给出说明；代码差异全部来自它的 `edit_file`/`write_file` 调用 |
| **PowerContext** | 保存任务进展和验证结果；`run`/`verify`/`develop` 每次开始都读回状态：跳过已完成步骤、取目标测试列表、把已有验证结果放进给 MiniMax 的上下文 |
| **sddctx** | 编排流程、执行工具调用、拦截对 `specs/`、`tests/` 等只读路径的写入、运行 pytest、记录全部调用 |

## 可信度保障

- **修改前失败是行为失败**：verify-before 要求目标用例全部失败且全部是断言失败，导入、夹具、收集错误都不算。
- **测试不被削弱**：MiniMax 只能写 `sdd.toml` 中 `code` 范围的文件；verify-after 再比较只读路径修改前后的指纹，并检查被测代码的差异与开发记录一致。
- **记录可核对**：开发记录保存每一轮的响应 ID、用量、工具调用及结果和最终差异；`check-record` 在干净副本上重放修改调用，得到与 `change.patch` 相同的 sha256。
- **成本与时延**：一次实时开发约 1 分钟、12 轮左右；上下文约 2 万字符，多轮对话命中 MiniMax 的输入缓存（记录中 `cache_read_input_tokens`）。
