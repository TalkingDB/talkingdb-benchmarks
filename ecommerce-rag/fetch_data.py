"""Download the benchmark data from Hugging Face and check every file by SHA-256.

The six PDFs and the questions live in the private dataset
https://huggingface.co/datasets/TalkingDB/ecommerce-rag , not in git. DATA.txt lists each
file with its SHA-256, the dataset commit it is fetched from, its path in the dataset and
its path here. Fetching from a fixed commit means later uploads to the dataset never change
this benchmark. Plain Python 3, no installs.

The dataset is private, so downloading needs a Hugging Face token from an account with
access to it, found in this order: the HF_TOKEN environment variable, HF_TOKEN in this
folder's .env file, or the token saved by `hf auth login`.

Usage: python3 fetch_data.py           download what is missing or changed
       python3 fetch_data.py --check   only check the files already here (no token needed)
"""

import hashlib
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = "huggingface.co"
DATASET = f"https://{HOST}/datasets/TalkingDB/ecommerce-rag/resolve/"
NO_ACCESS = (
    "The dataset TalkingDB/ecommerce-rag is private. Use a Hugging Face account with access to it, "
    "then either run `hf auth login`, export HF_TOKEN=hf_..., or add HF_TOKEN=hf_... to {env}."
)


def hf_token():
    """The Hugging Face token: HF_TOKEN, then .env here, then the token `hf auth login` saved."""
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            value = value.strip().strip("'\"")
            if key.strip().removeprefix("export ").strip() == "HF_TOKEN" and value and value != "hf_...":
                return value  # hf_... is the placeholder from .env.example
    saved = os.environ.get("HF_TOKEN_PATH") or Path(
        os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "token"
    saved = Path(saved)
    if saved.exists() and saved.read_text(encoding="utf-8").strip():
        return saved.read_text(encoding="utf-8").strip()
    return None


class KeepTokenOnHost(urllib.request.HTTPRedirectHandler):
    """Send the token only to huggingface.co. Files are served from a signed link on another
    host, which must not receive it (and would refuse a second form of authorization)."""

    def __init__(self, token):
        self.token = token

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and self.token and urllib.parse.urlsplit(new.full_url).hostname == HOST:
            new.add_unredirected_header("Authorization", f"Bearer {self.token}")
        return new


def download(url, dest, token):
    req = urllib.request.Request(url, headers={"User-Agent": "talkingdb-benchmarks-fetch"})
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")  # never copied to a redirect
    opener = urllib.request.build_opener(KeepTokenOnHost(token))
    with opener.open(req, timeout=120) as resp, open(dest, "wb") as out:
        while block := resp.read(1 << 20):
            out.write(block)


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
    token = None if check_only else hf_token()
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
            download(f"{DATASET}{commit}/{urllib.parse.quote(remote)}", tmp, token)
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            if e.code in (401, 403, 404):
                # Hugging Face answers 401 (or 404) for a private dataset the token cannot read.
                sys.exit(f"FAILED   {rel}: HTTP {e.code}.\n"
                         + ("No Hugging Face token found. " if not token else "This token has no access. ")
                         + NO_ACCESS.format(env=HERE / ".env"))
            bad.append(rel)
            print(f"FAILED   {rel}: {e}")
            continue
        except OSError as e:
            tmp.unlink(missing_ok=True)
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
