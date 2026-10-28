#!/usr/bin/env bash
# 等待 seekdb、court-api、PowerContext 全部 healthy（PowerContext 首次初始化可能要几分钟）。
set -euo pipefail
cd "$(dirname "$0")/.."
deadline=$((SECONDS + ${WAIT_TIMEOUT:-900}))
for svc in seekdb court-api powercontext; do
  printf '等待 %s ' "$svc"
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q "$svc")" 2>/dev/null)" = healthy ]; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo; echo "超时：$svc 还没有就绪，请查看 docker compose logs $svc" >&2; exit 1
    fi
    printf '.'; sleep 5
  done
  echo ' ok'
done
echo "全部就绪。"
