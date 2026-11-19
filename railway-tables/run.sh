#!/usr/bin/env bash
# Run the benchmark, or ask a question about your own PDF.
#
#   bash run.sh                          reproduce the results in results/results.json
#   bash run.sh your.pdf "question" [--row-id PATTERN] [--columns "A,B,C"]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
S="$HERE/ttt-src"
export CE_DOCX_PAGINATE=0 CLIENT_MODE=direct
export PYTHONPATH="$S/module-ttt:$S/package-content-elementizer:$S/base-tdb-models:$S/base-tdb-clients:$S/base-tdb-helpers"
TTT="$HERE/.venv-ttt/bin/python"

if [ $# -eq 0 ]; then
  "$TTT" "$HERE/pipeline/score.py"
  "$TTT" "$HERE/pipeline/join_pages.py"
  (cd "$S/module-ttt" && "$TTT" "$HERE/pipeline/benchmark.py" --ttt)
  "$TTT" "$HERE/pipeline/make_images.py"
  exit 0
fi

pdf="$1"; question="$2"; shift 2
tables="$(mktemp --suffix=.json)"
"$HERE/.venv-extract/bin/python" "$HERE/pipeline/extract.py" "$pdf" "$tables"
(cd "$S/module-ttt" && "$TTT" "$HERE/pipeline/ask.py" "$tables" "$question" "$@")
