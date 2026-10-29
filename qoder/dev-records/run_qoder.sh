#!/usr/bin/env bash
# How every Qoder development session in this project was run.
#   dev-records/run_qoder.sh <session-name> <prompt-file> [extra qoderclicn args, e.g. -m GLM-5.3]
# The complete stream-json transcript goes to dev-records/sessions/<session-name>.jsonl,
# with start/finish timestamps next to it. Commands Qoder may run without asking are
# listed in ALLOWED (plus EXTRA_ALLOWED from the environment, for a session that needs
# more, such as the Docker one); file edits are allowed by --permission-mode accept_edits.
# Allowed-command patterns match whole words, so scripts are listed by their exact path.
set -euo pipefail

# The whole body is a function, so bash parses all of it before running: editing this
# file while a session is running cannot change what the running copy does.
main() {
here="$(cd "$(dirname "$0")" && pwd)"
project="$(cd "$here/.." && pwd)"          # the qoder/ directory
name="$1"; prompt="$2"; shift 2
out="$here/sessions/$name"

ALLOWED="Bash(uv:*),Bash(python3:*),Bash(python:*),Bash(.venv/bin/python:*),Bash(curl:*),\
Bash(docker exec examradar-dev-seekdb:*),Bash(ls:*),Bash(cat:*),Bash(head:*),Bash(tail:*),\
Bash(grep:*),Bash(rg:*),Bash(find:*),Bash(wc:*),Bash(sed -n:*),Bash(sort:*),Bash(diff:*),\
Bash(file:*),Bash(shasum:*),Bash(jq:*),Bash(tree:*),Bash(pwd:*),Bash(echo:*),Bash(test:*),\
Bash(cd:*),Bash(env:*),Bash(export:*),Bash(source:*),Bash(sleep:*),Bash(xargs:*),\
Bash(mkdir:*),Bash(chmod:*),Bash(bash scripts/load_sample.sh:*),Bash(bash ../scripts/load_sample.sh:*),\
Bash(scripts/load_sample.sh:*),Bash(./scripts/load_sample.sh:*),Bash(../scripts/load_sample.sh:*),\
Bash(nohup:*),Bash(lsof:*),Bash(kill:*),Bash(which:*),Bash(.venv/bin/uvicorn:*),Bash(.venv/bin/pytest:*)"
ALLOWED="$ALLOWED${EXTRA_ALLOWED:+,$EXTRA_ALLOWED}"

date '+%Y-%m-%dT%H:%M:%S%z' > "$out.started"
set +e
qoderclicn -p "$(cat "$prompt")" -w "$project" --permission-mode accept_edits \
  --allowed-tools "$ALLOWED" -o stream-json -n "$name" "$@" > "$out.jsonl" 2> "$out.stderr"
status=$?
set -e
date '+%Y-%m-%dT%H:%M:%S%z' > "$out.finished"
python3 - "$out.jsonl" <<'EOF'
import json, sys
res = None
for line in open(sys.argv[1], encoding="utf-8"):
    try:
        d = json.loads(line)
    except ValueError:
        continue
    if d.get("type") == "result":
        res = d
if res:
    print({k: res.get(k) for k in ("subtype", "num_turns", "duration_ms", "total_credits", "is_error", "session_id")})
    print("denials:", res.get("permission_denials"))
EOF
return $status
}
main "$@"
