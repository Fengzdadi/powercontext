#!/usr/bin/env bash
# Import all sample course materials into ExamRadar via the HTTP API, so the
# same script serves both local dev and Docker deployments (set APP_URL).
# syllabus.txt is NOT imported: the exam scope is an input for coverage
# analysis (M2), not course material.
# Re-running is safe: the server deduplicates by (course, sha256).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMPLES="$PROJECT_DIR/samples/course-db"
COURSE="db101"
APP_URL="${APP_URL:-http://127.0.0.1:18800}"

if ! curl -sf -o /dev/null "$APP_URL/"; then
    echo "ERROR: ExamRadar is not reachable at $APP_URL" >&2
    echo "Start it first, or set APP_URL, e.g.:" >&2
    echo "  APP_URL=http://127.0.0.1:18807 bash scripts/load_sample.sh" >&2
    exit 1
fi

echo "=== ExamRadar: importing sample course materials ==="
echo "App:     $APP_URL"
echo "Course:  $COURSE"
echo "Samples: $SAMPLES"
echo ""

TOTAL=0

import_file() {
    local file="$1"
    local kind="$2"
    local name resp out count
    name=$(basename "$file")
    resp=$(curl -sf -X POST "$APP_URL/api/documents" \
        -H "X-ExamRadar-Source: auto" \
        -F "file=@$file" \
        -F "course_id=$COURSE" \
        -F "doc_kind=$kind")
    # python prints "<chunk_count>\t<display line>" so bash can total it
    out=$(python3 -c '
import json, sys
name, kind, raw = sys.argv[1], sys.argv[2], sys.argv[3]
r = json.loads(raw)
n = r.get("chunk_count", 0)
state = "skip (already imported)" if r.get("skipped") else "new"
print("%d\t%s (%s): %d chunks, %s" % (n, name, kind, n, state))
' "$name" "$kind" "$resp")
    count=${out%%$'\t'*}
    TOTAL=$((TOTAL + count))
    echo "  ${out#*$'\t'}"
}

echo "--- Notes ---"
for f in "$SAMPLES"/notes/*.md; do
    import_file "$f" notes
done

echo ""
echo "--- Slides ---"
for f in "$SAMPLES"/slides/*.pdf; do
    import_file "$f" slides
done

echo ""
echo "--- Exams ---"
for f in "$SAMPLES"/exams/*.pdf; do
    import_file "$f" exam
done

echo ""
echo "--- Papers ---"
for f in "$SAMPLES"/papers/*.pdf; do
    import_file "$f" paper
done

echo ""
echo "=== Import complete: $TOTAL chunks total ==="
