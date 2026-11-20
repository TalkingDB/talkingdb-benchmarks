"""Compare prompt glossaries and evidence retrieval over the same acronym questions."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from string import ascii_uppercase

from sources import (
    CACHE,
    MODEL_REPO,
    MODEL_REVISION,
    ROOT,
    file_hash,
    model_files,
    read_json,
)

TOP_K = 3
TOKEN_BUDGET = 768
BGE_MODEL = "BAAI/bge-small-en-v1.5"
BGE_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
BGE_WEIGHTS = "3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad"
ARMS = ("no_glossary", "glossary_in_system_prompt", "glossary_full", "bm25", "scoped_prototype")
BASELINE = "glossary_in_system_prompt"
SYSTEM = (
    "Choose the option that expands the acronym and cites a matching entry in the supplied "
    "glossary. A citation must refer to the named specification when the question names one. "
    "Choose NONE when the evidence is missing or when multiple meanings fit the context. "
    "Answer with the option letter only."
)


def words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def dataset_hash(path):
    # Text mode normalizes newlines so checkouts on Windows and Linux agree.
    content = path.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize(expansion):
    return " ".join(words(expansion))


def named_specs(text):
    return set(re.findall(r"\bTS\s+(\d{2}\.\d{3}(?:-\d+)?)\b", text, flags=re.IGNORECASE))


def entry_text(entry, specs):
    scope = specs[entry["spec"]]["summary"]
    return f"{entry['acronym']} {entry['expansion']} {scope}"


class BM25:
    def __init__(self, entries, specs):
        self.rows = {row["id"]: Counter(words(entry_text(row, specs))) for row in entries}
        self.lengths = {key: sum(terms.values()) for key, terms in self.rows.items()}
        self.average = mean(self.lengths.values())
        counts = Counter(term for terms in self.rows.values() for term in terms)
        self.idf = {term: math.log1p((len(entries) - count + 0.5) / (count + 0.5))
                    for term, count in counts.items()}

    def rank(self, query, rows):
        terms = set(words(query))

        def score(row):
            key = row["id"]
            length_adjust = 1.2 * (0.25 + 0.75 * self.lengths[key] / self.average)
            return sum(self.idf[term] * 2.2 * count / (count + length_adjust)
                       for term, count in self.rows[key].items() if term in terms)

        return sorted(rows, key=lambda row: (-score(row), row["id"]))


def dense_ranking(entries, specs, cases, directory):
    import torch
    from sentence_transformers import SentenceTransformer

    if file_hash(directory / "model.safetensors") != BGE_WEIGHTS:
        raise ValueError(f"Run requires {BGE_MODEL} at {BGE_REVISION}")
    torch.set_num_threads(4)
    model = SentenceTransformer(str(directory), device="cpu", local_files_only=True)
    vectors = model.encode([entry_text(row, specs) for row in entries], normalize_embeddings=True)
    questions = ["Represent this sentence for searching relevant passages: " + c["question"] for c in cases]
    similarities = model.encode(questions, normalize_embeddings=True) @ vectors.T
    return {case["id"]: {row["id"]: float(sim) for row, sim in zip(entries, scores)}
            for case, scores in zip(cases, similarities)}


def evidence_for(arm, question, acronym, entries, bm25, dense_scores=None):
    scope = named_specs(question)
    scoped = [entry for entry in entries if not scope or entry["spec"] in scope]
    if arm == "no_glossary":
        return []
    if arm == "glossary_full":
        return sorted(scoped, key=lambda row: (row["spec"], row["id"]))
    if arm.startswith("glossary_"):
        # Prefer the queried acronym under a fixed budget, while retaining all competing meanings.
        return sorted(scoped, key=lambda row: (row["acronym"] != acronym, row["id"]))
    if arm == "scoped_prototype":
        scoped = [entry for entry in scoped if entry["acronym"] == acronym]
    if arm == "bge_dense":
        return sorted(scoped, key=lambda row: (-dense_scores[row["id"]], row["id"]))[:TOP_K]
    return bm25.rank(question, scoped)[:TOP_K]


def answer_options(case, entries):
    # All arms get the same plausible choices. Randomize order independently of the answer key.
    choices = [entry for entry in entries if entry["acronym"] == case["acronym"]] + [None]
    seed = int.from_bytes(hashlib.sha256(case["id"].encode()).digest()[:8], "big")
    random.Random(seed).shuffle(choices)
    return dict(zip(ascii_uppercase, choices, strict=False))


def score_answer(expected, answer, visible):
    if answer is None:
        return "correct_abstention" if "abstain" in expected else "missed_answer"
    if "abstain" in expected:
        return "guessed_on_control"
    if normalize(answer["expansion"]) not in {normalize(e) for e in expected["expansions"]}:
        return "wrong_expansion"
    if answer["id"] not in expected["citations"] or answer["id"] not in visible:
        return "wrong_or_missing_citation"
    return "grounded_answer"


def prompt(case, options, evidence, specs):
    groups = defaultdict(list)
    for entry in evidence:
        groups[entry["spec"]].append(f"[{entry['id']}] {entry['acronym']} = {entry['expansion']}")
    lines = [f"TS {spec}, {specs[spec]['summary']}\n" + "\n".join(rows) for spec, rows in groups.items()]
    menu = "\n".join(f"{k}. {e['expansion']} [{e['id']}]" if e else f"{k}. NONE" for k, e in options.items())
    return (
        f"<|im_start|>system\n{SYSTEM}\nGlossary evidence:\n" + ("\n".join(lines) or "None supplied.")
        + f"<|im_end|>\n<|im_start|>user\n{case['question']}\n\n{menu}<|im_end|>\n"
          "<|im_start|>assistant\nOption:"
    )


class LocalModel:
    def __init__(self, directory, threads):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_files(directory)
        self.np = np
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        cpu = ort.SessionOptions()
        cpu.intra_op_num_threads = threads
        cpu.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / "model_q4.onnx"), cpu, providers=["CPUExecutionProvider"])
        self.inputs = self.session.get_inputs()
        self.option_tokens = {}
        for letter in ascii_uppercase:
            tokens = self.tokenize(" " + letter)
            if len(tokens) != 1:
                raise ValueError(f"Option {letter} is not a single token")
            self.option_tokens[letter] = tokens[0]

    def tokenize(self, text):
        return self.tokenizer.encode(text, add_special_tokens=False).ids

    def choose(self, tokens, options):
        np = self.np
        ids = np.array([tokens], dtype=np.int64)
        feed = {}
        for arg in self.inputs:
            if arg.name == "input_ids":
                feed[arg.name] = ids
            elif arg.name == "attention_mask":
                feed[arg.name] = np.ones_like(ids)
            elif arg.name == "position_ids":
                feed[arg.name] = np.array([range(len(tokens))], dtype=np.int64)
            elif arg.name.startswith("past_key_values."):
                _, heads, _, dimension = arg.shape
                dtype = np.float16 if arg.type == "tensor(float16)" else np.float32
                feed[arg.name] = np.zeros((1, heads, 0, dimension), dtype=dtype)
            else:
                raise ValueError(f"Unexpected input for the pinned model: {arg.name}")
        logits = self.session.run(["logits"], feed)[0][0, -1]
        scores = {letter: float(logits[self.option_tokens[letter]]) for letter in options}
        return max(scores, key=scores.get), scores


def run_case(case, arm, entries, specs, bm25, model, dense_scores):
    start = time.perf_counter()
    ranking = evidence_for(arm, case["question"], case["acronym"], entries, bm25, dense_scores)
    gold = set(case["expected"].get("citations", []))
    result = {"id": case["id"], "family": case["acronym"], "kind": case["kind"], "arm": arm,
              "evidence_at_3": [row["id"] for row in ranking[:TOP_K]],
              "recall_at_3": any(row["id"] in gold for row in ranking[:TOP_K]) if gold else None}
    if model is None:
        return result
    options = answer_options(case, entries)
    tokens = model.tokenize(prompt(case, options, ranking, specs))
    while len(tokens) > TOKEN_BUDGET and ranking and arm != "glossary_full":
        ranking = ranking[:-1]
        tokens = model.tokenize(prompt(case, options, ranking, specs))
    if len(tokens) > (8192 if arm == "glossary_full" else TOKEN_BUDGET):
        raise ValueError(f"Prompt exceeds model or comparison budget: {case['id']}, {arm}")
    letter, scores = model.choose(tokens, options)
    answer = options[letter]
    visible = [row["id"] for row in ranking]
    result.update({"shown": visible, "input_tokens": len(tokens), "option_logits": scores,
                   "evidence_at_3": visible[:TOP_K],
                   "recall_at_3": bool(set(visible[:TOP_K]) & gold) if gold else None,
                   "selected": letter, "answer": answer["expansion"] if answer else None,
                   "citation": answer["id"] if answer else None,
                   "verdict": score_answer(case["expected"], answer, visible),
                   "seconds": round(time.perf_counter() - start, 4)})
    return result


def summarize(rows):
    recalled = [row["recall_at_3"] for row in rows if row["recall_at_3"] is not None]
    summary = {"cases": len(rows), "answerable": len(recalled), "evidence_found_at_3": sum(recalled)}
    if "verdict" in rows[0]:
        summary.update({"verdicts": dict(Counter(row["verdict"] for row in rows)),
                        "answers_citing_unseen_evidence": sum(
                            bool(row["citation"] and row["citation"] not in row["shown"]) for row in rows
                        ),
                        "mean_input_tokens": round(mean(row["input_tokens"] for row in rows), 1),
                        "mean_seconds": round(mean(row["seconds"] for row in rows), 4)})
    return summary


def paired(anchor, challenger):
    by_id = {row["id"]: row for row in anchor}
    groups = defaultdict(list)
    for row in challenger:
        if row["recall_at_3"] is not None:
            win = int(row["verdict"] == "grounded_answer") - int(by_id[row["id"]]["verdict"] == "grounded_answer")
            groups[row["family"]].append(win)
    if not groups:
        return None
    scores = [mean(values) for values in groups.values()]
    diffs = [delta for values in groups.values() for delta in values]
    rng = random.Random(905)
    draws = sorted(mean(rng.choices(scores, k=len(scores))) for _ in range(2000))
    return {"wins": diffs.count(1), "losses": diffs.count(-1), "ties": diffs.count(0),
            "family_mean_delta": round(mean(scores), 4), "family_bootstrap_95": [draws[50], draws[1949]]}


def paired_by_case_type(anchor, challenger):
    successful = {"grounded_answer", "correct_abstention"}
    by_id = {row["id"]: row for row in anchor}
    counts = defaultdict(Counter)
    for row in challenger:
        delta = int(row["verdict"] in successful) - int(by_id[row["id"]]["verdict"] in successful)
        counts[row["kind"]][delta] += 1
    return {kind: {"wins": counter[1], "losses": counter[-1], "ties": counter[0]}
            for kind, counter in sorted(counts.items())}


def summarize_run(grouped):
    summary = {"arms": {arm: summarize(rows) for arm, rows in grouped.items()}}
    summary["by_case_type"] = {}
    for arm, rows in grouped.items():
        cases = defaultdict(list)
        for row in rows:
            cases[row["kind"]].append(row)
        summary["by_case_type"][arm] = {kind: summarize(items) for kind, items in sorted(cases.items())}
    if "verdict" in grouped[BASELINE][0]:
        comparisons = {arm: rows for arm, rows in grouped.items() if arm != BASELINE}
        baseline = grouped[BASELINE]
        summary["paired_vs_glossary"] = {arm: paired(baseline, rows) for arm, rows in comparisons.items()}
        summary["paired_by_case_type"] = {arm: paired_by_case_type(baseline, rows) for arm, rows in comparisons.items()}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "evaluation"), default="evaluation")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--model-dir", type=Path, default=CACHE / "model")
    parser.add_argument("--dense-dir", type=Path, help="local checkout of the pinned BGE model")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out must point to a new directory to preserve saved runs")
    args.out.mkdir(parents=True)
    specs, entries = read_json("sources.json"), read_json("definitions.json")
    case_path = f"cases/{args.split}.json"
    cases = read_json(case_path)
    bm25 = BM25(entries, specs)
    dense = dense_ranking(entries, specs, cases, args.dense_dir) if args.dense_dir else {}
    arms = ARMS + (("bge_dense",) if dense else ())
    model = None if args.retrieval_only else LocalModel(args.model_dir, args.threads)
    grouped = defaultdict(list)
    with (args.out / "per-case.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for i, case in enumerate(cases, 1):
            for arm in arms:
                row = run_case(case, arm, entries, specs, bm25, model, dense.get(case["id"]))
                grouped[arm].append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            if i % 5 == 0 or i == len(cases):
                print(f"{args.split}: {i}/{len(cases)} cases checked", flush=True)
    report = {"split": args.split, "dataset_hashes": {path: dataset_hash(ROOT / path) for path in
              (case_path, "sources.json", "definitions.json")}, "k": TOP_K, "budget": TOKEN_BUDGET,
              "python": sys.version.split()[0], "threads": args.threads,
              "model": {"id": MODEL_REPO, "revision": MODEL_REVISION, "format": "ONNX Q4",
                        "onnxruntime": importlib.metadata.version("onnxruntime"),
                        "tokenizers": importlib.metadata.version("tokenizers"), "api_cost": 0} if model else None,
              "dense": {"id": BGE_MODEL, "revision": BGE_REVISION,
                        "sentence_transformers": importlib.metadata.version("sentence-transformers"),
                        "torch": importlib.metadata.version("torch")} if dense else None}
    report.update(summarize_run(grouped))
    (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
