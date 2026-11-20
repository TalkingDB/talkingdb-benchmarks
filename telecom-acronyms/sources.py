"""Fetch pinned PDFs and verify the evidence rows against their original pages."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
MODEL_REPO = "HuggingFaceTB/SmolLM2-360M-Instruct"
MODEL_REVISION = "a10cc1512eabd3dde888204e902eca88bddb4951"
MODEL_FILES = {
    "tokenizer.json": "9ca9acddb6525a194ec8ac7a87f24fbba7232a9a15ffa1af0c1224fcd888e47c",
    "onnx/model_q4.onnx": "a4ffda96e65beafc6f6cef0cbcf9fdc1cbdd79c230906bf3897d190547c7a596",
}


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def file_hash(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def ensure_file(path, url, digest, fetch):
    if path.is_file() and file_hash(path) == digest:
        return
    if not fetch:
        raise ValueError(f"Missing file or checksum mismatch: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
    try:
        subprocess.run(
            ["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
             "--max-time", "900", "--output", str(temporary), url], check=True,
        )
        if file_hash(temporary) != digest:
            raise ValueError(f"Downloaded bytes differ from the manifest: {url}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def model_files(directory, fetch=False):
    for filename, digest in MODEL_FILES.items():
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{filename}"
        ensure_file(directory / Path(filename).name, url, digest, fetch)


def pdf_lines(page):
    rows = {}
    for left, top, _, _, word, *_ in page.get_text("words"):
        rows.setdefault(round(top, 1), []).append((left, word))
    return [" ".join(word for _, word in sorted(words)) for _, words in sorted(rows.items())]


def verify_sources(directory, fetch=False):
    import pymupdf

    specs = read_json("sources.json")
    entries = read_json("definitions.json")
    for spec, source in specs.items():
        path = directory / f"{spec}.pdf"
        ensure_file(path, source["url"], source["sha256"], fetch)
        with pymupdf.open(path) as pdf:
            last_clause = None
            pages = {}
            spec_entries = [entry for entry in entries if entry["spec"] == spec]
            for number in range(1, max(entry["pdf_page"] for entry in spec_entries) + 1):
                lines = pdf_lines(pdf[number - 1])
                if len(lines) == 0:
                    continue
                for line in lines:
                    heading = re.fullmatch(r"(3(?:\.\d+)+)\s+(?:Abbreviations|Symbols and abbreviations)", line)
                    if heading:
                        last_clause = heading[1]
                pages[number] = lines, last_clause
            for entry in spec_entries:
                lines, clause = pages[entry["pdf_page"]]
                header = re.search(r"Release \d+\)?\s+(\d+)\s+ETSI", lines[0])
                row = f"{entry['acronym']} {entry['expansion']}"
                if not header or int(header[1]) != entry["printed_page"] or row not in lines or clause != entry["clause"]:
                    raise ValueError(f"Source row or pagination changed: TS {spec}, {entry['id']}")
    return len(specs), len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--model", action="store_true", help="also check or download the pinned model")
    parser.add_argument("--pdf-dir", type=Path, default=CACHE / "pdfs")
    parser.add_argument("--model-dir", type=Path, default=CACHE / "model")
    args = parser.parse_args()
    documents, rows = verify_sources(args.pdf_dir, args.fetch)
    print(f"Verified {rows} definition rows against {documents} pinned ETSI PDFs.", flush=True)
    if args.model:
        model_files(args.model_dir, args.fetch)
        print(f"Verified {MODEL_REPO} at {MODEL_REVISION}.")


if __name__ == "__main__":
    main()
