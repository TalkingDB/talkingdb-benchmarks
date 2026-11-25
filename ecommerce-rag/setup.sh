#!/usr/bin/env bash
# Set up the benchmark on Linux, WSL or Git Bash on Windows.
# Needs git and uv (https://docs.astral.sh/uv/); uv also provides Python. Takes a few minutes the first time.
#
#   .venv-rag                         Python 3.13 with the pipeline's pinned dependencies
#   documents/, cases/questions.json  fetched from the private Hugging Face dataset at pinned commits,
#                                     checked by SHA-256; needs a token: hf auth login, or HF_TOKEN
#   agent-src/ecommerce-rag-agent     the RAG pipeline, checked out at the commit in AGENT_COMMIT.txt
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

[ -d .venv-rag ] || uv venv -q -p 3.13 .venv-rag
PY=.venv-rag/bin/python                 # Linux and WSL
[ -x "$PY" ] || PY=.venv-rag/Scripts/python.exe  # Windows
# A certificate path that does not exist (conda in Git Bash sets one) breaks every HTTPS call.
if [ -n "${SSL_CERT_FILE:-}" ] && [ ! -f "$SSL_CERT_FILE" ]; then unset SSL_CERT_FILE; fi

"$PY" fetch_data.py  # the PDFs and the questions, checked by SHA-256

read -r name sha < AGENT_COMMIT.txt
sha="${sha%$'\r'}"  # a Windows checkout can leave a CRLF line ending
mkdir -p agent-src
[ -d "agent-src/$name/.git" ] || git clone -q "https://github.com/TalkingDB/$name.git" "agent-src/$name"
git -C "agent-src/$name" fetch -q origin "$sha" 2>/dev/null || true
git -C "agent-src/$name" checkout -q "$sha"

VIRTUAL_ENV=.venv-rag uv pip install -q -r requirements.lock  # exact versions, dependencies included
echo "Setup done. Next: bash run.sh (needs OPENAI_API_KEY) or bash run.sh --local (needs Ollama)"
