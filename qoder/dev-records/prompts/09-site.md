会话 09：项目网站（之后用 Qoder Sites 发布）。

本会话只做网站，所有文件都放在 `qoder/site/` 下。除了在 `docs/DEVLOG.md` 末尾追加本会话记录，**不要改 `site/` 以外的任何文件**：你在单独的一份工作目录里，应用代码由别的会话同时在改，之后由产品负责人合并。网站是给大赛评审看的项目介绍页，评审对象是项目本身，网站本身不单独评分。所以要做到：信息准确、一眼看懂、打开快。

先读这些材料，网站上的每个事实都要以它们为准，**不要编造任何数字、用户或评价**：
- `docs/BRIEF.md`、`docs/PLAN.md`、`docs/DEVLOG.md`；
- `samples/course-db/README.md`；
- `dev-records/CREDITS.md` 和 `dev-records/README.md`。

## 网站内容（中文）

1. **首屏**：项目名"考前雷达 ExamRadar"，一句话说明它做什么，两个按钮："看示例雷达"（跳到下面的体验区）、"代码仓库"。
2. **解决的问题**：期末复习时，笔记、课件 PDF、英文阅读材料、往年试卷散在各处。学生不知道哪些考点自己根本没记、哪些往年分值很高；做题时反复错同一类题，下次打开又从头开始。
3. **核心功能**，每项配一张截图（截图由产品负责人提供，放在 `site/images/`，先用占位框标出文件名）：
   - 导入资料 + 问笔记：混合检索，每条结果带出处（文件 · 页 · 标题）；
   - 考前覆盖雷达：按考试范围逐个考点找证据，判定已覆盖 / 薄弱 / 缺失；往年试卷按题归属到知识点；盲区按"分值 × 未覆盖"排序；每个判定都写明理由；
   - 复习教练：按盲区和到期复习出题、判分，用 Leitner 间隔复习排期；
   - 学习者记忆：掌握度卡片（每次判分产生新的 revision，可看变化轨迹）、错题、复习计划；下次打开时的开场白，例如"上次你在 X 上错了 2 次"；
   - 使用记录：真实使用和开发测试的数据分开统计，可以导出。
4. **seekdb 和 PowerContext 的分工**：一张图加一张表。说明各自存什么、在哪个功能里起作用、怎么核对。例如 seekdb 那一行写 `DBMS_HYBRID_SEARCH` 和 `GET_SQL`；PowerContext 那一行写 Scope、原子记忆的 revision、标签、`context/bootstrap` 和 `context/prepare`。
5. **体验区**：用样例课程（《数据库系统原理》）的真实分析结果，做一个可交互的覆盖雷达快照。
   - 数据已经在 `site/data/sample-coverage.json`：产品负责人从本地应用原样导出了 `GET /api/coverage/latest?course_id=db101` 的结果，不要改里面的数据。
   - 用 ECharts 画雷达图，下面是盲区清单，点开能看证据、出处和试题。
   - 页面上写明：这是示例数据的静态快照；完整功能要在本地运行。
   - 给出 Docker 一键启动的几条命令，以 `docs/DEPLOY.md` 或 `README.md` 为准，并链接到仓库里的 README 和 VALIDATION。
6. **演示视频**：`site/media/demo.mp4`，由产品负责人提供，先放占位。文件不存在时，这一节显示"视频即将上线"，不要出现坏掉的播放器。
7. **Qoder 开发过程**：
   - 会话表：编号、做了什么、模型、轮数、Credits，数据来自 `dev-records/CREDITS.md`；
   - 说明分工：需求拆解、编码、调试由 Qoder 完成，产品负责人负责需求、审阅和验收；
   - 链接到仓库里的 `dev-records/`：完整会话记录、关键截图。
8. **使用效果**：只写真实、可核对的数据，并注明来源（使用记录导出、Qoder Sites 访问统计）。还没有真实使用数据时，如实写"真实使用数据收集中"，不要拿开发测试数据充数。
9. **页脚**：
   - 代码仓库：https://github.com/Fengzdadi/powercontext/tree/2026-competition-ecosystem/qoder
   - 许可证：代码 Apache-2.0，样例资料 CC BY 4.0；
   - 第三方组件（ECharts 等）的来源。

## 技术要求

- 纯静态页面：`site/index.html` 加 `site/assets/`、`site/data/`、`site/images/`、`site/media/`，不需要构建步骤。之后用 Qoder Sites 发布 `site/` 目录。
- **不引用外部 CDN**，评审的网络环境未知。ECharts 从 `app/static/lib/` 复制一份到 `site/assets/`，并写明版本。
- 手机和电脑都要能看。页面总大小控制在 3 MB 以内，视频除外。
- 不放任何密码、密钥、个人信息。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- 本地预览用 `cd site && python3 -m http.server 18808`（用 Bash 的后台运行方式启动，命令末尾不要加 `&`），用浏览器实际打开检查，截图存到 `qoder/.cache/scratch/`。结束时关掉它。
- 浏览器检查：两种办法任选。
  - 在 `qoder/.cache/scratch/` 下建一个小虚拟环境（`uv venv` + `uv pip install playwright`），用本机 Chrome（`channel="chrome"`，不需要下载浏览器）。不要建在 `site/` 里，`site/` 会整个发布出去。
  - 用 Python 标准库驱动 Chrome DevTools 协议。

  不要动 `app/` 的依赖。
- 不要在 18800 端口上启动任何服务（别的会话在用）。
- 权限规则：
  - 带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；
  - 前置环境变量（`X=1 cmd`）会被拒绝，用 `export X=1 && cmd`；
  - 不要用 pip。
- **不要发布网站**：发布是公开操作，要等账号所有者确认后单独进行。

## 验收标准

- 在浏览器里打开 `http://127.0.0.1:18808/`，桌面宽度和手机宽度（375px）各截一张图，看过没有错位。
- 体验区的雷达和盲区清单用的是真实导出的数据。点开盲区能看到证据和试题。
- 页面上的每个数字都能在仓库里找到出处，在 DEVLOG 里列出对照。
- 没有外部 CDN 请求：用浏览器的网络记录确认。

结束前在 `docs/DEVLOG.md` 追加本会话记录，做不到的验收项写"未验证"和原因。
