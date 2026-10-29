会话 10c：开场白里错题次数的说法，以及复习教练相关文档。

先读 `docs/DEVLOG.md` 里会话 10 和会话 10b 两节。环境同前：seekdb 127.0.0.1:10800，PowerContext 127.0.0.1:18801，密码在 `qoder/.env`；不要启停开发用的容器。

## 要改的问题

1. **开场白里的次数是累计的，说法却是"上次"**
   - `coach.build_review_plan_inputs` 里的次数取自掌握度卡片的累计答错数，开场白写的却是"上次你在『X』上错了 N 次"。
   - 现象：学习者"示例同学"上一次会话只答错 t04 一次，下一次会话的开场白却是"上次你在『函数依赖与范式（3NF、BCNF）』上错了 4 次，先复习它"。
   - 要求：
     - 改成和数据一致的说法，例如"你在『X』上累计错了 N 次，先复习它；『Y』累计错了 M 次"；
     - 会话 10b 加的盲区括注保留。
   - 已有学习者的复习计划存在 PowerContext 里，要等下一次判分才会按新说法重写。不用迁移，在 DEVLOG 里写明。
2. **`README.md` 的复习教练一节**
   - 标题"## 9. 复习教练与学习者记忆（M3）"去掉"9."，和其他二级标题一致；
   - 开场白的例子按新说法改；
   - 第 2 条"选题优先级"按会话 10b 的实现补全：
     - 同一会话里刚出过的知识点，隔 2 道别的题再出；
     - 计划里的知识点先轮一遍，再回到答错的；
     - 自测题在这个知识点的几道往年原题之间轮换。
3. **`docs/VALIDATION.md` 第 7 节**
   - 开场白的两处例子按新说法改；
   - 第 1 题的 `source.label` 改成会话 10b 之后的实际输出（"… · 第4题 · 15 分"）；
   - 按第 7 节的命令在开发服务器上实际跑一遍，核对"预期结果"里其余的摘录。和实际输出不一致的地方，按实际输出改。

## 验收标准（逐条跑通后再结束会话，把实际结果写进 DEVLOG）

- `cd app && uv run pytest` 和 `cd app && export EXAMRADAR_IT=1 && uv run pytest -m integration` 全部通过。断言旧说法的测试一起改。
- 新增单测：开场白的次数说法与数据来源一致（累计答错次数），不出现"上次……错了"。
- 开发库上用一个新的学习者名字（带上时间）连续做 3 次会话：
  - 第 1 次答错 t04；
  - 第 2 次再答错 t04；
  - 把第 2、3 次会话开始时的开场白原文贴进 DEVLOG，t04 的次数应是 1 和 2。
- 端到端：`docker compose -p examradar-ci --env-file .env.ci up -d --build` 之后，`scripts/e2e_verify.py --app-url http://127.0.0.1:18807` 全部 ✅，报告写入 `docs/validation/e2e-report.md`。
- 会话结束前 `docker compose -p examradar-ci --env-file .env.ci down -v`，关掉你启动的进程。

## 工作方式

- 本会话用的模型是 GLM-5.3。
- `uv` 命令一律在 `qoder/app/` 下运行（`cd app && uv ...`）。
- docker 命令只能这样写：`docker compose -p examradar-ci --env-file .env.ci <子命令>`，子命令为 `up -d --build`、`ps`、`logs <服务>`、`down -v`。CI 栈占用 18805–18807。
- 开发服务器只用 18800 端口：
  - Bash 设为后台运行（run_in_background），命令是 `cd app && .venv/bin/python -m uvicorn examradar.main:app --host 127.0.0.1 --port 18800`，末尾不要加 `&`；
  - 结束时用 PID 关掉。
- 权限规则同前：带 `2>&1`、`2>/dev/null`、管道、末尾 `&` 的命令会被拒绝；前置环境变量用 `export X=1 && cmd`；不要用 pip，用 uv。
- 不要修改 `docs/reference/`、`dev-records/`、`samples/` 和 `site/`。

结束前在 `docs/DEVLOG.md` 末尾追加"会话 10c"一节：做了什么、遇到的问题和解决办法、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。
