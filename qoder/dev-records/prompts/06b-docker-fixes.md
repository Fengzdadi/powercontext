会话 06b：修正会话 06 审阅发现的问题（接着会话 06 继续）。

我审阅了会话 06。这些都没问题：
- compose 从零启动；
- 端口只绑 127.0.0.1；
- 模型打进了镜像；
- `load_sample.sh` 走 HTTP；
- DEPLOY.md 和平台支持表。

下面三处要改。

1. **`LICENSE` 不是 Apache-2.0 原文**。和 https://www.apache.org/licenses/LICENSE-2.0.txt 逐行对比：
   - 措辞有差异，例如原文是"source, and configuration files"，这里写成了"source files, and configuration files"；原文"other media types"写成了"other media"；
   - 换行也不同。

   DEVLOG 里写的"官方 LICENSE-2.0.txt 原样"不成立。修法：
   - 用 `curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE` 直接下载原文，不要经过模型转写；
   - 用 `shasum -a 256 LICENSE` 核对，应为 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`；
   - 在 DEVLOG 会话 06 一节里改正那句"原样"，写明后来是怎么修的。
2. **Dockerfile 的层顺序**：现在 `COPY app/examradar/` 在 `uv sync` 和模型下载之前，改任何一行代码，后面的层缓存全部失效，每次构建都要重装全部依赖、重新下载模型。改成：
   - 先只装依赖：`uv sync --frozen --no-dev --no-install-project`；
   - 再下载模型；
   - 然后复制源码，再 `uv sync --frozen --no-dev` 安装项目本身；
   - 最后复制 `static/`。
3. **模型名在 Dockerfile 里写死了**，可 compose 允许用 `EMBEDDING_MODEL` 换模型。换了以后，运行时是离线模式，会找不到新模型。
   - 把模型名做成构建参数，默认 `BAAI/bge-small-zh-v1.5`；
   - compose 用同一个 `EMBEDDING_MODEL` 变量，同时传给构建参数和运行时环境；
   - DEPLOY.md 里说明"换模型要重新构建镜像"。

   顺带核对 DEPLOY.md 里"`FASTEMBED_CACHE_PATH` 未设置时为 `/tmp/fastembed_cache` 或 `~/.cache` 下"这句：查 fastembed 源码，写出确切的默认位置，不要写"或"。

## 验收标准

- `shasum -a 256 LICENSE` 与上面的值一致。
- 先 `down -v`，再 `docker compose -p examradar-ci --env-file .env.ci up -d --build` 从零启动，三个服务都 healthy。
- 导入样例、一条检索都成功，请求带 `X-ExamRadar-Source: auto`。
- 会话结束前 `down -v`，不留容器和卷。
- `app/` 没有改动。

规则和会话 06 一样：
- 只改部署相关文件；
- docker 命令只能用 `docker compose -p examradar-ci --env-file .env.ci <子命令>`；
- 模型用 GLM-5.3。

结束前在 DEVLOG 会话 06 一节后面追加"会话 06b"小节：改了什么、验收结果。做不到的验收项写"未验证"和原因，不能打 ✅。
