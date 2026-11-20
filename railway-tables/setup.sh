#!/usr/bin/env bash
# Set up both steps on Linux or WSL (tested on Ubuntu under WSL, CPU only).
# Needs git and uv (https://docs.astral.sh/uv/). Takes about ten minutes the first time.
#
#   .venv-extract   step 1, the open source PDF table extractor
#   .venv-ttt       steps 2 and 3, TalkingDB TTT at the commits in TTT_COMMITS.txt
#   ttt-src/        public TalkingDB repositories, checked out at those commits
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

[ -d .venv-extract ] || uv venv -q -p 3.14 .venv-extract
VIRTUAL_ENV=.venv-extract uv pip install -q --torch-backend cpu -r requirements-extract.txt  # CPU build of torch, no GPU libraries

mkdir -p ttt-src
while read -r name sha; do
  [ -z "$name" ] && continue
  [ -d "ttt-src/$name/.git" ] || git clone -q "https://github.com/TalkingDB/$name.git" "ttt-src/$name"
  git -C "ttt-src/$name" fetch -q origin "$sha" 2>/dev/null || true
  git -C "ttt-src/$name" checkout -q "$sha"
done < TTT_COMMITS.txt

[ -d .venv-ttt ] || uv venv -q -p 3.13 .venv-ttt
VIRTUAL_ENV=.venv-ttt uv pip install -q -r requirements-ttt.txt
echo "Setup done. Next: bash run.sh"
