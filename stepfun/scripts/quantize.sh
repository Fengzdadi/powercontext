#!/usr/bin/env bash
# Runs scripts/quantize.py in a throwaway uv environment with pinned package versions.
# Without uv: pip install onnx==1.23.2 onnxruntime==1.31.1 onnxconverter-common==1.16.0 tokenizers==0.23.3 numpy==2.3.4
#             python scripts/quantize.py
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found: install it (https://docs.astral.sh/uv/) or use the pip command at the top of $0" >&2
  exit 1
fi
exec uv run --no-project --python ">=3.10" \
  --with onnx==1.23.2 \
  --with onnxruntime==1.31.1 \
  --with onnxconverter-common==1.16.0 \
  --with tokenizers==0.23.3 \
  --with numpy==2.3.4 \
  python -I scripts/quantize.py "$@"
