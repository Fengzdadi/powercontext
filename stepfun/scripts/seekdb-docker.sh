#!/usr/bin/env bash
# Local seekdb server for the app, in its own Docker container (does not touch any other container).
#   bash scripts/seekdb-docker.sh start|stop|status|logs|reset
# Overrides: SEEKDB_CONTAINER (stepfun-seekdb), SEEKDB_PORT (12881), SEEKDB_IMAGE (default: the tested
# seekdb 1.4.0 build; set oceanbase/seekdb:latest to follow upstream), SEEKDB_MEMORY (4G), SEEKDB_CPU (4).
set -euo pipefail

NAME="${SEEKDB_CONTAINER:-stepfun-seekdb}"
PORT="${SEEKDB_PORT:-12881}"
IMAGE="${SEEKDB_IMAGE:-oceanbase/seekdb:1.4.0-100000172026082615}"
VOLUME="${NAME}-data"

wait_ready() {
  printf 'waiting for seekdb on 127.0.0.1:%s ' "$PORT"
  for _ in $(seq 1 180); do
    if docker exec "$NAME" mysql -h127.0.0.1 -P2881 -uroot -e "SELECT 1" >/dev/null 2>&1; then
      echo "ready"
      docker exec "$NAME" mysql -h127.0.0.1 -P2881 -uroot -N -e "SELECT VERSION()"
      return 0
    fi
    printf '.'
    sleep 2
  done
  echo "timed out; see: docker logs $NAME" >&2
  return 1
}

case "${1:-start}" in
  start)
    if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
      echo "container $NAME already running"
    elif docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
      docker start "$NAME" >/dev/null
    else
      docker run -d --name "$NAME" -p "${PORT}:2881" \
        -e CPU_COUNT="${SEEKDB_CPU:-4}" -e MEMORY_LIMIT="${SEEKDB_MEMORY:-4G}" \
        -e LOG_DISK_SIZE=4G -e DATAFILE_SIZE=2G \
        -v "${VOLUME}:/var/lib/seekdb" "$IMAGE" >/dev/null
    fi
    wait_ready
    ;;
  stop) docker stop "$NAME" ;;
  status) docker ps -a --filter "name=^${NAME}$" --format '{{.Names}}  {{.Status}}  {{.Ports}}' ;;
  logs) docker logs --tail 50 "$NAME" ;;
  reset)
    # Removes this app's container and its data volume only.
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker volume rm "$VOLUME" >/dev/null 2>&1 || true
    echo "removed $NAME and volume $VOLUME"
    ;;
  *) echo "usage: $0 start|stop|status|logs|reset" >&2; exit 2 ;;
esac
