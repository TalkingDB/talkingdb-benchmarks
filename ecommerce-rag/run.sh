#!/usr/bin/env bash
# Run the benchmark.
#
#   bash run.sh                      index the documents and run every question with OpenAI, 3 runs,
#                                    rewriting results/openai/ and the README result section
#                                    (needs OPENAI_API_KEY)
#   bash run.sh --local              the same with local models through Ollama, into results/local/
#   bash run.sh --answers            also have the bot answer from the same top 4, and check each
#                                    answer cites its evidence (one more model call per question)
#   bash run.sh --runs 1 --only Q01  a quick check on a few questions
#
# Without installs or an API key:
#   python3 fetch_data.py && python3 pipeline/score.py
#                                    fetch the questions from Hugging Face, re-score the saved run
#                                    and check it matches summary.json
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PY=.venv-rag/bin/python                 # Linux and WSL
[ -x "$PY" ] || PY=.venv-rag/Scripts/python.exe  # Windows (Git Bash)
[ -x "$PY" ] || { echo "No .venv-rag found. Run: bash setup.sh"; exit 1; }
# A certificate path that does not exist (conda in Git Bash sets one) breaks every HTTPS call.
if [ -n "${SSL_CERT_FILE:-}" ] && [ ! -f "$SSL_CERT_FILE" ]; then unset SSL_CERT_FILE; fi

"$PY" pipeline/score.py --self-check  # the scoring rules still behave
"$PY" pipeline/benchmark.py "$@"
