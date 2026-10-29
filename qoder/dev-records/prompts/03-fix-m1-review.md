会话 03：修复 M1 审阅发现的问题（检索排序调试、切块清洗、导入、工程）。本会话不做新功能。

先读 `docs/DEVLOG.md` 了解当前状态。环境和上次一样：seekdb 在 127.0.0.1:10800，PowerContext 在 127.0.0.1:18801，密码在 `qoder/.env`。不要启停任何容器。

## 审阅意见

我复核了 M1：47 个测试通过；试卷 11 题、合计 100 分；没有残留部首。下面这些要先改。

### A. 检索质量（验收没过的两条）

我用 `/api/search` 复跑了 6 条验收检索（括号里是关键词排名和语义排名）：

- "脏页表"：第 6 页（2, 1）排在第 7 页（1, 3）前面，两者 RRF 分数几乎相同。
- "先写日志原则"：第 3 页（1, 2）排在第 4 页（2, 1）前面。第 4 页的标题就是"先写日志原则（WAL）"。
- "B+树插入时结点分裂"：3.3 节（2, 1）只是险胜 3.6 节（1, 3）。

验收要求第一条命中，现在不算通过。请按下面的方向改，**不许针对样例写特判**：

1. **幻灯片标题被并进了正文**（见 B.1）。修好之后标题才可用。
2. **查询向量没有用 BGE 的检索指令**：bge-small-zh-v1.5 推荐查询前加"为这个句子生成表示以用于检索相关文章："，文档不加。短查询的语义排名很可能就是这里差的。改完后对比前后排名。
3. **标题加权**：给 `heading` 建 IK 全文索引，检索时用 `multi_match`，字段 `["content", "heading^N"]`，或者在 bool 里用 should 子句给标题命中加分。我在 seekdb 1.4.0 上试过：
   - `match_phrase` 不支持，报 1235；
   - `multi_match` 要求列出的每一列都有 FULLTEXT 索引，否则报 1191。
   boost 的写法请用 `GET_SQL` 确认真的生效。
4. 把 6 条验收检索写成集成测试（`integration` 标记），断言第一条出处，以后就不会退化。
5. DEVLOG 里贴出修改前后 6 条检索前 3 名的出处、两路分数和排名。如果用正当方法还有一条过不了，用数据说明原因，不要硬凑。

### B. 切块与清洗

1. `clean_extracted_text` 里 `([\u4e00-\u9fff])\s+([\u4e00-\u9fff])` 的 `\s` 包括换行，第 2、3、7、9 页的标题和下一行正文被拼成了一行（库里的 heading 是"日志记录与日志文件日志按时间顺序追加写入，……"）。只删同一行内汉字之间的空格。
2. 不要对整段文本做 NFKC：它会把全角标点变成半角（库里成了"(5 分)""第7讲故障恢复:日志"）。只把康熙部首区（U+2F00–U+2FDF）和 CJK 部首补充区（U+2E80–U+2EFF，例如 ⻚→页）的字符逐个映射成标准汉字。
3. **PDF 解析换成 `pypdfium2`**（Apache-2.0 / BSD-3-Clause），去掉 PyMuPDF（AGPL-3.0）。本项目要以 Apache-2.0 开源，还要打进 Docker 镜像分发，AGPL 依赖不合适。我实测过，pypdfium2 对样例 PDF 直接给出标准汉字，但段内有硬换行，每页末尾有页码。B.2 的映射继续保留，作为兜底。
4. 去掉页脚页码，也就是每页最后一行单独的数字。

### C. 导入

1. **`scripts/load_sample.sh` 把 `syllabus.txt` 当成 notes 导入了**：考试范围是覆盖分析的输入，不是课程资料。它进了知识库，就成了"两阶段锁能不能避免死锁"的第 3 条结果；到了 M2，每个知识点都会被范围文本自己"覆盖"。从脚本里去掉，再删掉库里已经导入的这份。
2. **导入要原子化**：现在先写 `documents`，再逐块向量化、写 `chunks`，中途失败会留下半个文档，而 sha256 去重又让它再也导入不了。改成全部切块、向量化成功后再写；写入失败时删掉这个文档已写的行。
3. 去重改成 `(course_id, sha256)`：同一个文件可以导入不同的课程。
4. 主键 `_gen_id() + chunk_index` 在同一毫秒内可能撞，改用 `AUTO_INCREMENT`（先确认 seekdb 的 heap 表支持）。
5. `POST /api/documents` 是 `async def`，却在事件循环里同步做向量化和写库，导入期间整个服务会卡住。改成普通 `def`。
6. 输入校验：`doc_kind` 只允许 notes / slides / paper / exam；文件只收 .md / .txt / .pdf；大小上限 30 MB。
7. 写库用一个连接加 `executemany`，不要每个 chunk 新建一个连接。

### D. 问笔记页

1. 出处要有**文件名**（现在只有标题路径和页码），格式是"文件 · 第 N 页 · 标题路径"。
2. 正文按 Markdown 渲染：或者引入一个小的 Markdown 库并在 static 里写清版本和来源，或者至少去掉 `##`、`**` 标记。
3. 默认显示前 5 条，"显示更多"展开；某一路没有命中时显示"—"，不要显示 0.0000。

### E. 工程

1. **Python 版本**：`uv sync` 选了 CPython 3.13，BRIEF 和 Dockerfile 都是 3.12。加 `app/.python-version`（3.12），`requires-python` 改成 `>=3.12,<3.13`。
2. **开发依赖**：pytest 放在 `[project.optional-dependencies]` 里，`uv sync` 默认不装，干净机器上 `uv run pytest` 会失败，或者用上 PATH 里别的 pytest。改成 `[dependency-groups] dev`（uv 默认安装）。
3. **`.env.example` 写本机开发用的地址**：`SEEKDB_HOST=127.0.0.1`、`SEEKDB_PORT=10800`、`POWERCONTEXT_URL=http://127.0.0.1:18801`、`APP_HOST=127.0.0.1`。compose 已经在 `environment:` 里写死了容器内地址，注释里说明哪些变量只给 compose 用。
4. **时间**：seekdb 容器的时区是 +08:00，`created_at` 存的是服务器本地时间，不带时区（首页显示的导入时间比本机早 12 小时）。统一由 app 写 UTC 时间；接口返回带时区的 ISO 字符串；前端按浏览器本地时区显示。M2 的"按天统计"按浏览器时区分天，在 API 参数里传时区。
5. **查库不要在命令里写密码**：上个会话把密码直接写进了命令。加一个 `python -m examradar.cli sql "SELECT ..."` 子命令，从配置读取连接信息，以表格形式打印结果。之后的验证和 README 里的查库步骤都用它。

Docker 和 compose 的问题在 M4 一起处理，本会话不用动。

## 执行命令的注意事项（非交互模式下的权限规则；上个会话因此浪费了二十多轮）

- 带 `2>&1`、`2>/dev/null`、`| head` 这类重定向或管道、末尾加 `&` 的命令都会被拒绝；用 `&&` 串联时每一段都必须在允许列表里。直接运行命令本身，输出会完整返回给你。
- 前置环境变量的写法也会被拒绝，比如 `EXAMRADAR_IT=1 cmd`。用 `export EXAMRADAR_IT=1 && cmd`。
- 不要用 pip，依赖一律用 `uv add` / `uv sync`。
- 开发服务器用 Bash 的后台运行方式启动：`.venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800`，命令里不要加 `&`。结束时用 PID 结束你自己启动的进程，不要用 pkill / killall。

## 数据和表结构

切块和清洗变了，库里 db101 课程的数据要清掉重新导入。可以加一个 `python -m examradar.cli delete-course db101` 子命令，删除这门课的 documents、chunks 和 usage_events。

表结构如果变了（新增全文索引、主键改 AUTO_INCREMENT、时间列），开发库可以直接删表重建再导入样例。启动时的建表逻辑要能在空库上一次建好。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- 6 条验收检索的第一条结果全部命中期望出处，`_keyword_score` 不为空，对应的集成测试通过。DEVLOG 里有修改前后的对比表：每条检索前 3 名的出处、两路分数和排名。
- 课件 9 页的 heading 都是该页第一行标题；库里的正文保留全角标点；没有残留部首；没有页脚页码。
- `syllabus.txt` 不在知识库里；`scripts/load_sample.sh` 导入 6 份资料，再运行一次不重复入库；试卷仍是 11 题、合计 100 分。
- 新建一个空的虚拟环境，`uv sync` 后 `uv run pytest` 能直接跑（Python 3.12，pytest 来自 dev 依赖组）；`export EXAMRADAR_IT=1 && uv run pytest -m integration` 通过。
- `python -m examradar.cli sql "SELECT doc_kind, COUNT(*) FROM chunks GROUP BY doc_kind"` 能打印结果，输出里没有密码。
- 问笔记页的结果显示文件名、页码和标题路径，正文按 Markdown 渲染。用浏览器实际打开看过，开发服务器跑在 18800。

结束前在 `docs/DEVLOG.md` 追加本会话记录：做了什么、遇到的问题和解决办法、验收结果。不要修改 `dev-records/` 和 `samples/`；会话结束前关掉你启动的进程。
