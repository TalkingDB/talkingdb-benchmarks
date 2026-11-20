"""Exact retrieval scoring for the e-commerce RAG benchmark. No language model, no judge.

A passage the pipeline returns counts for an evidence unit only when it:
1. comes from the same document as the unit, and
2. contains one of the unit's quotes, word for word (runs of whitespace are ignored).
A unit with several chunk_ids is one clause split across chunks; finding any part counts.

For each question and run it checks two stages:
  top 20  the candidates vector search returns (after the cosine filter)
  top 4   the passages left after the reranker and its score cutoff
and gives a verdict per stage:
  top 20  PASS all primary units found, PARTIAL some, FAIL none
  top 4   PASS all primary units in the top 4 (majority of runs), FAIL otherwise
Questions whose answer is not in the documents pass the top 4 when nothing gets through
(empty retrieval), and are a RISK when passages still get through.

Usage, plain Python 3, no installs:
  python3 pipeline/score.py                 self check, then re-score the saved OpenAI run
                                            and confirm it matches results/openai/summary.json
  python3 pipeline/score.py results/local   score another run folder and write its summary
  python3 pipeline/score.py --self-check    only the self check
"""

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CASES = HERE / "cases" / "questions.json"
TOP_K = 4


def norm(text):
    return " ".join((text or "").split())


# --- matching -------------------------------------------------------------------------

def unit_found(unit, passages):
    """True when any passage (document, text) holds one of the unit's quotes."""
    for doc, text in passages:
        for ev in unit["evidence"]:
            if ev["document"] == doc and norm(ev["quote"]) in text:
                return True
    return False


def passages_of(ids, index):
    return [(index[i]["document"], index[i]["text"]) for i in ids if i in index]


def score_record(case, rec, index):
    """Score one question in one run."""
    primary, supporting = case["primary"], case["supporting"]
    top20 = passages_of(rec["candidates"], index)
    kept_ids = rec["kept"]
    kept = passages_of(kept_ids, index)
    out = {"kept": kept_ids, "n_kept": len(kept_ids)}

    if not primary:
        out.update(scored=False, top4_ok=not kept_ids)
        return out

    in20 = [unit_found(u, top20) for u in primary]
    in4 = [unit_found(u, kept) for u in primary]
    vec4 = passages_of([c for c, _ in rec["top_vector"]][:TOP_K], index)
    gold = primary + supporting
    first = next(
        (r + 1 for r, p in enumerate(kept) if any(unit_found(u, [p]) for u in primary)),
        None,
    )
    out.update(
        scored=True,
        in20=in20,
        in4=in4,
        primary_recall_20=sum(in20) / len(primary),
        all_primary_20=all(in20),
        primary_hit_4=all(in4),
        primary_recall_4=sum(in4) / len(primary),
        vector_only_hit_4=all(unit_found(u, vec4) for u in primary),
        capped_recall_4=sum(unit_found(u, kept) for u in gold) / min(len(gold), TOP_K),
        precision_4=(sum(any(unit_found(u, [p]) for u in gold) for p in kept) / len(kept)) if kept else 0.0,
        mrr=1 / first if first else 0.0,
        supporting_in20=sum(unit_found(u, top20) for u in supporting),
        supporting_in4=sum(unit_found(u, kept) for u in supporting),
    )
    return out


def score_answer(case, rec, index):
    """Score the bot's answer in one run, from the passages its [n] citations name.
    No judge: an answer is grounded when it cites a passage holding primary evidence."""
    refused = rec["refused"]
    if not case["primary"]:
        return {"scored": False, "declined": refused}
    cited = passages_of(rec["cited"], index)
    return {
        "scored": True,
        "answered": not refused,
        "grounded": not refused and any(unit_found(u, cited) for u in case["primary"]),
        "all_cited": not refused and all(unit_found(u, cited) for u in case["primary"]),
        "uncited": not refused and not rec["cited"],
        "invalid": bool(rec["invalid_citations"]),
    }


def answer_verdict(case, scored_runs):
    runs = len(scored_runs)
    if not case["primary"]:
        declined = sum(s["declined"] for s in scored_runs)
        if declined * 2 > runs:
            return f"DECLINED, correctly ({declined}/{runs} runs)"
        return f"ANSWERED although the answer is not in the documents ({runs - declined}/{runs} runs)"
    grounded = sum(s["grounded"] for s in scored_runs)
    refused = sum(not s["answered"] for s in scored_runs)
    if grounded * 2 > runs:
        return f"GROUNDED ({grounded}/{runs} runs cite primary evidence)"
    if refused * 2 > runs:
        return f"REFUSED although the documents hold the answer ({refused}/{runs} runs)"
    return f"UNGROUNDED ({runs - refused - grounded}/{runs} runs answer without citing primary evidence)"


ANSWER_METRICS = [
    ("answered", "Answered (questions with evidence)"),
    ("grounded", "Answer cites primary evidence"),
    ("all_cited", "Answer cites all primary evidence"),
    ("uncited", "Answer without any citation"),
    ("invalid", "Answer cites a passage that does not exist"),
]


def label(unit):
    """#22/#23 when the unit has reference chunk ids, else its first quote and page."""
    if unit.get("chunk_ids"):
        return "/".join(f"#{c}" for c in unit["chunk_ids"])
    e = unit["evidence"][0]
    quote = e["quote"] if len(e["quote"]) <= 40 else e["quote"][:40] + "..."
    return f'"{quote}" ({e["document"]} p{e["page"]})'


def verdicts(case, scored_runs, rec0, index):
    """Top-20 and top-4 verdict lines for one question across its runs."""
    if case.get("not_scored"):
        return "Not scored: " + case["not_scored"], "Not scored"
    runs = len(scored_runs)
    if not case["primary"]:
        declined = sum(s["top4_ok"] for s in scored_runs)
        top20 = "N/A: answer not in documents"
        if declined * 2 > runs:
            top4 = "PASS: nothing passes the reranker" + (f" ({declined}/{runs} runs)" if declined < runs else "")
        else:
            top4 = f"RISK: answer not in documents, but passages pass the reranker in {runs - declined}/{runs} runs"
        return top20, top4

    order = [c for c, _ in rec0["top_vector"]]
    parts, found = [], 0
    for u, hit in zip(case["primary"], scored_runs[0]["in20"]):
        if hit:
            found += 1
            rank = min(
                r + 1 for r, cid in enumerate(order)
                if cid in index and unit_found(u, [(index[cid]["document"], index[cid]["text"])])
            )
            parts.append(f"{label(u)} at rank {rank}")
        else:
            parts.append(f"{label(u)} not in top 20")
    n = len(case["primary"])
    status = "PASS" if found == n else "FAIL" if found == 0 else "PARTIAL"
    top20 = f"{status} ({found}/{n} primary in top 20): " + "; ".join(parts) + "."

    passed = sum(s["primary_hit_4"] for s in scored_runs)
    det = []
    for k, u in enumerate(case["primary"]):
        kept_runs = sum(s["in4"][k] for s in scored_runs)
        if kept_runs == runs:
            det.append(f"{label(u)} kept")
        elif not scored_runs[0]["in20"][k]:
            det.append(f"{label(u)} never reached top 20")
        else:
            det.append(f"{label(u)} dropped by reranker" + (f" ({runs - kept_runs}/{runs} runs)" if kept_runs else ""))
    status = "PASS" if passed * 2 > runs else "FAIL"
    top4 = f"{status} ({passed}/{runs} runs had all primary in top 4): " + "; ".join(det) + "."
    return top20, top4


METRICS = [
    ("all_primary_20", "All primary evidence in top 20"),
    ("primary_recall_20", "Primary recall in top 20"),
    ("primary_hit_4", "All primary evidence in top 4 (headline)"),
    ("primary_recall_4", "Primary recall in top 4"),
    ("vector_only_hit_4", "All primary in top 4 by vector order alone"),
    ("capped_recall_4", "Evidence recall in top 4, capped at 4"),
    ("precision_4", "Top 4 passages that are evidence"),
    ("mrr", "Mean reciprocal rank of first primary passage"),
]


def score_folder(folder):
    folder = Path(folder)
    cases = {c["id"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["questions"]}
    index = {
        c["chunk_id"]: {"document": c["document"], "text": norm(c["text"])}
        for c in json.loads((folder / "index.json").read_text(encoding="utf-8"))
    }
    records = [json.loads(line) for line in (folder / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    by_q = {}
    for rec in records:
        by_q.setdefault(rec["id"], []).append(rec)
    runs = max(r["run"] for r in records)

    has_answers = all("answer" in r for r in records)
    rows, per_run = [], {k: [[] for _ in range(runs)] for k, _ in METRICS}
    ans_run = {k: [[] for _ in range(runs)] for k, _ in ANSWER_METRICS + [("declined", "")]}
    counts20, counts4, counts_ans = Counter(), Counter(), Counter()
    for qid, case in cases.items():
        if case.get("not_scored") or qid not in by_q:
            continue
        recs = sorted(by_q[qid], key=lambda r: r["run"])
        scored = [score_record(case, r, index) for r in recs]
        for s, r in zip(scored, recs):
            if s["scored"]:
                for k, _ in METRICS:
                    per_run[k][r["run"] - 1].append(float(s[k]))
        v20, v4 = verdicts(case, scored, recs[0], index)
        counts20[v20.split(" ")[0].rstrip(":")] += 1
        counts4[v4.split(" ")[0].rstrip(":")] += 1
        extra = {}
        if has_answers:
            ans = [score_answer(case, r, index) for r in recs]
            for s, r in zip(ans, recs):
                for k in ans_run:
                    if k in s:
                        ans_run[k][r["run"] - 1].append(float(s[k]))
            va = answer_verdict(case, ans)
            counts_ans[va.split(" ")[0].rstrip(",")] += 1
            extra = {
                "answer_verdict": va,
                "answer_cites_run1": " ".join(f"#{c}" for c in recs[0]["cited"]) or "(none)",
                "answer_run1": recs[0]["answer"],
            }
        rows.append({
            "id": qid,
            "category": case["category"],
            "question": case["question"],
            "top20_verdict": v20,
            "top4_verdict": v4,
            "top20_run1": " ".join(f"#{c}" for c in recs[0]["candidates"]),
            "top4_run1": " ".join(f"#{c}" for c in recs[0]["kept"]) or "(none)",
            "top4_per_run": " | ".join(" ".join(f"#{c}" for c in r["kept"]) or "(none)" for r in recs),
            "query_used": recs[0]["query"],
            **extra,
        })

    ran = [cases[q] for q in by_q if q in cases and not cases[q].get("not_scored")]
    summary = {
        "runs": runs,
        "questions_scored": sum(1 for c in ran if c["primary"]),
        "questions_answer_not_in_documents": sum(1 for c in ran if not c["primary"]),
        "metrics": {},
        "top20_verdicts": dict(sorted(counts20.items())),
        "top4_verdicts": dict(sorted(counts4.items())),
    }
    for k, name in METRICS:
        vals = [statistics.mean(v) if v else 0.0 for v in per_run[k]]
        summary["metrics"][name] = {"mean": round(statistics.mean(vals), 3), "min": round(min(vals), 3), "max": round(max(vals), 3)}
    if has_answers:
        named = ANSWER_METRICS + [("declined", "Declined when the answer is not in the documents")]
        summary["answer_metrics"] = {}
        for k, name in named:
            vals = [statistics.mean(v) if v else 0.0 for v in ans_run[k]]
            summary["answer_metrics"][name] = {"mean": round(statistics.mean(vals), 3),
                                               "min": round(min(vals), 3), "max": round(max(vals), 3)}
        summary["answer_verdicts"] = dict(sorted(counts_ans.items()))
    return summary, rows


def write(folder, summary, rows):
    folder = Path(folder)
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with open(folder / "per_question.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def fmt(name, m):
    """Mean and range as percentages; mean reciprocal rank stays a plain number."""
    if name.startswith("Mean reciprocal rank"):
        return f"{m['mean']:.3f}  (min {m['min']:.3f}, max {m['max']:.3f})"
    return f"{m['mean']:6.1%}  (min {m['min']:.1%}, max {m['max']:.1%})"


def show(summary):
    print(f"{summary['questions_scored']} questions with evidence, "
          f"{summary['questions_answer_not_in_documents']} with no answer in the documents, {summary['runs']} runs")
    for name, m in summary["metrics"].items():
        print(f"  {name:<50} {fmt(name, m)}")
    print("  Top 20 verdicts:", summary["top20_verdicts"])
    print("  Top 4 verdicts: ", summary["top4_verdicts"])
    if "answer_metrics" in summary:
        print("Answers, checked against the passages they cite:")
        for name, m in summary["answer_metrics"].items():
            print(f"  {name:<50} {fmt(name, m)}")
        print("  Answer verdicts:", summary["answer_verdicts"])


# --- self check -----------------------------------------------------------------------

def self_check():
    unit = {"chunk_ids": [1, 2], "evidence": [
        {"document": "a.pdf", "page": 1, "quote": "within  seven days"},
        {"document": "a.pdf", "page": 2, "quote": "of delivery"},
    ]}
    assert unit_found(unit, [("a.pdf", "returns within seven days only")]), "whitespace is ignored"
    assert unit_found(unit, [("a.pdf", "7 days of delivery")]), "either part of a split clause counts"
    assert not unit_found(unit, [("b.pdf", "returns within seven days")]), "other documents never count"
    assert not unit_found(unit, [("a.pdf", "returns within seven")]), "partial quotes never count"

    index = {
        1: {"document": "a.pdf", "text": "returns within seven days"},
        9: {"document": "a.pdf", "text": "unrelated"},
    }
    case = {"primary": [unit], "supporting": []}
    rec = {"candidates": [9, 1], "kept": [1], "top_vector": [[9, 0.5], [1, 0.4]]}
    s = score_record(case, rec, index)
    assert s["all_primary_20"] and s["primary_hit_4"] and s["mrr"] == 1.0 and s["vector_only_hit_4"]
    rec_miss = {"candidates": [9], "kept": [9], "top_vector": [[9, 0.5]]}
    s = score_record(case, rec_miss, index)
    assert not s["all_primary_20"] and not s["primary_hit_4"] and s["precision_4"] == 0.0

    none_case = {"primary": [], "supporting": []}
    assert score_record(none_case, {"candidates": [9], "kept": [], "top_vector": []}, index)["top4_ok"]
    assert not score_record(none_case, {"candidates": [9], "kept": [9], "top_vector": []}, index)["top4_ok"]

    cites = lambda cited, refused=False, bad=(): {"cited": cited, "refused": refused, "invalid_citations": list(bad)}  # noqa: E731
    a = score_answer(case, cites([1]), index)
    assert a["answered"] and a["grounded"] and a["all_cited"], "citing the evidence passage is grounded"
    a = score_answer(case, cites([9]), index)
    assert a["answered"] and not a["grounded"], "citing only other passages is not grounded"
    a = score_answer(case, cites([], refused=True), index)
    assert not a["answered"] and not a["grounded"], "a refusal is not an answer"
    assert score_answer(case, cites([], bad=[5]), index)["invalid"] and score_answer(case, cites([]), index)["uncited"]
    assert score_answer(none_case, cites([], refused=True), index)["declined"], "declining is right when there is no answer"
    assert not score_answer(none_case, cites([9]), index)["declined"]
    print("score.py self check: passed")


def main():
    self_check()
    if sys.argv[1:] == ["--self-check"]:
        return
    if len(sys.argv) > 1:
        summary, rows = score_folder(sys.argv[1])
        write(sys.argv[1], summary, rows)
        show(summary)
        return
    saved = HERE / "results" / "openai"
    summary, _ = score_folder(saved)
    committed = json.loads((saved / "summary.json").read_text(encoding="utf-8"))
    show(summary)
    if summary != committed:
        sys.exit("Re-scored result differs from results/openai/summary.json. If you changed the questions "
                 "(cases/questions.json), that is expected: bash run.sh scores the new set.")
    print("Matches the saved results/openai/summary.json")


if __name__ == "__main__":
    main()
