#!/usr/bin/env bash
# 从空状态把验证样例 T-101 完整跑一遍，并把每一步的终端输出和产物收集到一个目录。
#
#   scripts/run-sample.sh            实时调用 MiniMax 完成代码修改（需要 MINIMAX_API_KEY），产物在 runs/evidence/T-101/
#   scripts/run-sample.sh --replay   不调用 MiniMax，回放已提交的开发记录 evidence/T-101/minimax/session.json，
#                                    产物在 runs/evidence-replay/T-101/
#   OUT=目录 scripts/run-sample.sh   指定产物目录
#
# 注意：第一步是 ./sdd reset，会删除本环境的 seekdb 数据卷、PowerContext 数据卷和 runs/。
set -euo pipefail
cd "$(dirname "$0")/.."

TASK=T-101
MODE=live
REPLAY_SESSION=evidence/$TASK/minimax/session.json
if [ "${1:-}" = "--replay" ]; then
  MODE=replay
  [ -f "$REPLAY_SESSION" ] || { echo "找不到 $REPLAY_SESSION" >&2; exit 1; }
fi
OUT="${OUT:-runs/evidence$([ "$MODE" = replay ] && echo -replay)/$TASK}"

sdd() {  # sdd 名称 子命令...：运行 ./sdd 并把命令、输出和退出码写到 $OUT/console/名称.txt
  local name="$1"; shift
  local file="$OUT/console/$name.txt"
  echo
  echo "\$ ./sdd $*" | tee "$file"
  set +e
  ./sdd "$@" 2>&1 | tee -a "$file"
  local code=${PIPESTATUS[0]}
  set -e
  echo "# exit code: $code" | tee -a "$file"
  if [ "$code" -ne 0 ]; then
    echo "步骤 $name 失败（exit $code），终端输出见 $file" >&2
    exit "$code"
  fi
}

./sdd reset
rm -rf "$OUT"
mkdir -p "$OUT/console" "$OUT/context" "$OUT/minimax" "$OUT/state"

sdd 00-up up
sdd 01-info info
sdd 02-import import
sdd 03-db-inspect db-inspect
sdd 04-search search "可借 在架 副本 出版年份 筛选" --kind spec --size 8
sdd 05-state-empty state $TASK
sdd 06-context context $TASK
cp runs/$TASK/context.md "$OUT/context/context-initial.md"
cp runs/$TASK/context.json "$OUT/context/context-initial.json"
sdd 07-check-context check-context $TASK
sdd 08-run-until-verify-before run $TASK --stop-after verify-before
sdd 09-restart restart
sdd 10-state-after-restart state $TASK
cp "$OUT/console/10-state-after-restart.txt" "$OUT/state/state-after-restart.md"
sdd 11-context-after-restart context $TASK --quiet
cp runs/$TASK/context.md "$OUT/context/context-after-restart.md"
if [ "$MODE" = replay ]; then
  sdd 12-run-resume run $TASK --replay "$REPLAY_SESSION"
else
  sdd 12-run-resume run $TASK
fi
sdd 13-run-again run $TASK
sdd 14-check-record check-record $TASK
sdd 15-spec-update-demo spec-update-demo $TASK
sdd 16-state-final state $TASK
./sdd state $TASK --json > "$OUT/state/state-final.json"
cp "$OUT/console/16-state-final.txt" "$OUT/state/state-final.md"

# 收集产物
cp runs/$TASK/develop/context-*.md "$OUT/context/context-for-minimax.md"
cp runs/$TASK/context-spec-updated.md runs/$TASK/context-spec-restored.md "$OUT/context/"
cp runs/$TASK/change.patch "$OUT/change.patch"
if [ "$MODE" = live ]; then
  session=$(ls -t runs/$TASK/develop/session-*.json | head -1)
  cp "$session" "$OUT/minimax/session.json"
  cp "${session%.json}.md" "$OUT/minimax/session.md"
  mkdir -p "$OUT/minimax/self-tests"
  cp runs/$TASK/develop/tests-*/*.log "$OUT/minimax/self-tests/" 2>/dev/null || true
else
  cp runs/$TASK/develop/replay-*.json "$OUT/minimax/replay.json"
fi
mkdir -p "$OUT/snapshots" "$OUT/tests"
cp -R runs/$TASK/snapshots/before runs/$TASK/snapshots/after "$OUT/snapshots/"
cp -R runs/$TASK/tests/before runs/$TASK/tests/after "$OUT/tests/"
cp -R runs/records "$OUT/records"
echo
echo "验证样例 $TASK 完成（$MODE），终端输出和产物在 $OUT/"
