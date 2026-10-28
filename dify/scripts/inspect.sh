#!/usr/bin/env bash
# 直接查看 seekdb 和 PowerContext 里的真实数据，用来核对 Dify 对话里说的「编入判例集」「记在小本本上」。
# 用法：scripts/inspect.sh [原告昵称] [检索词]
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
PLAYER="${1:-阿强}"
QUERY="${2:-闹钟 周末 吵醒}"
HOST="${BIND_ADDRESS:-127.0.0.1}"
COURT="http://$HOST:${COURT_API_HOST_PORT:-18080}"
PC="http://$HOST:${POWERCONTEXT_HOST_PORT:-18000}"
json() { python3 -c "import json,sys; print(json.dumps(dict(zip(sys.argv[1::2], sys.argv[2::2])), ensure_ascii=False))" "$@"; }

echo "== court-api 健康检查（seekdb 连接、向量模型、混合检索方式）"
curl -fsS "$COURT/health"; echo

echo; echo "== seekdb：cases 表里由玩家诉讼产生的案件（SQL 直接查询）"
docker compose exec -T seekdb mysql -h127.0.0.1 -P2881 -uroot -p"$SEEKDB_ROOT_PASSWORD" court -e \
  "SELECT case_no, status, plaintiff, defendant, outcome, title FROM cases WHERE source = 'player' ORDER BY id;
   SELECT source, status, COUNT(*) AS n FROM cases GROUP BY source, status;" 2>/dev/null

echo; echo "== seekdb：DBMS_HYBRID_SEARCH 混合检索「$QUERY」（court-api /api/search）"
curl -fsS -X POST "$COURT/api/search" -H 'Content-Type: application/json' \
  -d "$(json query "$QUERY")" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("mode:", d["mode"])
for p in d["precedents"]:
    print(" ", p["case_no"], p["title"], "score=%s" % p.get("score"), "matched_by=%s" % p.get("matched_by"))
for s in d["statutes"]:
    print("  法典第%s条 %s" % (s["article_no"], s["title"]))'

echo; echo "== PowerContext：原告「$PLAYER」的记忆（/v1/atomic-memory/list）"
SCOPE=$(curl -fsS -X POST "$PC/v1/scopes" -H 'Content-Type: application/json' \
  -d "$(json title "鸡毛蒜皮法庭·原告 $PLAYER" summary "喵青天法庭为原告「$PLAYER」建立的案底档案" idempotency_key "jimao-court:player:$PLAYER")" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["scope_id"])')
echo "scope_id: $SCOPE"
curl -fsS -X POST "$PC/v1/atomic-memory/list" -H 'Content-Type: application/json' \
  -d "{\"scope_id\": \"$SCOPE\", \"limit\": 30}" | python3 -c '
import json, sys
items = json.load(sys.stdin).get("items", [])
print("共 %d 条" % len(items))
for i in items:
    print("  [%s/%s] %s" % (i.get("kind"), i.get("state"), i.get("text")))'

echo; echo "== PowerContext：立案时法官看到的 PreparedContext（/v1/context/prepare）"
curl -fsS -X POST "$PC/v1/context/prepare" -H 'Content-Type: application/json' \
  -d "{\"scope_id\": \"$SCOPE\", \"query\": $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1], ensure_ascii=False))' "喵青天 $PLAYER"), \"max_bytes\": 2000}" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("status:", d.get("status")); print((d.get("content") or "（没有可召回的记忆）")[:1500])'
