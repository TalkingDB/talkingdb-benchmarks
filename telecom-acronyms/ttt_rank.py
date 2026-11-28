"""Rank telecom evidence with the same TalkingDB TTT runtime as the railway benchmark."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from importlib import import_module
from importlib.metadata import version
from pathlib import Path

from benchmark import TOP_K, dataset_hash, named_specs
from sources import ROOT, read_json

RAILWAY = ROOT.parent / "railway-tables"
INPUTS = ("cases/evaluation.json", "sources.json", "definitions.json")


def runtime_pins():
    return dict(line.split() for line in (RAILWAY / "TTT_COMMITS.txt").read_text().splitlines() if line.strip())


def load_runtime(tree, pins):
    for name, expected in pins.items():
        checkout = tree / name
        actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        changes = subprocess.check_output(
            ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"], text=True,
        ).strip()
        if actual != expected or changes:
            raise ValueError(f"Need an unmodified checkout of {name} at {expected}")
    sys.path[:0] = [str(tree / name) for name in pins]
    sys.path.append(str(RAILWAY / "pipeline"))
    os.environ["CLIENT_MODE"] = "direct"
    os.environ["CE_DOCX_PAGINATE"] = "0"
    os.chdir(tree / "module-ttt")
    railway = import_module("ask")
    extractor = import_module("app.services.extractor").ExtractorService
    return railway.index, extractor


def rank_cases(definitions, specs, cases, index, extractor):
    graph_ids = {}
    for spec, source in specs.items():
        rows = [{"cells": [entry["id"], entry["acronym"], entry["expansion"], entry["clause"]],
                 "page": entry["printed_page"]} for entry in definitions if entry["spec"] == spec]
        graph_ids[spec] = index([rows], ["Evidence ID", "Acronym", "Expansion", "Clause"],
                                f"TS {spec}. {source['summary']}")
        print(f"Indexed TS {spec}: {len(rows)} definition rows", flush=True)

    ids_by_graph = {graph: {e["id"] for e in definitions if e["spec"] == spec}
                    for spec, graph in graph_ids.items()}
    rankings = {}
    for offset, case in enumerate(cases, 1):
        scope = named_specs(case["question"])
        graphs = [graph for spec, graph in graph_ids.items() if not scope or spec in scope]
        start = time.perf_counter()
        hits = extractor(graphs, max_matches=TOP_K).extract(query=case["question"])["elements"] if graphs else []
        seconds = round(time.perf_counter() - start, 4)
        evidence = []
        elements = []
        for hit in hits:
            content = str(hit["content"])
            ids = [value for value in re.findall(r"\bE\d{2}\b", content) if value in ids_by_graph[hit["graph_id"]]]
            evidence.extend(ids)
            elements.append({"type": hit["type"], "content": content, "score": hit["score"], "evidence_ids": ids})
        rankings[case["id"]] = {"evidence_ids": list(dict.fromkeys(evidence))[:TOP_K],
                                "retrieval_seconds": seconds, "elements": elements}
        if offset % 10 == 0 or offset == len(cases):
            print(f"TTT retrieval: {offset}/{len(cases)}", flush=True)
    return rankings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttt-src", type=Path, required=True, help="checkout directory created by the railway setup")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    destination = args.out.resolve()
    if destination.exists():
        parser.error("--out must point to a new file to preserve saved runs")
    pins = runtime_pins()
    index, extractor = load_runtime(args.ttt_src.resolve(), pins)
    definitions, specs, cases = (read_json(name) for name in ("definitions.json", "sources.json", INPUTS[0]))
    rankings = rank_cases(definitions, specs, cases, index, extractor)
    report = {"commits": pins, "python": sys.version.split()[0], "versions": {package: version(package) for package in
              ("spacy", "en-core-web-md", "networkx", "python-docx")}, "k": TOP_K,
              "dataset_hashes": {name: dataset_hash(ROOT / name) for name in INPUTS}, "rankings": rankings}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
