#!/usr/bin/env bash
# Rebuild the sample PDFs from the HTML sources in this folder with headless Chrome/Chromium.
# The committed PDFs were produced this way; you only need this script if you edit the HTML.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="$here/.."
chrome="${CHROME:-}"
if [[ -z "$chrome" ]]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" google-chrome chromium chromium-browser; do
    if command -v "$c" >/dev/null 2>&1 || [[ -x "$c" ]]; then chrome="$c"; break; fi
  done
fi
[[ -n "$chrome" ]] || { echo "Chrome/Chromium not found; set CHROME=/path/to/chrome" >&2; exit 1; }

render() {  # render <html> <pdf>
  "$chrome" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$2" "file://$here/$1" 2>/dev/null
  echo "wrote $2"
}
mkdir -p "$out/slides" "$out/exams" "$out/papers"
render lecture07-recovery.html  "$out/slides/第7讲-故障恢复.pdf"
render exam-2025-final.html     "$out/exams/2025-2026-1-期末试卷A.pdf"
render reading-2pc-primer.html  "$out/papers/two-phase-commit-primer.pdf"
