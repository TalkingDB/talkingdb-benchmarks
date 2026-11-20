#!/usr/bin/env bash
# Run the benchmark.
#
#   bash run.sh                      index the documents and run the 70 questions with OpenAI, 3 runs,
#                                    rewriting results/openai/ and the README result section
#                                    (needs OPENAI_API_KEY)
#   bash run.sh --local              the same with local models through Ollama, into results/local/
#   bash run.sh --answers            also have the bot answer from the same top 4, and check each
#                                    answer cites its evidence (one more model call per question)
#   bash run.sh --runs 1 --only Q01  a quick check on a few questions
#
# Without installs or an API key:
#   python3 fetch_data.py && python3 pipeline/score.py
#                                    fetch the saved OpenAI run from Hugging Face, re-score it
#                                    and check it matches summary.json
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

python3 pipeline/score.py --self-check  # the scoring rules still behave
.venv-rag/bin/python pipeline/benchmark.py "$@"
