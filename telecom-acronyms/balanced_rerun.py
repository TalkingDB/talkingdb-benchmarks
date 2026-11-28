"""Rerun the answer step with every option shown at every letter.

In the published run each question showed its options in one fixed shuffled order,
and the small model chose letter C in 359 of 371 decisions. A method's score therefore
depended mostly on whether the right row happened to sit at C. This rerun keeps
everything else fixed: the same pinned model, the same prompt and, for every method,
the exact rows that method showed (read from the saved per question results). It only
rotates the options, so each option appears once at every letter.

Rotation 0 is the published order. It must reproduce the saved choice and its option
scores, so a run on a different machine or model stops at the first mismatch.

Usage:
    python balanced_rerun.py [--threads 8] [--max-minutes N]
    python balanced_rerun.py --summary-only

Run python fetch_data.py and python sources.py --model first. The run resumes from
results/balanced/per-run.jsonl, so it can be stopped and started again; the summary
is written once every run is present.
"""

import argparse
import hashlib
import importlib
import json
import random
import sys
import time
from collections import Counter, defaultdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from statistics import mean

from benchmark import BASELINE, LocalModel, answer_options, dataset_hash, prompt, score_answer
from sources import CACHE, MODEL_REPO, MODEL_REVISION, ROOT, read_json

SAVED = ("results/evaluation/per-case.jsonl", "results/ttt/scored/per-case.jsonl")
ARMS = ("no_glossary", "glossary_in_system_prompt", "glossary_full", "talkingdb_ttt",
        "bm25", "bge_dense", "scoped_prototype")
OUT = ROOT / "results/balanced"
TOLERANCE = 1e-3


def installed(name):
    try:
        return version(name)
    except PackageNotFoundError:
        try:
            return getattr(importlib.import_module(name), "__version__", "unknown")
        except ImportError:
            return "not installed"


def saved_decisions():
    rows = {}
    for path in SAVED:
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rows[(row["id"], row["arm"])] = row
    return rows


def rotations(options):
    letters, choices = list(options), list(options.values())
    for r in range(len(choices)):
        yield r, dict(zip(letters, choices[r:] + choices[:r]))


def plan(cases, saved, arms=ARMS):
    for case in cases:
        for arm in arms:
            yield case, arm, saved[(case["id"], arm)]


def run(args):
    entries, specs = read_json("definitions.json"), read_json("sources.json")
    defs = {e["id"]: e for e in entries}
    cases, saved = read_json("cases/evaluation.json"), saved_decisions()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "per-run.jsonl"
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done.add((row["id"], row["arm"], row["rotation"]))
    todo = [(c, a, s, r, o) for c, a, s in plan(cases, saved, args.arms)
            for r, o in rotations(answer_options(c, entries)) if (c["id"], a, r) not in done]
    print(f"{len(done)} runs already saved, {len(todo)} to go", flush=True)
    if not todo:
        return True
    model = LocalModel(args.model_dir, args.threads)
    runtime = {"onnxruntime": installed("onnxruntime"), "tokenizers": installed("tokenizers")}
    deadline = time.monotonic() + 60 * args.max_minutes if args.max_minutes else None
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for n, (case, arm, old, r, options) in enumerate(todo, 1):
            shown = old["shown"]
            tokens = model.tokenize(prompt(case, options, [defs[i] for i in shown], specs))
            letter, scores = model.choose(tokens, options)
            if r == 0:
                drift = max(abs(scores[k] - old["option_logits"][k]) for k in scores)
                if letter != old["selected"] or drift > TOLERANCE or len(tokens) != old["input_tokens"]:
                    sys.exit(f"{case['id']} {arm}: rotation 0 does not reproduce the saved decision "
                             f"(chose {letter}, saved {old['selected']}, largest score change {drift:.2e})")
            answer = options[letter]
            row = {"id": case["id"], "family": case["acronym"], "kind": case["kind"], "arm": arm,
                   "rotation": r, "order": [e["id"] if e else "NONE" for e in options.values()],
                   "shown": shown, "input_tokens": len(tokens), "option_logits": scores,
                   "selected": letter, "chosen": answer["id"] if answer else "NONE",
                   "answer": answer["expansion"] if answer else None,
                   "verdict": score_answer(case["expected"], answer, shown), **runtime}
            if r == 0:
                row["reproduced_saved_decision"] = round(drift, 8)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            if n % 25 == 0:
                print(f"{len(done) + n} runs saved", flush=True)
            if deadline and time.monotonic() > deadline and n < len(todo):
                print(f"stopped at the time limit with {len(todo) - n} runs to go", flush=True)
                return False
    return True


def counts(rows, cases, entries):
    """Totals over all rotations, plus what a chooser that ignores the text would score."""
    options_of = {c["id"]: answer_options(c, entries) for c in cases}
    expected = {c["id"]: c["expected"] for c in cases}
    verdicts = Counter(row["verdict"] for row in rows)
    by_case = defaultdict(list)
    for row in rows:
        by_case[row["id"]].append(row)
    answerable = [cid for cid in by_case if "abstain" not in expected[cid]]
    controls = [cid for cid in by_case if "abstain" in expected[cid]]
    # A chooser that always picks the same letter meets each option once over the rotations.
    letter_only = sum(score_answer(expected[cid], e, by_case[cid][0]["shown"]) == "grounded_answer"
                      for cid in answerable for e in options_of[cid].values())
    stable = [cid for cid in answerable if len({row["chosen"] for row in by_case[cid]}) == 1]
    return {
        "questions": len(by_case),
        "answerable_questions": len(answerable),
        "answerable_runs": sum(len(by_case[cid]) for cid in answerable),
        "grounded_runs": verdicts["grounded_answer"],
        "right_meaning_wrong_row_runs": verdicts["wrong_or_missing_citation"],
        "wrong_meaning_runs": verdicts["wrong_expansion"],
        "declined_answerable_runs": verdicts["missed_answer"],
        "letter_only_grounded_runs": letter_only,
        "same_choice_in_every_rotation": len(stable),
        "grounded_in_every_rotation": sum(all(r["verdict"] == "grounded_answer" for r in by_case[cid])
                                          for cid in answerable),
        "control_questions": len(controls),
        "control_runs": sum(len(by_case[cid]) for cid in controls),
        "correct_decline_runs": verdicts["correct_abstention"],
        "letter_only_decline_runs": len(controls),
        "letters_chosen": dict(sorted(Counter(row["selected"] for row in rows).items())),
    }


def paired(anchor, challenger):
    """Per question change in the grounded share over rotations, against the glossary."""
    def share(rows):
        by_case = defaultdict(list)
        for row in rows:
            if row["verdict"] not in ("correct_abstention", "guessed_on_control"):
                by_case[(row["family"], row["id"])].append(row["verdict"] == "grounded_answer")
        return {key: mean(values) for key, values in by_case.items()}
    base, other = share(anchor), share(challenger)
    deltas = {key: other[key] - base[key] for key in base}
    families = defaultdict(list)
    for (family, _), delta in deltas.items():
        families[family].append(delta)
    scores = [mean(values) for values in families.values()]
    rng = random.Random(905)
    draws = sorted(mean(rng.choices(scores, k=len(scores))) for _ in range(2000))
    return {"questions_better": sum(d > 0 for d in deltas.values()),
            "questions_worse": sum(d < 0 for d in deltas.values()),
            "questions_same": sum(d == 0 for d in deltas.values()),
            "family_mean_delta": round(mean(scores), 4),
            "family_bootstrap_95": [round(draws[50], 4), round(draws[1949], 4)]}


def summarize():
    entries, cases = read_json("definitions.json"), read_json("cases/evaluation.json")
    path = OUT / "per-run.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    # One fixed order, whatever order the runs were made in, so the file hash is stable.
    place = {c["id"]: i for i, c in enumerate(cases)}
    rows.sort(key=lambda r: (place[r["id"]], ARMS.index(r["arm"]), r["rotation"]))
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    expected_runs = len(ARMS) * sum(len(answer_options(c, entries)) for c in cases)
    if len(rows) != expected_runs or len({(r["id"], r["arm"], r["rotation"]) for r in rows}) != expected_runs:
        sys.exit(f"{len(rows)} runs saved, {expected_runs} expected: finish the run first")
    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row["arm"]].append(row)
    report = {
        "what": "Every option shown once at every letter, with the rows each method showed in the published run",
        "dataset_hashes": {p: dataset_hash(ROOT / p) for p in ("cases/evaluation.json", "sources.json", "definitions.json")},
        "saved_decisions_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SAVED},
        "per_run_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "runs": len(rows),
        "published_decisions_reproduced": sum("reproduced_saved_decision" in r for r in rows),
        "largest_score_change_on_reproduction": max(r.get("reproduced_saved_decision", 0) for r in rows),
        "model": {"id": MODEL_REPO, "revision": MODEL_REVISION, "format": "ONNX Q4", "api_cost": 0,
                  "runs_by_onnxruntime": dict(sorted(Counter(r["onnxruntime"] for r in rows).items())),
                  "runs_by_tokenizers": dict(sorted(Counter(r["tokenizers"] for r in rows).items()))},
        "arms": {arm: counts(by_arm[arm], cases, entries) for arm in ARMS},
        "by_case_type": {arm: {kind: counts([r for r in by_arm[arm] if r["kind"] == kind], cases, entries)
                               for kind in sorted({r["kind"] for r in by_arm[arm]})} for arm in ARMS},
        "paired_vs_glossary": {arm: paired(by_arm[BASELINE], by_arm[arm]) for arm in ARMS if arm != BASELINE},
    }
    (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT / 'summary.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-dir", type=Path, default=CACHE / "model")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-minutes", type=float, help="stop cleanly after this long; run again to resume")
    parser.add_argument("--arms", type=lambda v: tuple(v.split(",")), default=ARMS,
                        help="comma separated subset, to split a long run across machines")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    if set(args.arms) - set(ARMS):
        parser.error(f"--arms must be among {', '.join(ARMS)}")
    if args.summary_only or run(args):
        summarize()


if __name__ == "__main__":
    main()
