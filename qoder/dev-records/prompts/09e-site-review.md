会话 09e：协调者审阅网站后提出两处修改：开场白示例换成应用现在的说法；网站上不再显示 Credits 数字。

先读 `docs/DEVLOG.md` 里会话 09d 一节，以及 `app/examradar/mastery.py` 里的 `build_opening_line`。

## 要改的

1. **「学习者记忆」里的开场白示例**（`site/index.html`）还是旧说法："上次你在 X 上错了 2 次，先复习这个"。
   - 会话 10c 之后，应用显示的是"你在『X』上累计错了 N 次，先复习它"，次数是累计的。
   - 把示例换成 `build_opening_line` 真正会生成的一句，例如它 docstring 里的那句。
2. **网站上不再显示 Credits 数字。** 这些数字是 CLI 报告的累计，和 Qoder 账户用量页上的显示对不上，所以公开网站上不放。
   - 会话表保留 #、会话内容、模型、轮数、耗时，去掉 Credits 列。合计行只留条数和轮数。
   - 手机上的会话卡片和合计卡也去掉 Credits。
   - `site/data/qoder-sessions.json` 的每一行和 totals 里都不再有 credits 字段：
     - 改 `scripts/build_site_data.py`，再运行它重新生成 JSON；
     - `dev-records/CREDITS.md` 的表格不变，脚本照旧从它读；
     - 脚本最后打印的那行也不再打印 credits。
   - 会话表上方的说明："下表是每次 Qoder 会话的型号、轮数和 Credits 用量"改成"下表是每次 Qoder 会话的模型、轮数和耗时"。
   - 表格（手机上是卡片）下面加一行可见的说明："用量以 Qoder 账户用量页为准（账号 UID 见 dev-records/README.md）。"
     - 其中 `dev-records/README.md` 链到 `https://github.com/Fengzdadi/powercontext/blob/2026-competition-ecosystem/qoder/dev-records/README.md`；
     - 新标签页打开，写法照页面上已有的 GitHub 链接。
   - 页面上其他地方也不要再出现 Credits 数字。不再用到的函数（如 `fmtCredits`）和样式一并删掉。
3. 其余内容不变。

## 验收标准

桌面（1440×900）和手机（375×812）都检查，用 DOM 量，结果写进 DEVLOG：

- 页面文本（`innerText`）里没有 "Credits" 或 "credits"。用脚本遍历 `qoder-sessions.json` 的全部键名，没有 credits。
- 会话表的表头、每一行、合计行都是 5 列；合计行的条数和轮数等于 JSON 的 totals。
- 手机卡片和合计卡里没有 Credits。
- 表格下方的说明在桌面和手机上都可见，链接地址正确。
- 开场白示例是新说法，页面里找不到"上次你在"。
- 会话 09c、09d 的其他检查项全部仍然通过：
  - 检查脚本是 `.cache/scratch/check_09c.py`、`check_09c_radar.py`、`check_09d.py`；
  - 其中核对 Credits 合计的检查改成核对"没有 Credits"，写成新脚本 `.cache/scratch/check_09e.py`。
- 截图，用 Read 看一遍。

## 规则

- 只改这些文件：
  - `site/index.html` 和 `site/assets/` 下的文件；
  - `scripts/build_site_data.py`，以及它重新生成的 `site/data/qoder-sessions.json`；
  - `docs/DEVLOG.md`：在会话 09d 一节后面追加"会话 09e"小节。
- 预览服务器只用 18808 端口：
  - Bash 设为后台运行（run_in_background），末尾不要加 `&`；
  - 结束时用 PID 关掉。
- 不要发布网站。
- 本会话用的模型是 GLM-5.3。临时脚本放在 `.cache/scratch/`，用 `.cache/scratch/pwvenv/bin/python` 运行。
- 权限规则同前。做不到的验收项写"未验证"和原因，不能打 ✅。
