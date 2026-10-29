会话 09g：演示视频一节改成封面图，点封面从 GitHub 下载视频。

先读 `docs/DEVLOG.md` 里会话 09d、09e、09f 三节。

## 背景

网站要用 Qoder Sites 发布 `site/` 目录，整个目录会打成一个包上传。带着 2.4 MB 的视频，上传四次都超时。所以视频不再放进网站，只留在代码仓库里。

产品负责人已经提交了这些改动，不用再动：

- `site/media/demo.mp4` 移到了 `docs/media/demo.mp4`，`site/` 里不再有视频文件。
- `site/media/demo-poster.jpg` 重新压缩过，仍是 1280×800。
- `site/images/` 的 5 张截图换成了 256 色版本，文件名和尺寸不变。

现在网站上演示视频一节探测不到视频，显示的是"视频即将上线"。

## 要改的

1. `site/index.html` 的 `<section id="video">`：
   - 去掉 `<video>` 和"视频即将上线"占位。
   - 换成封面图 `media/demo-poster.jpg`。整张封面是一个链接，在新标签页打开（`target="_blank" rel="noopener"`），地址是：
     `https://github.com/Fengzdadi/powercontext/raw/2026-competition-ecosystem/qoder/docs/media/demo.mp4`
     这是 GitHub 的原始文件地址，点开会直接下载视频。
   - 封面中间叠一个播放图标，看得出能点。用 CSS 或内联 SVG，不要引入新文件或外部资源。
   - 封面下加一行字，原文如下：
     `视频文件放在代码仓库里（qoder/docs/media/demo.mp4，MP4，约 2.4 MB），点封面从 GitHub 下载。`
   - 封面图的 `alt` 写明这是演示视频的封面。
   - 标题和副标题（`.sec-sub`）不变。
2. `site/assets/main.js`：删掉视频探测和显示/隐藏的代码（`DEMO_VIDEO`、`loadVideo` 及其调用），其他不动。
3. `site/assets/style.css`：加封面、播放图标和说明文字的样式。封面宽度和原来的视频框一致，手机宽度下不超出容器。删掉不再用到的视频样式（`.video-box video`、`.video-pending`）。

## 验收标准

用 DOM 量，结果写进 DEVLOG：

- 1440×900 和 375×812 两种宽度下：
  - 页面上没有 `<video>`、`#demo-video`、`#video-pending`；
  - 封面图加载成功（`naturalWidth` 为 1280），没有超出容器，页面没有横向滚动；
  - 封面链接的 `href`、`target`、`rel` 和上面一致；
  - 封面下那行字可见，文字和上面完全一致，位置在封面下方；
  - 所有请求都来自本站，没有任何请求的地址里含 `demo.mp4`；控制台没有报错。
- `site/` 里没有 `.mp4` 文件。`site/` 的文件数和总大小写进 DEVLOG。
- 更新检查脚本，改完都要通过：
  - `.cache/scratch/check_09d.py`：视频相关的检查（时长、`preload`、`poster`、404 时的占位，以及按 `site/media/demo.mp4` 算大小的那段）换成上面的封面检查；截图和说明文字的检查保留。
  - `.cache/scratch/check_09e.py`：第 418–438 行的视频检查（视频存在、模拟缺失两种）换成封面检查，其余不动。
  - `check_09c_radar.py`、`check_09f.py` 不改，仍然通过。
- 桌面和手机各截一张演示视频一节的图，用 Read 看一遍。

## 规则

- 只改 `site/index.html`、`site/assets/main.js`、`site/assets/style.css` 和上面两个检查脚本，并在 `docs/DEVLOG.md` 会话 09f 一节后面追加"会话 09g"小节。
- 不要访问上面的 GitHub 地址。文件要等推送后才有，由产品负责人确认。检查只核对链接属性，不要点击链接。
- 预览服务器只用 18808 端口：
  - Bash 设为后台运行（run_in_background），末尾不要加 `&`；
  - 结束时用 PID 关掉。
- 不要发布网站。
- 本会话用的模型是 GLM-5.3。临时脚本放在 `.cache/scratch/`，用 `.cache/scratch/pwvenv/bin/python` 运行。
- 权限规则同前。做不到的验收项写"未验证"和原因，不能打 ✅。
