会话 05b：修正会话 05 审阅时发现的盲区排序问题和雷达页的几处显示问题。

先读 `docs/DEVLOG.md` 里会话 05 的记录。环境同前：seekdb 127.0.0.1:10800，PowerContext 127.0.0.1:18801，密码在 `qoder/.env`；不要启停开发用的容器。开发库 `examradar` 里的 db101 样例资料已经导入，不需要重导。

我在开发库上重新跑了一次分析：10 个判定、11 道题的归属、盲区第一 t04 都和设计真值一致，单元测试和集成测试也都通过。下面这些要改。

## 本会话和别的会话同时进行

- 会话 07 在另一份目录里做 M3，会话 08b、09b 在各自的目录里写文档和网站。之后由产品负责人合并。
- **只改这些文件**：`app/examradar/coverage.py`、`app/static/radar.html`、`app/tests/test_coverage.py`、`app/tests/test_integration.py`、`scripts/calibrate.py`（如果它依赖顺序或理由的措辞），以及在 `docs/DEVLOG.md` 末尾追加"会话 05b"一节。
- 不要改 `seekdb.py`、别的页面、`config.py`、`.env.example`、`docker*`、`README.md`、`docs/VALIDATION.md`、`scripts/e2e_verify.py`、`site/`。
- 端口：开发服务器只用 **18809**。18800 是会话 08b 的，18802、18803 是会话 07 的，18805–18808 是别的会话的。

## 要改的问题

1. **"载入上次分析"时盲区清单没有排序（bug）**
   - 现象：雷达页点"载入上次分析"，盲区清单按 t01…t10 排，t04（盲区分数 25.00）排在第 4 名；标题写的却是"按 考试权重 × 未覆盖度 排序"。
   - 原因：`analyze()` 返回前按 `blind_spot_score` 排了序（`coverage.py` 里 `topic_results.sort(...)`），`get_latest()` 读的是 `seekdb.py` 里 `ORDER BY topic_id` 的结果，没有再排。
   - 改法：两个接口返回同样的顺序（盲区分数从高到低，同分按 `topic_id`），排序只在 `coverage.py` 的一个地方写。页面上的"排名"列以接口顺序为准。
   - 测试：
     - 构造数据单测：排序函数在同分、全 0 时的顺序；
     - 集成测试：`get_latest()` 的 `items[0]` 是 t04，并且整个顺序和刚跑完的 `analyze()` 一致。
   - 会话 07 的复习教练也通过 `get_latest()` 读覆盖结果，所以接口顺序很重要。
2. **雷达图轴标签从词中间断开，底部标签压住图例**
   - 1440×900 下看到的：`t09 故障恢复：WAL 与 ARIE` / `S`、`范式（3N` / `F、BCN` / `F）`、`事务的 A` / `CID 特性`。
   - 底部 t06 的标签和图例"覆盖度 / 考试权重"重叠。
   - 要求：
     - 只在"："、"与"、"（"、空格这些位置换行，英文单词和 3NF、BCNF、WAL、ARIES、MVCC 这类缩写不能拆开；
     - 图例不压任何标签；
     - 所有标签都在图表容器内。
   - 图表改用 SVG 渲染器（`echarts.init(el, null, {renderer: "svg"})`），这样能用 DOM 量出来。
3. **判定理由的措辞**
   - 刚好等于阈值时写成了"考点词比例 1/2 高出阈值 0.5 0.00"，高于阈值时是"高出阈值 0.5 0.50"。改成"考点词比例 1/2，达到阈值 0.5"或者"高于阈值 0.5"这类通顺的说法。
   - 理由太长。t03 的理由把每段证据的完整章节路径都列一遍，例如"03-索引与B+树.md·第3章 索引：B+树与哈希索引（课堂笔记） > 3.1 为什么需要索引"重复了 7 次。
     - 改成每个考点词写"文档名·最后一级标题"，最多 2 处，再写"等 N 段"；
     - 找到 / 没找到的考点词、支撑段数和字数、离阈值的距离照旧要有。
   - 理由是分析时写进库里的，改完在开发库上重新跑一次分析。
4. **盲区清单的表头**："排名""考试权重""盲区分数"的表头和"查看理由"折成了两行，改成不折行。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- `cd app && uv run pytest` 和 `cd app && export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过。
- 在开发库上重新分析一次：
  - 10 个判定、11 道题的归属仍与设计真值一致；
  - 接口和"载入上次分析"的盲区清单第一名都是 t04；
  - 把全部 10 条判定理由贴进 DEVLOG。
- 浏览器验证（`?source=auto`，1440×900 和 768×1024 两种宽度，点"载入上次分析"之后）：
  - 每个轴标签（SVG 的 text 元素）的 `getBoundingClientRect()` 都在图表容器内，并且和图例不相交；
  - 标签文字里没有被拆开的英文单词或缩写；
  - 盲区清单的表头和"查看理由"单元格只有一行高；
  - 盲区清单第一行是 t04。

  截图，用 Read 看一遍，在 DEVLOG 里写看到了什么。
- 会话结束前关掉你启动的进程。`git status` 里只有上面允许改的文件。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。
- **开发服务器**：Bash 设为后台运行（run_in_background），命令是 `cd app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18809`，末尾不要加 `&`。用 `curl -s http://127.0.0.1:18809/api/health` 确认它起来了；结束时用 PID 结束它。
- 接口请求都带 `X-ExamRadar-Source: auto`。
- **浏览器验证**：`.cache/scratch/pwvenv` 里已经装好 playwright，用本机 Chrome（`channel="chrome"`），脚本用 `.cache/scratch/pwvenv/bin/python` 运行。截图存到 `.cache/scratch/`。
- 临时脚本放在 `qoder/.cache/scratch/`（已被 git 忽略），`rm` 不在允许的命令里。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip，用 uv。

结束前在 `docs/DEVLOG.md` 末尾追加本会话记录：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。不要修改 `dev-records/` 和 `samples/`。
