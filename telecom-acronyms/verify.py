"""Check every published number against the raw decisions. No model, no network.

Usage:
    python verify.py                 check the data files, every saved decision and every summary
    python verify.py --case AMF-04   print the full trail for one question
    python verify.py --csv           also write outcomes.csv, one row per question and method

Run python fetch_data.py first. What it checks:
1. Every file in DATA.txt matches its SHA-256, and the summaries name the same
   questions, rows and sources that are in this folder.
2. Every one of the 371 published decisions: the option order is rebuilt from the
   question id, the chosen letter is the highest scoring option, the recorded answer
   is the option at that letter, and the verdict follows from the expected answer and
   the rows that were shown.
3. Every count in results/evaluation, results/ttt/scored and results/balanced is
   recomputed from those decisions and must match exactly.
4. In the position balanced rerun, every option sits at every letter exactly once,
   and rotation 0 is the published order with the published choice.
5. outcomes.csv, the table in the dataset viewer, is rebuilt from the raw decisions
   and must match byte for byte.
6. Every number quoted in README.md is recomputed here and must appear there as written.
"""

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from string import ascii_uppercase

from balanced_rerun import ARMS, counts, paired as balanced_paired, rotations
from benchmark import BASELINE, answer_options, dataset_hash, paired, paired_by_case_type, score_answer, summarize
from fetch_data import manifest, sha256
from sources import ROOT, read_json

NAMES = {
    "no_glossary": "No evidence",
    "glossary_in_system_prompt": "Glossary in the prompt",
    "glossary_full": "Full glossary",
    "talkingdb_ttt": "TalkingDB Text-to-Tree",
    "bm25": "Keyword search",
    "bge_dense": "Dense search",
    "scoped_prototype": "Scoped prototype",
}
PUBLISHED = ("results/evaluation/per-case.jsonl", "results/ttt/scored/per-case.jsonl")
BALANCED = "results/balanced/per-run.jsonl"
INPUTS = ("cases/evaluation.json", "sources.json", "definitions.json")
failures = []


def check(ok, message):
    if not ok:
        failures.append(message)
    return ok


def jsonl(path):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]


def load():
    entries = read_json("definitions.json")
    cases = read_json("cases/evaluation.json")
    published = [row for path in PUBLISHED for row in jsonl(path)]
    balanced = jsonl(BALANCED) if (ROOT / BALANCED).exists() else []
    return entries, cases, published, balanced


def check_files():
    for digest, rel in manifest():
        path = ROOT / rel
        check(path.exists() and sha256(path) == digest, f"{rel} is missing or differs from DATA.txt; run fetch_data.py")
    hashes = {p: dataset_hash(ROOT / p) for p in INPUTS}
    for path in ("results/evaluation/summary.json", "results/ttt/scored/summary.json", "results/balanced/summary.json"):
        if (ROOT / path).exists():
            check(read_json(path)["dataset_hashes"] == hashes, f"{path} was made from other questions or rows")


def check_decision(row, case, entries):
    options = answer_options(case, entries)
    letter = max(row["option_logits"], key=row["option_logits"].get)
    option = options[row["selected"]]
    gold = set(case["expected"].get("citations", []))
    where = f"{row['id']} {row['arm']}"
    check(set(row["option_logits"]) == set(options), f"{where}: options differ from the rebuilt order")
    check(letter == row["selected"], f"{where}: chosen letter is not the highest scoring option")
    check((option["id"] if option else None) == row["citation"], f"{where}: cited row is not the option at that letter")
    check((option["expansion"] if option else None) == row["answer"], f"{where}: answer is not the option at that letter")
    check(score_answer(case["expected"], option, row["shown"]) == row["verdict"], f"{where}: verdict does not follow")
    if gold:
        check(row["recall_at_3"] == bool(gold & set(row["shown"][:3])), f"{where}: evidence recall does not follow")


def check_published(entries, cases, published):
    by_id = {c["id"]: c for c in cases}
    for row in published:
        check_decision(row, by_id[row["id"]], entries)
    grouped = defaultdict(list)
    for row in published:
        grouped[row["arm"]].append(row)
    check(len(published) == 7 * len(cases) and all(len(v) == len(cases) for v in grouped.values()),
          "published runs do not cover every question for every method")
    evaluation = read_json("results/evaluation/summary.json")
    ttt = read_json("results/ttt/scored/summary.json")
    for arm, rows in grouped.items():
        saved = ttt["arms"][arm] if arm == "talkingdb_ttt" else evaluation["arms"][arm]
        check(summarize(rows) == saved, f"summary for {arm} does not recompute")
        if arm != BASELINE:
            saved_pair = (ttt if arm == "talkingdb_ttt" else evaluation)["paired_vs_glossary"][arm]
            check(paired(grouped[BASELINE], rows) == saved_pair, f"paired result for {arm} does not recompute")
            saved_type = (ttt if arm == "talkingdb_ttt" else evaluation)["paired_by_case_type"][arm]
            check(paired_by_case_type(grouped[BASELINE], rows) == saved_type, f"paired by type for {arm} does not recompute")
    return grouped


def position_facts(entries, cases, published):
    """What the shuffle put at C, and how often the model chose C."""
    at_c = Counter()
    for case in cases:
        option = answer_options(case, entries)["C"]
        expected = case["expected"]
        if "abstain" in expected:
            at_c["control, a meaning at C" if option else "control, NONE at C"] += 1
        elif option is None:
            at_c["answerable, NONE at C"] += 1
        elif option["id"] in expected["citations"]:
            at_c["answerable, right row at C"] += 1
        elif option["expansion"].casefold() in {e.casefold() for e in expected["expansions"]}:
            at_c["answerable, right meaning but another row at C"] += 1
        else:
            at_c["answerable, wrong meaning at C"] += 1
    letters = Counter(row["selected"] for row in published)
    agree = sum(len({r["selected"] for r in published if r["id"] == c["id"]}) == 1 for c in cases)
    return {"decisions": len(published), "chose_C": letters["C"], "letters": dict(sorted(letters.items())),
            "questions_all_methods_same_letter": agree, "at_C": dict(at_c)}


def check_balanced(entries, cases, published, balanced):
    by_id = {c["id"]: c for c in cases}
    saved = {(r["id"], r["arm"]): r for r in published}
    runs = defaultdict(list)
    for row in balanced:
        runs[(row["id"], row["arm"])].append(row)
    check(set(runs) == set(saved), "balanced rerun does not cover every question for every method")
    for (cid, arm), rows in runs.items():
        case, old = by_id[cid], saved[(cid, arm)]
        expected_orders = {r: [e["id"] if e else "NONE" for e in o.values()] for r, o in rotations(answer_options(case, entries))}
        where = f"{cid} {arm}"
        check(sorted(r["rotation"] for r in rows) == sorted(expected_orders), f"{where}: rotations missing or repeated")
        for row in rows:
            order = expected_orders[row["rotation"]]
            check(row["order"] == order, f"{where} rotation {row['rotation']}: option order is wrong")
            check(row["shown"] == old["shown"], f"{where}: rows shown differ from the published run")
            letter = max(row["option_logits"], key=row["option_logits"].get)
            check(letter == row["selected"], f"{where}: chosen letter is not the highest scoring option")
            chosen = order[ascii_uppercase.index(row["selected"])]
            check(chosen == row["chosen"], f"{where}: chosen row is not the option at that letter")
            option = None if chosen == "NONE" else next(e for e in entries if e["id"] == chosen)
            check(score_answer(case["expected"], option, row["shown"]) == row["verdict"], f"{where}: verdict does not follow")
            if row["rotation"] == 0:
                check(row["selected"] == old["selected"], f"{where}: rotation 0 does not repeat the published choice")
        # every option meets every letter exactly once
        seen = Counter((r["order"][i], letter) for r in rows for i, letter in enumerate(ascii_uppercase[:len(r["order"])]))
        check(set(seen.values()) == {1} and len(seen) == len(rows) ** 2, f"{where}: options do not meet every letter once")
    if not (ROOT / "results/balanced/summary.json").exists():
        check(False, "results/balanced/summary.json is missing")
        return {}
    summary = read_json("results/balanced/summary.json")
    by_arm = defaultdict(list)
    for row in balanced:
        by_arm[row["arm"]].append(row)
    for arm in ARMS:
        check(counts(by_arm[arm], cases, entries) == summary["arms"][arm], f"balanced counts for {arm} do not recompute")
        for kind, saved_kind in summary["by_case_type"][arm].items():
            rows = [r for r in by_arm[arm] if r["kind"] == kind]
            check(counts(rows, cases, entries) == saved_kind, f"balanced counts for {arm}, {kind} do not recompute")
        if arm != BASELINE:
            check(balanced_paired(by_arm[BASELINE], by_arm[arm]) == summary["paired_vs_glossary"][arm],
                  f"balanced paired result for {arm} does not recompute")
    check(summary["per_run_sha256"] == hashlib.sha256((ROOT / BALANCED).read_bytes()).hexdigest(),
          "results/balanced/summary.json names a different per-run file")
    check(summary["published_decisions_reproduced"] == len(published), "not every published decision was reproduced")
    return summary


def pct(part, whole):
    return f"{100 * part / whole:.1f}%"


def claims(entries, cases, published, grouped, facts, balanced_summary):
    """Every figure the README quotes, recomputed. Each string must appear in README.md as written."""
    ttt_pub = summarize(grouped["talkingdb_ttt"])
    glo_pub = summarize(grouped[BASELINE])
    saving = 1 - ttt_pub["mean_input_tokens"] / glo_pub["mean_input_tokens"]
    answerable = [c for c in cases if "citations" in c["expected"]]
    shown = {arm: sum(bool(set(c["expected"]["citations"]) & set(next(r for r in rows if r["id"] == c["id"])["shown"]))
                      for c in answerable) for arm, rows in grouped.items()}
    out = [
        f"{facts['chose_C']} of {facts['decisions']}",
        f"{facts['questions_all_methods_same_letter']} of {len(cases)} questions",
        f"right row at C for {facts['at_C']['answerable, right row at C']} of {len(answerable)}",
        f"**{shown['talkingdb_ttt']} of {len(answerable)}**",
        f"**{ttt_pub['mean_input_tokens']}**",
        f"**{glo_pub['mean_input_tokens']}**",
        f"{round(saving * 100)}% fewer input tokens",
        f"{ttt_pub['verdicts']['grounded_answer']} of {ttt_pub['answerable']} grounded answers",
        f"{glo_pub['verdicts']['grounded_answer']} for the glossary in the prompt",
    ]
    if balanced_summary:
        every = balanced_summary["runs"]
        chose_c = sum(a["letters_chosen"].get("C", 0) for a in balanced_summary["arms"].values())
        out += [f"{chose_c:,} of {every:,}", f"{balanced_summary['published_decisions_reproduced']} published decisions"]
        for arm in ARMS:
            a = balanced_summary["arms"][arm]
            tokens = summarize(grouped[arm])["mean_input_tokens"]
            out.append(f"| {NAMES[arm]} | {shown[arm]} of {len(answerable)} | {tokens} | "
                       f"{a['grounded_runs']} of {a['answerable_runs']} | {a['letter_only_grounded_runs']} | "
                       f"{a['correct_decline_runs']} of {a['control_runs']} |")
        gap = max(abs(a["grounded_runs"] - a["letter_only_grounded_runs"]) for a in balanced_summary["arms"].values())
        out.append(f"within {gap} runs of what always picking the same letter would score")
        most = max(a["same_choice_in_every_rotation"] for a in balanced_summary["arms"].values())
        out.append(f"the same option in every rotation for {most} of {len(answerable)} questions")
        t = balanced_summary["arms"]["talkingdb_ttt"]
        g = balanced_summary["arms"][BASELINE]
        out += [f"**{t['grounded_runs']} of {t['answerable_runs']}**", f"{t['letter_only_grounded_runs']} by letter alone",
                f"{g['grounded_runs']} of {g['answerable_runs']}", f"{g['letter_only_grounded_runs']} by letter alone"]
    return out


def check_readme(strings):
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for s in strings:
        check(s in text, f"README.md does not say {s!r}")


def outcomes(entries, cases, published, balanced):
    defs = {e["id"]: e for e in entries}
    specs = read_json("sources.json")
    runs = defaultdict(list)
    for row in balanced:
        runs[(row["id"], row["arm"])].append(row)
    saved = {(r["id"], r["arm"]): r for r in published}

    def link(eid):
        d = defs[eid]
        return f"{eid} TS {d['spec']} p.{d['printed_page']} {specs[d['spec']]['url']}#page={d['pdf_page']}"

    for case in cases:
        exp = case["expected"]
        for arm in ARMS:
            old, rows = saved[(case["id"], arm)], runs.get((case["id"], arm), [])
            gold = set(exp.get("citations", []))
            chosen = Counter(r["chosen"] for r in rows)
            options = answer_options(case, entries).values()
            yield {
                "question_id": case["id"], "kind": case["kind"], "acronym": case["acronym"],
                "question": case["question"],
                "expected": " | ".join(exp.get("expansions", [])) or f"NONE ({exp.get('abstain')})",
                "expected_rows": "; ".join(link(e) for e in exp.get("citations", [])),
                "method": NAMES[arm], "rows_shown": " ".join(old["shown"]),
                "right_row_shown": bool(gold & set(old["shown"])) if gold else "",
                "input_tokens": old["input_tokens"],
                "published_letter": old["selected"], "published_choice": old["citation"] or "NONE",
                "published_verdict": old["verdict"],
                "balanced_runs": len(rows),
                "balanced_grounded_runs": sum(r["verdict"] == "grounded_answer" for r in rows),
                "balanced_correct_declines": sum(r["verdict"] == "correct_abstention" for r in rows),
                "balanced_choices": "; ".join(f"{k} x{v}" for k, v in sorted(chosen.items())),
                "letter_only_grounded_runs": sum(score_answer(exp, e, old["shown"]) == "grounded_answer" for e in options),
            }


def show_case(cid, entries, cases, published, balanced):
    defs = {e["id"]: e for e in entries}
    specs = read_json("sources.json")
    case = next(c for c in cases if c["id"] == cid)
    print(f"{cid} ({case['kind']}): {case['question']}")
    print(f"Expected: {json.dumps(case['expected'])}")
    for letter, option in answer_options(case, entries).items():
        print(f"  {letter}. " + (f"{option['expansion']} [{option['id']}, TS {option['spec']}]" if option else "NONE"))
    for arm in ARMS:
        old = next(r for r in published if r["id"] == cid and r["arm"] == arm)
        rows = [r for r in balanced if r["id"] == cid and r["arm"] == arm]
        print(f"\n{NAMES[arm]}: showed {', '.join(old['shown']) or 'no rows'}")
        for eid in old["shown"][:6]:
            d = defs[eid]
            print(f"    {eid} {d['acronym']} = {d['expansion']}, TS {d['spec']} clause {d['clause']} page "
                  f"{d['printed_page']}  {specs[d['spec']]['url']}#page={d['pdf_page']}")
        print(f"  published: chose {old['selected']} -> {old['citation'] or 'NONE'}, {old['verdict']}")
        for r in rows:
            print(f"  rotation {r['rotation']}: order {' '.join(r['order'])}, chose {r['selected']} -> {r['chosen']}, {r['verdict']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case")
    parser.add_argument("--csv", action="store_true")
    args = parser.parse_args()
    entries, cases, published, balanced = load()
    if args.case:
        show_case(args.case, entries, cases, published, balanced)
        return
    check_files()
    grouped = check_published(entries, cases, published)
    facts = position_facts(entries, cases, published)
    summary = check_balanced(entries, cases, published, balanced) if balanced else {}
    if balanced:
        rows = list(outcomes(entries, cases, published, balanced))
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        table = buffer.getvalue().encode("utf-8")
        if args.csv:
            (ROOT / "outcomes.csv").write_bytes(table)
            print(f"wrote outcomes.csv ({len(rows)} rows)")
        elif (ROOT / "outcomes.csv").exists():
            check((ROOT / "outcomes.csv").read_bytes() == table, "outcomes.csv differs from the raw decisions it summarises")
    check_readme(claims(entries, cases, published, grouped, facts, summary))
    print(f"published decisions checked: {len(published)}; balanced runs checked: {len(balanced)}")
    print(f"the model chose C in {facts['chose_C']} of {facts['decisions']}; letters {facts['letters']}")
    print(f"what the shuffle put at C: {facts['at_C']}")
    if failures:
        print(f"\n{len(failures)} problem(s):")
        for message in failures[:40]:
            print("  " + message)
        sys.exit(1)
    print("every check passed")


if __name__ == "__main__":
    main()
