会话 08（里程碑 M4 第二部分）：端到端验证脚本 + 验证样例 + README。

先读 `docs/DEVLOG.md`（会话 06 已经修好 Docker 部署，写了 `docs/DEPLOY.md`；会话 07 完成了复习教练和记忆）。开发用的 seekdb（127.0.0.1:10800）和 PowerContext（127.0.0.1:18801）照常在跑，不要动它们。

{{REVIEW}}

## 本会话任务

1. **端到端验证脚本** `scripts/e2e_verify.py`：只用标准库或 app 已有的依赖，请求都带 `X-ExamRadar-Source: auto`。脚本按验证样例逐步执行，并把每一步写进 Markdown 报告 `docs/validation/e2e-report.md`。步骤：
   - 导入样例资料：各份资料的块数；试卷 11 题，合计 100 分。
   - 6 条检索：检索 JSON、`GET_SQL` 给出的实际 SQL、前 3 条结果的出处和两路分数，并和期望出处对照。
   - 覆盖雷达：10 个知识点的判定、每个考点词的证据、11 道题的归属，和设计真值对照；盲区第一名。
   - 复习教练：
     - 流程：新学习者开始会话（bootstrap 为空）→ 出题 → 答错 → 答对 → 结束 → 开始新会话，开场白提到上次答错的知识点。
     - 列出这一路对 PowerContext 的每次读写：接口、artifact id、revision、标签。
     - 列出掌握度卡片的 revision 历史，以及 `context/prepare` 召回到的错题。
   - 每一步标 ✅ / ❌，最后一行给出总结。脚本退出码：全部通过为 0，否则为 1。
   - 支持 `--app-url` 参数，本地开发和 Docker 部署都能跑。对 examradar-ci 跑一次，把报告提交进仓库。
2. **README.md**：中文，放在 `qoder/README.md`。这是给评审看的，要能照着从零跑起来。
   - 一句话介绍、解决的问题、核心功能、界面截图（截图我来补，先留 `docs/images/` 路径）；
   - 版本表：Python、uv、seekdb 镜像 tag、PowerContext 版本、向量模型、ECharts、主要 Python 依赖；
   - 架构图（Mermaid），以及 **seekdb 和 PowerContext 的分工**：各自存什么、在哪个功能里起作用、对应的代码位置；
   - 部署方式 A（Docker 一键启动）和部署方式 B（本地开发），以 `docs/DEPLOY.md` 为基础；
   - 配置项表：每个环境变量的含义和默认值，包括可选的大模型配置；
   - **验证样例**：链接到 `docs/VALIDATION.md`；
   - 常见问题；
   - 许可证：代码 Apache-2.0，样例资料 CC BY 4.0。另列第三方组件来源（ECharts、marked 等，写明版本和许可证）。
3. **`docs/VALIDATION.md`**：给人手动执行的验证样例。
   - 初始数据：`samples/course-db/` 的每份文件；
   - 输入；
   - 操作步骤：界面操作和对应的 curl / CLI 命令各一份；
   - 每一步的预期结果；
   - 怎么核对 seekdb 的查询（`python -m examradar.cli sql ...` 或 `GET_SQL` 的输出）；
   - 怎么核对 PowerContext 的记忆读写：具体接口和返回字段；
   - 最后一节说明 `scripts/e2e_verify.py` 能把这些一次跑完。

## 工作方式

- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。
- docker 命令只能这样写：`docker compose -p examradar-ci --env-file .env.ci <子命令>`，子命令为 `up -d --build`、`ps`、`logs <服务>`、`down -v`。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip。

## 验收标准

- `docker compose -p examradar-ci --env-file .env.ci up -d --build` 从零起来，三个服务都 healthy。
- `scripts/e2e_verify.py --app-url http://127.0.0.1:18807` 全部 ✅，报告已写入 `docs/validation/e2e-report.md`。
- `cd app && uv run pytest` 和 `cd app && export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过。
- README 里的每条命令你都实际跑过，写在 DEVLOG 里。
- 会话结束前 `down -v` 清掉 examradar-ci，关掉你启动的进程。

结束前在 `docs/DEVLOG.md` 追加本会话记录。做不到的验收项写"未验证"和原因，不能打 ✅。不要修改 `dev-records/` 和 `samples/`。
