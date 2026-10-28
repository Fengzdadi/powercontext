#!/usr/bin/env bash
# 把法庭恢复到初始状态：删除 seekdb 和 PowerContext 的数据卷，重新启动并等待服务就绪。
# 恢复后 seekdb 里只有 44 件种子判例和 33 条法典，PowerContext 里没有任何原告的记忆。
# Dify 里的旧会话不影响游戏状态（庭审进度存在各自会话的会话变量里），新开一个会话即可。
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down -v
docker compose up -d
"$(dirname "$0")/wait.sh"
