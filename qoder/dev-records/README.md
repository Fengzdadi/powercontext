# Qoder 开发记录

本项目（考前雷达 ExamRadar）的需求拆解、技术设计、编码和调试由 **Qoder CLI**（`qoderclicn` 1.1.80，Qoder CN）完成。
产品负责人只负责写需求、提供样例数据和接口实测备忘、审阅和验收，不直接写应用代码。

- **Qoder 账号**：个人版（用户名不公开，以下面的 UID 为准）
- **账号 UID**：`01a184e5-b79a-7087-aa96-d00a66126283`

公开记录中的 Qoder 用户名已替换为 [redacted]。

## 关键环节截图

下面是 Qoder CLI 自己界面的截图：会话结束后用 `qoderclicn --resume` 重放会话历史并渲染成图片，做法见后文"截图是怎么来的"。全部截图见后文的表格。

**需求拆解**（会话 01）：产品负责人给出需求拆解任务，Qoder 读简报和接口备忘后产出 `docs/PLAN.md`。

![会话 01：需求拆解任务](screenshots/01-plan-1-prompt.png)

**编码**（会话 02）：Qoder 编写导入、检索接口和测试。

![会话 02：编写代码和测试](screenshots/02-m1-1-writing-code-and-tests.png)

**调试**（会话 02）：Qoder 发现 `DBMS_HYBRID_SEARCH` 返回的字段不在 `_source` 下，改了检索接口和集成测试后全部通过。

![会话 02：调试检索返回字段](screenshots/02-m1-2-debug-search-result-fields.png)

**验收**（会话 10）：单元测试、集成测试、Docker 从零启动后的端到端验证、浏览器走查。

![会话 10：验收结果](screenshots/10-merge-m3-1-acceptance-summary.png)

## 目录

| 路径 | 内容 |
| --- | --- |
| `prompts/NN-*.md` | 每个会话里产品负责人发给 Qoder 的原始指令 |
| `sessions/NN-*.jsonl` | 每个会话的**完整原始记录**（`qoderclicn -o stream-json` 输出：每条模型消息、思考、工具调用、工具结果、用量），以及开始 / 结束时间 |
| `transcripts/NN-*.md` | 由 `render_transcript.py` 从 `.jsonl` 转成的可读版本（长的工具输出有截断，完整内容以 `.jsonl` 为准） |
| `qoder-native/` | Qoder CLI 自己保存的会话文件（`~/.qoder-cn/projects/<项目>/<会话 ID>.jsonl`，含子 Agent 记录）的副本 |
| `screenshots/` | 关键环节的 Qoder 界面截图 |
| `CREDITS.md` | 每个会话消耗的 Qoder Credits |
| `run_qoder.sh` | 每个会话的调用方式（非交互 `-p`、`--permission-mode accept_edits`、允许执行的命令清单） |
| `tui_capture.py` | 截图工具：在虚拟终端里运行 `qoderclicn --resume <会话 ID>`，把 Qoder 界面显示的会话历史渲染成图片，不发送任何新指令 |

## 会话一览

见 `CREDITS.md`，以及 `docs/DEVLOG.md`（Qoder 在每个会话结束时自己写的开发日志）。

## 截图是怎么来的

`screenshots/` 里是 Qoder CLI 自己的界面。会话结束后，在一个虚拟终端（150×46）里运行 `qoderclicn --resume <会话 ID>`，Qoder 会把这次会话的历史重新显示出来；`tui_capture.py` 把屏幕和滚动历史渲染成图片。

- 重放时不发送任何新指令，也不产生新的模型调用。
- 重放时 CLI 会弹出"是否信任此文件夹"的确认框。截图没有回答它，而是把它裁掉了（`--cut-at`）。

| 截图 | 环节 | 内容 |
| --- | --- | --- |
| [`01-plan-1-prompt.png`](screenshots/01-plan-1-prompt.png) | 规划 | 会话 01 开头：Qoder CLI 版本与登录方式、产品负责人给的需求拆解任务 |
| [`01-plan-2-summary.png`](screenshots/01-plan-2-summary.png) | 规划 | 会话 01 结尾：Qoder 产出的 PLAN.md 各章摘要 |
| [`02-m1-1-writing-code-and-tests.png`](screenshots/02-m1-1-writing-code-and-tests.png) | 核心编码 | 会话 02：Qoder 编写测试代码 |
| [`02-m1-2-debug-search-result-fields.png`](screenshots/02-m1-2-debug-search-result-fields.png) | 调试 | 会话 02：Qoder 发现 `DBMS_HYBRID_SEARCH` 返回字段不在 `_source` 下，修改检索接口和集成测试后全部通过 |
| [`02-m1-3-acceptance-summary.png`](screenshots/02-m1-3-acceptance-summary.png) | 验收 | 会话 02 结尾：Qoder 报告的验收结果（有两条检索标了 ⚠，交给会话 03 修复） |
| [`03-fix-1-browser-check-without-tools.png`](screenshots/03-fix-1-browser-check-without-tools.png) | 调试 | 会话 03：没有可用的浏览器工具（技能和 npm 安装被拒），Qoder 改为用 Python 标准库直接驱动 Chrome DevTools 协议来验证页面 |
| [`03-fix-2-acceptance-summary.png`](screenshots/03-fix-2-acceptance-summary.png) | 验收 | 会话 03 结尾：6 条验收检索全部第一条命中，测试全部通过 |
| [`04-m2-1-debug-exam-weights-zero.png`](screenshots/04-m2-1-debug-exam-weights-zero.png) | 调试 | 会话 04：校准时所有试题权重都是 0，Qoder 逐步排查，发现校准脚本查试卷块时没有取 `embedding` 列 |
| [`04-m2-2-acceptance-summary.png`](screenshots/04-m2-2-acceptance-summary.png) | 验收 | 会话 04 结尾：Qoder 如实标出没过的两项（覆盖判定 4/10、试题归属 10/11），交给会话 05 修复 |
| [`05-fix-1-support-threshold-margin.png`](screenshots/05-fix-1-support-threshold-margin.png) | 调试 | 会话 05：t02 的支撑字数离阈值只差 17 字，Qoder 把阈值从 250 调到 280，核对单测构造数据的余量，再跑校准确认判定不变 |
| [`05-fix-2-acceptance-summary.png`](screenshots/05-fix-2-acceptance-summary.png) | 验收 | 会话 05 结尾：10 个判定、11 道题的归属与设计真值一致，盲区第一是 t04（25 分，覆盖度 0） |
| [`06-docker-1-check-wheel-platforms.png`](screenshots/06-docker-1-check-wheel-platforms.png) | 设计 | 会话 06：为了让镜像在 amd64 和 arm64 上都能构建，Qoder 逐个核对 seekdb 镜像、PowerContext 和应用原生依赖的 wheel 平台 |
| [`06b-docker-fix-1-license-sha-and-layers.png`](screenshots/06b-docker-fix-1-license-sha-and-layers.png) | 修复 | 会话 06b：Qoder 用 curl 下载 Apache-2.0 官方原文并核对 sha256，再改写 Dockerfile 的分层顺序 |
| [`05b-radar-order-1-acceptance-summary.png`](screenshots/05b-radar-order-1-acceptance-summary.png) | 验收 | 会话 05b 结尾：两个覆盖接口共用一个排序函数，盲区第一都是 t04；雷达标签只在"：""与""（"和空格处换行，浏览器量出 30 个 SVG 标签都在容器内 |
| [`07-m3-1-acceptance-summary.png`](screenshots/07-m3-1-acceptance-summary.png) | 验收 | 会话 07 结尾：无模型全流程、本机 Ollama 出题、PowerContext 不可用时降级、30 分钟空闲结束会话都验证通过；顺手修了 `memory_ok` 误报和使用事件被误记成真实使用的问题 |
| [`08a-e2e-1-expected-red-check-and-report-fix.png`](screenshots/08a-e2e-1-expected-red-check-and-report-fix.png) | 调试 | 会话 08a：验证脚本如实报出唯一一项 ❌（当时 `get_latest()` 还没按盲区排序，由会话 05b 修），并修好报告里一处被截断的说明 |
| [`08b-docs-1-cd-app-root-cause.png`](screenshots/08b-docs-1-cd-app-root-cause.png) | 调试 | 会话 08b：开发服务器两次启动失败，Qoder 查到原因是工作目录已经在 `app/` 里，再 `cd app` 就会失败；之后按 README 的写法另起一个实例实测 |
| [`09b-site-1-fixes-measured.png`](screenshots/09b-site-1-fixes-measured.png) | 验收 | 会话 09b 结尾：网站的 9 条审阅意见逐条修复，并在 1440px 和 375px 两种宽度下用 DOM 和 ECharts 接口量测 |
| [`09c-site-1-radar-label-root-cause.png`](screenshots/09c-site-1-radar-label-root-cause.png) | 调试 | 会话 09c 第二次运行：Qoder 查到雷达标签按固定字数硬折行、会拆开英文缩写，改成只在"：""与""（"和空格处换行，再写脚本在两种宽度下量测 |
| [`10-merge-m3-1-acceptance-summary.png`](screenshots/10-merge-m3-1-acceptance-summary.png) | 验收 | 会话 10 结尾：单测和集成测试通过；Docker 栈从零启动后端到端 5 步 66 项全绿；浏览器走完开会话、答错、答对、新会话开场白、记忆页、使用记录 |

会话 03、04、05 中途 Qoder 各压缩过一次上下文，`--resume` 只显示压缩之后的部分。所以截图里看不到这几段过程：
- 会话 03 的检索排序调试（标题加权参数扫描、RRF 平分时用关键词分决胜）；
- 会话 04 前半段的编码（考试范围解析、覆盖度引擎）；
- 会话 05 前半段的编码（按考点词判定覆盖、按考点词归属试题、切块修复）。

完整过程在 `sessions/` 和 `transcripts/` 里的同名文件中。`docs/DEVLOG.md` 的会话 03 一节有修改前后的对比表。

## 说明

- 开发时连接的是本机 Docker 里的 seekdb 和 PowerContext，数据库密码是本机随机生成的开发密码，只存在被 `.gitignore`
  忽略的 `qoder/.env` 里。如果会话记录里出现过它，提交前已替换为 `***REDACTED***`，除此之外记录未做任何改动。
- Qoder 的会话可以在同一账号下用 `qoderclicn --list-sessions`（在 `qoder/` 目录下）和 `qoderclicn --resume <会话 ID>` 查看。
