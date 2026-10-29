# Qoder 开发记录

本项目（考前雷达 ExamRadar）的需求拆解、技术设计、编码和调试由 **Qoder CLI**（`qoderclicn` 1.1.80，Qoder CN）完成。
产品负责人只负责写需求、提供样例数据和接口实测备忘、审阅和验收，不直接写应用代码。

- **Qoder 账号**：用户名 `fengzc`（个人版）
- **账号 UID**：（待账号所有者在 Qoder 账号页核对后填写）

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

## 说明

- 开发时连接的是本机 Docker 里的 seekdb 和 PowerContext，数据库密码是本机随机生成的开发密码，只存在被 `.gitignore`
  忽略的 `qoder/.env` 里。如果会话记录里出现过它，提交前已替换为 `***REDACTED***`，除此之外记录未做任何改动。
- Qoder 的会话可以在同一账号下用 `qoderclicn --list-sessions`（在 `qoder/` 目录下）和 `qoderclicn --resume <会话 ID>` 查看。
