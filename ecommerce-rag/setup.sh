#!/usr/bin/env bash
# Set up the benchmark on Linux or WSL (tested on Ubuntu under WSL).
# Needs git and uv (https://docs.astral.sh/uv/). Takes a few minutes the first time.
#
#   documents/, cases/questions.json  fetched from Hugging Face at pinned commits, checked by SHA-256
#   agent-src/ecommerce-rag-agent  the RAG pipeline, checked out at the commit in AGENT_COMMIT.txt
#   .venv-rag                     Python 3.13 with the pipeline's pinned dependencies
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

python3 fetch_data.py  # the PDFs and the questions, checked by SHA-256

read -r name sha < AGENT_COMMIT.txt
mkdir -p agent-src
[ -d "agent-src/$name/.git" ] || git clone -q "https://github.com/TalkingDB/$name.git" "agent-src/$name"
git -C "agent-src/$name" fetch -q origin "$sha" 2>/dev/null || true
git -C "agent-src/$name" checkout -q "$sha"

[ -d .venv-rag ] || uv venv -q -p 3.13 .venv-rag
VIRTUAL_ENV=.venv-rag uv pip install -q -r requirements.txt
echo "Setup done. Next: bash run.sh (needs OPENAI_API_KEY) or bash run.sh --local (needs Ollama)"
