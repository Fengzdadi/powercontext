# Qoder Sites 发布记录

项目网站用 Qoder CLI 的 `sites` 子命令发布到 Qoder Sites，由产品负责人在本机执行（Qoder 账号已在本机登录）。发布前，账号所有者已同意公开，协调者已审阅草稿。

- **网址**：<https://examradar-9ertt3o7l76.qoder.zone>
- **访问范围**：任何人都可访问（`update_access_policy`，`mode` 为 `public`，`confirmPublic` 为 `true`）
- **发布内容**：`qoder/site/` 目录，14 个文件，共 1,474,696 字节（上传包 654,425 字节），来自提交 `f9a646e4`。之后的提交没有改 `site/`。
- **时间**：2026-10-29 03:11 EDT（北京时间 15:11）
- **工具**：`qoderclicn` 1.1.80，`qoderclicn sites <操作> --input '<JSON>'`，命令都在 `qoder/` 目录下执行
- **演示视频不在发布包里**：带视频的包有 3.3 MB（16 个文件），本机上行约 25–46 KB/s，`prepare_site` 上传四次都在约 30 秒时超时（`sites_upload_unavailable`）。所以视频留在代码仓库的 `qoder/docs/media/demo.mp4`，网站上演示视频一节改成封面图（会话 09g），点封面从 GitHub 下载。截图同时换成 256 色版本（文件名和尺寸不变），封面重新压缩。

## 步骤

下面是实际执行的命令和输出摘要。输出里的访问引用（`accessRef`）是不透明引用，记录里只保留前 10 个字符；`requestId` 省略。

1. **带视频的包，上传失败**（02:26–02:34 EDT）。`prepare_site` 的输入：
   `{"actionId": "43cbd2cf-…", "projectRoot": "…/qoder", "webDirectory": "site", "createNewSite": true, "displayName": "考前雷达 ExamRadar", "slug": "examradar"}`
   这一步建好了项目 `01a18656-e6a2-7ba3-bed0-9bcde591c8c0` 和站点 `01a18656-e6a3-72a9-ba07-85adb9f5b0dd`，但上传连同三次原样重试都失败，输出 `{"ok": false, "error": "sites_upload_unavailable"}`。
2. **缩包后重新准备**（03:02 EDT）。换新的 action，带已有项目，不新建站点：
   `{"actionId": "5212fde4-…", "projectRoot": "…/qoder", "webDirectory": "site", "projectId": "01a18656-e6a2-7ba3-bed0-9bcde591c8c0", "displayName": "考前雷达 ExamRadar", "slug": "examradar"}`
   第一次仍在 30 秒时超时。03:09:20 原样重试，28 秒传完，输出 `ok: true`、`descriptorStatus: pending`。
3. `get_publish_status {"actionId": "5212fde4-…"}`：`artifactReady: true`，`dependenciesReady: true`，`canPublish: true`，`blockers: []`。
4. 按 CLI 的提示，用同一个 action 和同样的输入再调一次 `prepare_site`（不重新打包，也不上传）：`descriptorStatus: written`。CLI 在 `qoder/` 下生成了本机描述文件 `.考前雷达 ExamRadar.qoder.site`（项目、站点、部署 ID，哈希和 `index.html` 副本）。它是本机的绑定状态，没有提交。
5. `publish_site {"actionId": "5212fde4-…"}`：返回 `publishOperationId`。
6. `get_publish_status`：`readiness: publication_completed`，`published: true`，`site.url` 为 `https://examradar-9ertt3o7l76.qoder.zone`，这时 `access_mode` 还是 `private`。
7. `get_site_access {"siteId": "01a18656-e6a3-72a9-ba07-85adb9f5b0dd"}`：`policy.mode` 为 `private`，没有邀请的访客。可选模式是 `private`、`selected` 和 `public`，其中 `public` 需要确认。访问引用 `sr_bhiC9PD…`。
8. `update_access_policy {"siteId": "01a18656-e6a3-72a9-ba07-85adb9f5b0dd", "requestId": "…", "accessRef": "sr_bhiC9PD…", "mode": "public", "confirmPublic": true}`：`policy.mode` 为 `public`，`auth_integration_status` 为 `not_required`。

## 未登录访问检查

2026-10-29 03:12–03:14 EDT，在本机检查：

- **`curl`，不带任何 cookie**：
  - 首页返回 `HTTP/2 200`。
  - 14 个文件逐个下载，13 个和 `qoder/site/` 里的文件逐字节相同。
  - `index.html` 在 `</body>` 之前也和本地文件逐字节相同。Qoder Sites 在 `</body>` 前注入了一段"Made with Qoder"水印脚本：内联，不发网络请求，不读写存储，唯一的外链指向 qoder.cn。水印显示在右下角，可以关掉。
  - `media/demo.mp4` 返回 404：视频不在发布包里，网站封面链接的是代码仓库里的 `qoder/docs/media/demo.mp4`。
- **全新的浏览器上下文（没有任何 cookie）**，桌面 1440×900 和手机 375×812 两种宽度：
  - 每种宽度 14 个请求，全部来自本站，控制台没有错误，图片全部加载；
  - 会话表 26 行，合计和数据一致，页面上没有 Credits；
  - 演示视频一节是封面链接，下面有说明文字。
