#!/usr/bin/env bash
# Import all sample course materials into examradar.
# syllabus.txt is NOT imported: the exam scope is an input for coverage
# analysis (M2), not course material.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMPLES="$PROJECT_DIR/samples/course-db"
COURSE="db101"

cd "$PROJECT_DIR/app"

echo "=== ExamRadar: importing sample course materials ==="
echo "Course: $COURSE"
echo "Samples: $SAMPLES"
echo ""

import_file() {
    local file="$1"
    local kind="$2"
    local name
    name=$(basename "$file")
    echo -n "  $name ($kind) ... "
    .venv/bin/python -m examradar.cli import "$file" --course "$COURSE" --kind "$kind" | tail -1
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
echo "=== Import complete ==="
