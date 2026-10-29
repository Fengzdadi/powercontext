# 验证样例 T-101：图书检索增加可借状态和出版年份筛选

业务工程是 [`project/`](../../project/)（校园图书馆借阅服务，Python 标准库 + pytest，原创）。任务定义在 [`task.toml`](task.toml)，
上下文必须包含的来源在 [`expected.json`](expected.json)（`sddctx check-context T-101` 按它逐项核对）。

## 1. 任务描述

**要改什么**：为 `GET /books` 增加两个筛选条件。

- `available`：`true` 只返回至少有一本在架副本的图书，`false` 只返回没有在架副本的图书；取值按布尔参数规则解析，不合法时返回 400。
- `year_from`、`year_to`：按出版年份闭区间筛选，可以只给一个；不是整数、或者 `year_from > year_to` 时返回 400。
- 新条件可以与关键词、分类组合；筛选在排序和分页之前生效。

**必须保持的原有行为**：

- 不带新参数时，`GET /books` 的结果、排序和分页与修改前完全一致；
- `q`、`category`、`sort`、`page`/`page_size` 的现有行为和错误提示不变，`total` 是筛选后的总数；
- 图书详情、借阅、归还、续借、罚款等其他接口的行为不变（91 个回归测试覆盖）。

任务描述只用自然语言，没有写规格编号；适用的规格、要改的代码和要跑的测试都由上下文模块从 seekdb 检索得出。

## 2. 有效规格

| 角色 | 条目 | 来源 |
|---|---|---|
| 目标（状态：待实现） | CAT-007 可借状态筛选 | `project/specs/catalog.md:61-78` |
| 目标（状态：待实现） | CAT-008 出版年份区间筛选 | `project/specs/catalog.md:80-90` |
| 约束（被目标条目引用） | API-002 错误格式 | `project/specs/api.md:15-26` |
| 约束（被目标条目引用） | API-003 布尔查询参数 | `project/specs/api.md:30-38` |
| 约束（被目标条目引用） | API-004 整数查询参数 | `project/specs/api.md:40-47` |
| 约束（被目标条目引用） | CAT-004 分页 | `project/specs/catalog.md:40-49` |
| 约束（被目标条目引用） | DATA-001 副本状态 | `project/specs/data.md:5-19` |
| 同一接口的已实现条目 | CAT-001、CAT-002、CAT-003、CAT-006 | `project/specs/catalog.md` |

规格条目的格式和追溯约定见 [`project/specs/README.md`](../../project/specs/README.md)。

## 3. 初始数据

- 业务工程：`project/`（25 个规格条目，`library/` 下 13 个源文件，7 个测试文件）。种子数据 `project/library/data/seed.json`：
  16 本图书、21 个副本、5 位读者、9 条借阅记录；测试中的“今天”固定为 2026-10-15。
- seekdb：空库。`./sdd import` 建表并导入 161 个片段（规格条目 25、规格说明 3、代码 52、测试函数 74、测试模块 7）和 569 条追溯关系。
- PowerContext：空状态，Scope `sddctx/campus-library/T-101` 不存在；第一次生成上下文时创建。

## 4. 上下文必须包含的来源

| 类别 | 必须包含 | 来源 |
|---|---|---|
| 规格（目标） | CAT-007、CAT-008 | 见上表 |
| 规格（约束） | API-002、API-003、API-004、CAT-004、DATA-001 | 见上表 |
| 代码（需要修改） | `library/catalog.py::search_books` | `project/library/catalog.py:53-84` |
| 代码（需要修改） | `library/api/handlers.py::list_books` | `project/library/api/handlers.py:16-33` |
| 代码（可复用） | `library/api/params.py::parse_bool`、`parse_int` | `project/library/api/params.py:15-27`、`30-52` |
| 目标测试 | `tests/test_api_books_filters.py`（15 个测试函数，25 个用例） | `project/tests/test_api_books_filters.py` |
| 回归测试 | `tests/test_api_books.py`、`tests/test_catalog_search.py`、`tests/test_api_params.py` | `project/tests/` |

除此之外，上下文还必须包含任务状态（已完成事项、待办、已有验证结果，来自 PowerContext），并且引用的每一处来源都要与工程文件逐行一致
（`check-context` 的最后两项）。

## 5. 操作步骤

在 `minimax/` 目录执行（需要 Docker 和 Compose v2）：

```bash
./sdd up                                   # 启动 seekdb、PowerContext，构建 sddctx 镜像
./sdd import                               # 导入工程资料
./sdd context T-101                        # 生成上下文（第一次运行时在 PowerContext 中写入 Work Contract 和第一条记录）
./sdd check-context T-101                  # 按 expected.json 核对
./sdd run T-101 --stop-after verify-before # 修改前验证后停止
./sdd restart                              # 重启 seekdb 和 PowerContext 容器
./sdd state T-101                          # 读回任务状态：已完成 context、verify-before，下一步 develop
./sdd run T-101                            # 从 PowerContext 记录的下一步继续：MiniMax 修改代码，然后修改后验证
./sdd check-record T-101                   # 核对 MiniMax 开发记录与代码差异
./sdd spec-update-demo T-101               # 修改 CAT-007 → 重新导入 → 上下文使用新内容 → 恢复
```

没有 MiniMax 密钥时，把 `./sdd run T-101` 换成 `./sdd run T-101 --replay evidence/T-101/minimax/session.json`：
按提交的开发记录重放 MiniMax 的修改调用，后续验证照常执行。上面的步骤也可以用 `scripts/run-sample.sh`（或加 `--replay`）一次跑完。

手动检查规格更新：编辑 `project/specs/catalog.md` 中 CAT-007 的验收条目 → `./sdd import`（输出“更新 spec:CAT-007 → 修订 r2”）→
`./sdd context T-101`（1.1 节中 CAT-007 显示修订 r2 和新内容，第 4 节提示规格在上次记录后发生变化）→ 恢复文件后再导入一次。

## 6. 预期结果

| 步骤 | 预期 |
|---|---|
| import | 导入批次 #1，161 个片段、569 条追溯关系 |
| context / check-context | 目标 CAT-007、CAT-008；需要修改 `search_books`、`list_books`；目标测试 15 个；17/17 项核对通过 |
| verify-before | 目标测试 25 个用例全部失败，且全部是断言失败（没有导入、夹具、收集错误）；回归测试 91 passed |
| restart + state | 记录仍在：已完成 context、verify-before 及其验证结果，待办 develop、verify-after |
| run（续跑） | 跳过已完成的两步；MiniMax 修改 `library/catalog.py` 和 `library/api/handlers.py`；修改后目标测试 25 passed、回归测试 91 passed，规格和测试文件未变 |
| run（再次） | 四个步骤都按 PowerContext 记录跳过 |
| check-record | 开发记录包含任务和上下文，来自 MiniMax 接口，重放修改调用得到与 `change.patch` 相同的差异 |
| spec-update-demo | CAT-007 修订 r2 进入上下文；恢复后修订 r3、内容回到原文 |

一次完整运行的实际输出在 [`evidence/T-101/`](../../evidence/T-101/)。

## 7. 重置

```bash
./sdd reset    # 删除容器和数据卷（seekdb 资料、PowerContext 任务状态）以及 runs/，回到空状态
```

`project/` 本身不会被修改：MiniMax 在 `runs/T-101/snapshots/after/`（工程副本）里工作。`spec-update-demo` 会临时修改
`project/specs/catalog.md`，结束时（包括出错时）恢复原文。
