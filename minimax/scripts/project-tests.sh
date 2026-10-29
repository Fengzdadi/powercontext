#!/usr/bin/env bash
# 不经过 sddctx，直接在一个工程目录里运行 T-101 的目标测试和回归测试（在 sddctx 镜像里执行，Python 3.12 + pytest 9.1.1）。
#
#   scripts/project-tests.sh project                              修改前：目标测试应全部失败（断言失败），回归测试应全部通过
#   scripts/project-tests.sh evidence/T-101/snapshots/after       修改后：目标测试和回归测试都应全部通过
#
# 目录必须在 minimax/ 之内（容器里挂载为 /workspace）。也可以自己复制 project/ 后用
#   patch -p1 -d <副本目录> < evidence/T-101/change.patch
# 应用 MiniMax 的修改再运行本脚本。
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="${1:?用法：scripts/project-tests.sh <工程目录>}"
DIR="${DIR%/}"
[ -f "$DIR/sdd.toml" ] || { echo "$DIR 不是业务工程目录（缺少 sdd.toml）" >&2; exit 2; }
TARGET=tests/test_api_books_filters.py
run() {
  echo "\$ (cd $DIR && python -m pytest -q $*)"
  set +e
  docker compose --progress quiet run --rm --no-deps -T --workdir "/workspace/$DIR" --entrypoint python sddctx -m pytest -q -p no:cacheprovider "$@"
  local code=$?
  set -e
  echo "# exit code: $code"
}
echo "# 工程目录：$DIR"
echo "# 目标测试（CAT-007、CAT-008）"
run "$TARGET"
echo
echo "# 回归测试（除目标测试外的全部测试）"
run --deselect "$TARGET"
