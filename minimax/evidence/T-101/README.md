# T-101 运行记录

`scripts/run-sample.sh` 的一次完整运行（产物目录 `runs/evidence/T-101/` 复制到这里）：从 `./sdd reset` 后的空状态开始，实时调用 MiniMax，中途重启 seekdb 和 PowerContext 容器后从 PowerContext 的记录续跑。

- 代码版本：`d8b4de84b1a3`（运行时的 git 提交；测试日志头部同时记录被测工程目录的指纹 `tree_sha256`）
- 运行时间：2026-10-29T02:23:08 – 2026-10-29T02:25:30（UTC）
- 环境：Docker Compose；seekdb `5.7.25-OceanBase seekdb-v1.4.0.0`；PowerContext 1.4.1（API 契约 1.4）；sddctx 1.0.0（Python 3.12.14，pytest 9.1.1）；MiniMax `MiniMax-M3.1-Flash`（`https://api.minimax.cn/anthropic/v1/messages`）

## 必做项与证据

| 必做项 | 证据 | 结果 |
|---|---|---|
| 能够运行 | `console/00-up.txt` … `console/16-state-final.txt`：每个文件第一行是命令，最后一行是退出码 | 17 步，退出码全部为 0 |
| MiniMax 实际参与 | `minimax/session.md`（可读版）、`minimax/session.json`（原始记录）、`console/12-run-resume.txt`、`console/14-check-record.txt` | 13 轮对话，工具调用 21 次，其中成功修改 2 次；开发记录核对 8/8 项通过：重放记录中的修改调用得到的差异与 `change.patch` 相同（sha256 `aab378c43059`） |
| 上下文正确 | `context/context-initial.md`、`console/07-check-context.txt`；规格更新：`console/15-spec-update-demo.txt`、`context/context-spec-updated.md`、`context/context-spec-restored.md` | 按 `samples/T-101/expected.json` 核对 17/17 项通过（规格、需要修改的代码、相关代码、目标测试、回归测试、来源逐行核对）；修改 CAT-007 并重新导入后，上下文使用修订 r2 的新内容并提示 PowerContext 中的记录基于旧规格，恢复后回到原文（4/4 项通过） |
| 数据库实际参与 | `records/seekdb-queries.jsonl`、`console/02-import.txt`、`console/03-db-inspect.txt`、`console/04-search.txt`、`context/context-initial.md` 附录的检索结果表 | 本次运行在 seekdb 上执行 464 条 SQL，其中 13 次 `DBMS_HYBRID_SEARCH`；导入批次 #1, #2, #3；上下文中的规格、代码、测试都来自这些查询的结果 |
| 状态能够复用 | `console/05-state-empty.txt` → `08-run-until-verify-before.txt` → `09-restart.txt` → `10-state-after-restart.txt` → `11-context-after-restart.txt` → `12-run-resume.txt` → `13-run-again.txt`；`state/`；`records/powercontext-calls.jsonl`；`context/context-for-minimax.md` 第 4 节 | 从空状态开始；重启两个容器后读回 3 条记录（Work Contract + context、verify-before 两条 Task Outcome），`run` 跳过已完成的两步，从 develop 继续；交给 MiniMax 的上下文包含从 PowerContext 读回的修改前验证结果；verify-after 的目标测试列表取自 PowerContext 记录；全部完成后再次 `run` 四步都跳过 |
| 代码修改有效 | `tests/before/`、`tests/after/`（日志 + junit）、`snapshots/before/`、`snapshots/after/`、`change.patch` | 修改前：目标测试 0 passed, 25 failed，exit 1；断言失败 25，其他问题 0；回归测试 91 passed, 0 failed，exit 0。修改后：目标测试 25 passed, 0 failed，exit 0；回归测试 91 passed, 0 failed，exit 0 |

## 测试日志

命令在被测工程目录（`cwd`）中执行；修改前后运行的是同一组测试。

| 日志 | 命令 | 退出码 | 代码版本 | 工程目录指纹 | 结果 |
|---|---|---|---|---|---|
| `tests/before/target.log` | `python -m pytest -q -rfE -p no:cacheprovider --junitxml=runs/T-101/tests/before/target.junit.xml <15 个目标测试函数>` | 1 | `d8b4de84b1a3` | `8acd5172039b` | 0 passed, 25 failed，exit 1；断言失败 25，其他问题 0 |
| `tests/before/regression.log` | `python -m pytest -q -rfE -p no:cacheprovider --junitxml=runs/T-101/tests/before/regression.junit.xml --deselect <15 个目标测试函数>` | 0 | `d8b4de84b1a3` | `8acd5172039b` | 91 passed, 0 failed，exit 0；断言失败 0，其他问题 0 |
| `tests/after/target.log` | `python -m pytest -q -rfE -p no:cacheprovider --junitxml=runs/T-101/tests/after/target.junit.xml <15 个目标测试函数>` | 0 | `d8b4de84b1a3` | `ef7bbeb1f9f4` | 25 passed, 0 failed，exit 0；断言失败 0，其他问题 0 |
| `tests/after/regression.log` | `python -m pytest -q -rfE -p no:cacheprovider --junitxml=runs/T-101/tests/after/regression.junit.xml --deselect <15 个目标测试函数>` | 0 | `d8b4de84b1a3` | `ef7bbeb1f9f4` | 91 passed, 0 failed，exit 0；断言失败 0，其他问题 0 |

修改前的目标测试失败全部是断言失败（`AssertionError`），没有导入错误、夹具错误或收集错误。verify-after 比较了只读路径（`specs/**`、`tests/**`、`sdd.toml`、`pyproject.toml`）修改前后的指纹，二者一致；被测快照与修改前快照的差异和 MiniMax 开发记录中的最终差异 sha256 相同（见 `console/12-run-resume.txt`）。

## MiniMax 开发过程

- 模型 `MiniMax-M3.1-Flash`，接口 `https://api.minimax.cn/anthropic/v1/messages`（Anthropic 兼容 Messages API + 工具调用），结束状态 `finished`，模型响应累计 105 秒。
- 13 轮，工具调用：read_file 13 次、run_tests 3 次、edit_file 2 次、list_dir 1 次、search 1 次、finish 1 次。
- Token：输入 29054，缓存命中 256302，输出 5640。
- 修改的文件：`library/api/handlers.py`, `library/catalog.py`（+24 −3 行），差异 sha256 `aab378c430591f02bbbd4763d9e5d73eb6d69678bd6b4cf990ce09c02d8c1b10`。
- 提供给 MiniMax 的上下文：`context/context-for-minimax.md`（sha256 `e2fa5327af16`，与开发记录首条消息中的上下文相同），第 4 节是从 PowerContext 读回的进度和修改前验证结果。
- 助手在开发过程中自己运行的测试：`minimax/self-tests/`。

MiniMax 的完成说明（`finish` 调用的原文）：

> 实现 T-101：GET /books 增加可借状态与出版年份筛选。
>
> 改动文件：
> 1. library/catalog.py::search_books —— 新增 available / year_from / year_to 三个关键字参数：
>    - available 复用已有 available_copies()（DATA-001，只计 on_shelf 副本）做过滤，True 取 copies_available>0，False 取 copies_available=0（含无副本图书），缺省不筛选；
>    - 年份按闭区间过滤，两个参数可只给其一；
>    - year_from > year_to 抛 InvalidParameter("year_from")，即 400/invalid_parameter/field=year_from；
>    - 所有筛选在 sort 与分页之前执行，total 为筛选后总数；docstring 标注 实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008。
> 2. library/api/handlers.py::list_books —— 复用现有 parse_bool/parse_int 解析 available、year_from、year_to（非法值统一按 API-002 返回 400，field 为对应参数名），并透传给 search_books；docstring 补 CAT-007、CAT-008 标注。
>
> 保持原有行为：q/category/sort/page/page_size 的行为与错误提示不变，不带新参数时结果、排序、分页与改前一致，其他接口未改动。
>
> 测试结果：目标测试 25 passed / 0 failed；回归测试 91 passed / 0 failed（全量 116 passed）。

## seekdb 查询

`records/seekdb-queries.jsonl` 每行一条 SQL（语句、参数、返回行数、耗时），另有 13 行记录混合检索返回的片段和名次。

| 命令 | SQL 条数 | 其中 DBMS_HYBRID_SEARCH |
|---|---|---|
| `info` | 2 | 0 |
| `import` | 333 | 0 |
| `db-inspect` | 9 | 0 |
| `search` | 2 | 1 |
| `context` | 28 | 4 |
| `check-context` | 14 | 2 |
| `run` | 19 | 2 |
| `spec-update-demo` | 57 | 4 |

`import` 的语句大部分是逐个写入片段和修订。每生成一次上下文执行 13 条查询：2 次混合检索（规格、代码）和 11 条其他查询（导入批次、追溯关系、片段内容）；另外每次连接时执行一次 `CREATE DATABASE IF NOT EXISTS sdd`。

## PowerContext 调用

`records/powercontext-calls.jsonl` 每行一次 HTTP 调用（请求、状态码、响应摘要）。写入 6 次，读取任务记录 30 次。

| 方法 | 用途 | 次数 |
|---|---|---|
| POST | state: write task outcome | 4 |
| POST | state: create or reuse task scope | 1 |
| POST | state: write work contract | 1 |
| GET | state: find task scope | 32 |
| GET | state: read task records | 30 |
| GET | server info | 1 |

最终状态（`state/state-final.md`、`state/state-final.json`）：

| 位置 | source_id | 步骤 | 状态 | 摘要 |
|---|---|---|---|---|
| 2 | `T-101/outcome/001-context` | context | partial | 已生成任务上下文：目标 CAT-007, CAT-008；需要修改 library/api/handlers.py::list_books, library/catalog.py::search_books；目标测试函数 15 个 |
| 3 | `T-101/outcome/002-verify-before` | verify-before | partial | 修改前验证（工程指纹 8acd5172039b）：目标测试 25 个用例失败 25 个（断言失败 25）；回归测试 91 passed |
| 4 | `T-101/outcome/003-develop` | develop | partial | MiniMax 开发助手（MiniMax-M3.1-Flash，实时调用）用 13 轮工具调用完成修改：library/api/handlers.py, library/catalog.py（+24 −3 行，差异 sha256 aab378c43059）；助手自测 target 25 passed / 0 failed；regression 91 passed / 0 failed；all 116 passed / 0 failed |
| 5 | `T-101/outcome/004-verify-after` | verify-after | succeeded | 任务完成：修改后验证（工程指纹 ef7bbeb1f9f4）：目标测试 25/25 passed；回归测试 91 passed；规格和测试未被修改 |

位置 1 是 Work Contract（目标、修改范围、完成标准）。

## 目录

| 路径 | 内容 |
|---|---|
| `console/` | 每一步的命令、终端输出和退出码 |
| `context/` | 第一次生成的上下文（`.md` 和 `.json`）、重启后生成的上下文、交给 MiniMax 的上下文、规格更新前后的上下文 |
| `minimax/` | MiniMax 开发记录（`session.json` 原始记录，`session.md` 可读版）和助手自测日志 |
| `change.patch` | 修改前后快照的差异（相对 `project/`，可用 `patch -p1` 应用） |
| `snapshots/before/`、`snapshots/after/` | 修改前、修改后的完整工程快照 |
| `tests/before/`、`tests/after/` | 修改前后目标测试和回归测试的日志与 junit 报告 |
| `records/` | seekdb 查询记录、PowerContext 调用记录 |
| `state/` | 重启后读回的任务状态、最终任务状态 |
| `trials/` | 另外 5 次实时运行的终端输出、开发记录和代码差异（见最后一节） |

记录和终端输出中的路径相对 `minimax/`，指运行时的 `runs/` 目录；本目录保存的是其中的同一批文件，例如 `runs/T-101/develop/session-20261029-022334.json` 即 `minimax/session.json`，`runs/T-101/tests/before/target.log` 即 `tests/before/target.log`。

## 复核方法

以下命令在 `minimax/` 目录执行，不需要 MiniMax 密钥：

```bash
./sdd up
./sdd check-record T-101 --session evidence/T-101/minimax/session.json --patch evidence/T-101/change.patch
scripts/project-tests.sh project                          # 修改前：目标测试 25 个失败，回归测试 91 个通过
scripts/project-tests.sh evidence/T-101/snapshots/after   # 修改后：全部通过
scripts/run-sample.sh --replay                            # 完整流程，develop 步骤回放这份开发记录，产物在 runs/evidence-replay/T-101/
```

有密钥时，`scripts/run-sample.sh` 从空状态完整重跑（MiniMax 每次写出的代码可能不同，以新的开发记录为准）。

## 多次实时运行

`scripts/trials.sh` 用独立的任务 ID 和 PowerContext Scope 重复完整流程（context → verify-before → develop → verify-after），检查 MiniMax 能否稳定完成。5 次全部通过（修改后目标测试 25/25、回归测试 91 passed，规格和测试未被修改）；连同上面这次运行，6 次运行写出了 5 种不同的差异（见表中的 sha256），都通过了全部测试。

| 任务 ID | 模型 | 代码版本 | 结果 | 全流程耗时 | 轮数 | 成功修改 | 差异 | 差异 sha256 | 模型响应耗时 | Token（输入 / 缓存命中 / 输出） |
|---|---|---|---|---|---|---|---|---|---|---|
| `T-101-default-1` | `MiniMax-M3.1-Flash` | `f94b65358bb9` | 全部步骤通过（退出码 0） | 67s | 12 | 2 | +26 −3 | `598c196a34d0` | 59 秒 | 25995 / 257280 / 5238 |
| `T-101-default-2` | `MiniMax-M3.1-Flash` | `f94b65358bb9` | 全部步骤通过（退出码 0） | 133s | 15 | 2 | +22 −3 | `593a0c9167b0` | 129 秒 | 31000 / 315929 / 4271 |
| `T-101-default-3` | `MiniMax-M3.1-Flash` | `f94b65358bb9` | 全部步骤通过（退出码 0） | 68s | 13 | 2 | +25 −3 | `d9cd48a07415` | 65 秒 | 24266 / 251936 / 4864 |
| `T-101-m3-1` | `MiniMax-M3` | `f94b65358bb9` | 全部步骤通过（退出码 0） | 41s | 8 | 2 | +25 −3 | `a1e109059e7b` | 38 秒 | 17448 / 103680 / 1717 |
| `T-101-m3-2` | `MiniMax-M3` | `f94b65358bb9` | 全部步骤通过（退出码 0） | 73s | 8 | 2 | +25 −3 | `d9cd48a07415` | 70 秒 | 18392 / 108577 / 1835 |

这 5 次运行在代码版本 `f94b65358bb9` 上进行，与上面的运行（`d8b4de84b1a3`）之间唯一的代码改动是 `scripts/run-sample.sh` 中默认输出目录的计算（修复 live 模式下不指定 `OUT` 时脚本直接退出的问题），多次运行不经过这个脚本。

每次的终端输出、开发记录和代码差异在 `trials/<任务 ID>/`（`console.txt`、`session.json`、`change.patch`），汇总在 `trials/summary.tsv`。每份记录都可以核对，例如：

```bash
./sdd check-record T-101-m3-1 --session evidence/T-101/trials/T-101-m3-1/session.json --patch evidence/T-101/trials/T-101-m3-1/change.patch
```
