"""Download the benchmark data from Hugging Face and check every file by SHA-256.

The six PDFs and the questions live in the dataset
https://huggingface.co/datasets/TalkingDB/ecommerce-rag , not in git. DATA.txt lists each
file with its SHA-256, the dataset commit it is fetched from, its path in the dataset and
its path here. Fetching from a fixed commit means later uploads to the dataset never change
this benchmark. Plain Python 3, no installs.

Usage: python3 fetch_data.py           download what is missing or changed
       python3 fetch_data.py --check   only check the files already here
"""

import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = "https://huggingface.co/datasets/TalkingDB/ecommerce-rag/resolve/"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest():
    """(sha256, dataset commit, path in the dataset, path here) for each file."""
    for line in (HERE / "DATA.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, commit, remote, local = line.split("\t")
            yield digest, commit, remote, local


def main(check_only=False):
    bad = []
    for digest, commit, remote, rel in manifest():
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
            urllib.request.urlretrieve(f"{DATASET}{commit}/{urllib.parse.quote(remote)}", tmp)
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
