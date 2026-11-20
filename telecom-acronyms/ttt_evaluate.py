"""Apply the saved benchmark's answer model and scoring to actual TalkingDB TTT results."""

import argparse
import json
from importlib.metadata import version
from pathlib import Path
from statistics import mean

from benchmark import (
    BASELINE,
    TOKEN_BUDGET,
    TOP_K,
    LocalModel,
    dataset_hash,
    named_specs,
    run_case,
    summarize_run,
)
from sources import CACHE, MODEL_REPO, MODEL_REVISION, ROOT, read_json
from ttt_rank import INPUTS, runtime_pins

TTT = "talkingdb_ttt"
REFERENCE = ROOT / "results/evaluation"


def checked_order(report, cases, entries):
    hashes = {name: dataset_hash(ROOT / name) for name in INPUTS}
    if report["dataset_hashes"] != hashes or report["commits"] != runtime_pins() or report["k"] != TOP_K:
        raise ValueError("The retrieval report does not match the current data, TTT pins or depth")
    if set(report["rankings"]) != {case["id"] for case in cases}:
        raise ValueError("The retrieval report must cover every evaluation question")
    for case in cases:
        item = report["rankings"][case["id"]]
        ids = item["evidence_ids"]
        from_hits = list(dict.fromkeys(value for hit in item["elements"] for value in hit["evidence_ids"]))[:TOP_K]
        if ids != from_hits or len(item["elements"]) > TOP_K or item["retrieval_seconds"] < 0:
            raise ValueError(f"Invalid evidence order or retrieval time: {case['id']}")
        scope = named_specs(case["question"])
        if any(value not in entries or (scope and entries[value]["spec"] not in scope) for value in ids):
            raise ValueError(f"Invalid evidence or document scope: {case['id']}")
    return hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=CACHE / "model")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out must point to a new directory to preserve saved runs")
    report = read_json(args.rankings.resolve())
    specs, entries, cases = (read_json(name) for name in ("sources.json", "definitions.json", INPUTS[0]))
    by_id = {entry["id"]: entry for entry in entries}
    hashes = checked_order(report, cases, by_id)
    reference = read_json(REFERENCE / "summary.json")
    if (reference["dataset_hashes"] != hashes or reference["model"]["id"] != MODEL_REPO
            or reference["model"]["revision"] != MODEL_REVISION or reference["budget"] != TOKEN_BUDGET):
        raise ValueError("The baseline must use the same data, answer model and token budget")
    if any(reference["model"][name] != version(name) for name in ("onnxruntime", "tokenizers")):
        raise ValueError("Install the same answer runtime as the saved baseline")
    baseline = [row for line in (REFERENCE / "per-case.jsonl").read_text(encoding="utf-8").splitlines()
                if (row := json.loads(line))["arm"] == BASELINE]
    model = LocalModel(args.model_dir, args.threads)
    args.out.mkdir(parents=True)
    evaluated = []
    with (args.out / "per-case.jsonl").open("x", encoding="utf-8", newline="\n") as output:
        for offset, case in enumerate(cases, 1):
            item = report["rankings"][case["id"]]
            ordered = [by_id[value] for value in item["evidence_ids"]]
            row = run_case(case, TTT, entries, specs, None, model, None, ranking=ordered)
            row["retrieval_seconds"] = item["retrieval_seconds"]
            evaluated.append(row)
            output.write(json.dumps(row) + "\n")
            output.flush()
            if offset % 10 == 0 or offset == len(cases):
                print(f"TTT answers: {offset}/{len(cases)}", flush=True)
    summary = {"dataset_hashes": hashes, "rankings_sha256": dataset_hash(args.rankings),
               "ttt_commits": report["commits"], "ttt_versions": report["versions"],
               "model": reference["model"], "baseline": BASELINE, "budget": TOKEN_BUDGET, "k": TOP_K,
               "mean_ttt_retrieval_seconds": round(mean(row["retrieval_seconds"] for row in evaluated), 4)}
    summary.update(summarize_run({BASELINE: baseline, TTT: evaluated}))
    with (args.out / "summary.json").open("x", encoding="utf-8", newline="\n") as output:
        json.dump(summary, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
