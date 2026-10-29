#!/usr/bin/env bash
# 多次实时运行 T-101 的完整流程，统计 MiniMax 开发助手的完成情况（需要 MINIMAX_API_KEY）。
# 每次使用独立的任务 ID（T-101-<标签>-<序号>）和独立的 PowerContext Scope，不影响 T-101 本身的状态。
#
#   scripts/trials.sh 3                         用默认模型跑 3 次
#   scripts/trials.sh 2 MiniMax-M3 m3           用 MiniMax-M3 跑 2 次，任务 ID 标签为 m3
#
# 每次的终端输出在 runs/trials/<任务ID>/console.txt，汇总追加到 runs/trials/summary.tsv。
set -euo pipefail
cd "$(dirname "$0")/.."
N="${1:-3}"
MODEL="${2:-}"
LABEL="${3:-${MODEL:-default}}"
mkdir -p runs/trials
for i in $(seq 1 "$N"); do
  id="T-101-$LABEL-$i"
  dir="runs/trials/$id"
  rm -rf "$dir" "runs/$id"
  mkdir -p "$dir"
  sed "s/^id = \"T-101\"/id = \"$id\"/" samples/T-101/task.toml > "$dir/task.toml"
  start=$(date +%s)
  set +e
  ./sdd run "$dir/task.toml" ${MODEL:+--model "$MODEL"} > "$dir/console.txt" 2>&1
  code=$?
  set -e
  seconds=$(( $(date +%s) - start ))
  result=$(grep -E "全部步骤已完成|没有完成|错误：" "$dir/console.txt" | tail -1 || true)
  printf '%s\t%s\t%s\t%ss\t%s\n' "$id" "${MODEL:-default}" "$code" "$seconds" "$result" | tee -a runs/trials/summary.tsv
done
