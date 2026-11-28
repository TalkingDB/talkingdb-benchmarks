"""Download the benchmark data from Hugging Face and check every file by SHA-256.

The two public PDFs and the saved extraction output are kept out of git, in the
dataset https://huggingface.co/datasets/TalkingDB/railway-tables , fetched from one
pinned dataset commit. DATA.txt lists each file with its SHA-256. Plain Python 3, no installs.

Usage: python3 fetch_data.py           download what is missing or changed
       python3 fetch_data.py --check   only check the files already here
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The dataset commit these files are fetched from, so later uploads to the dataset never
# change what an older checkout of this benchmark downloads.
REVISION = "036eaa607fecf78a69540096469405b0fe22df0e"
BASE = f"https://huggingface.co/datasets/TalkingDB/railway-tables/resolve/{REVISION}/"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest():
    for line in (HERE / "DATA.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split(maxsplit=1)
            yield digest, rel


def main(check_only=False):
    bad = []
    for digest, rel in manifest():
        path = HERE / rel
        if path.exists() and sha256(path) == digest:
            print(f"ok       {rel}")
            continue
        if check_only:
            bad.append(rel)
            print(f"missing  {rel}" if not path.exists() else f"CHANGED  {rel}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        try:
            urllib.request.urlretrieve(BASE + rel, tmp)
        except OSError as e:
            bad.append(rel)
            print(f"FAILED   {rel}: {e}")
            continue
        if sha256(tmp) != digest:
            tmp.unlink()
            bad.append(rel)
            print(f"WRONG    {rel}: downloaded file does not match DATA.txt")
            continue
        tmp.replace(path)
        print(f"fetched  {rel}")
    if bad:
        sys.exit(f"{len(bad)} file(s) not ready: {', '.join(bad)}")


if __name__ == "__main__":
    main(check_only="--check" in sys.argv)
