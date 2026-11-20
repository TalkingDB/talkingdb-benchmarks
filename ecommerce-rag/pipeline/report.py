"""Write the result section for a run, from its own summary.json, per_question.csv and config.json.

The published run (results/openai) goes into README.md, between the result markers, so the
README always shows what the saved run scores. A local run gets results/local/report.md.
Plain Python 3, no installs.

  python3 pipeline/report.py                rewrite the README result section from results/openai
  python3 pipeline/report.py results/local  write results/local/report.md
"""

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PUBLISHED = HERE / "results" / "openai"
START, END = "<!-- result:start -->", "<!-- result:end -->"


def load(folder):
    folder = Path(folder)
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    with open(folder / "per_question.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return summary, config, rows


def section(folder):
    """Markdown for one run: settings, the result table, and where the loss happens."""
    summary, config, rows = load(folder)
    n = summary["questions_scored"]
    v20, v4 = summary["top20_verdicts"], summary["top4_verdicts"]
    no_answer = [r for r in rows if r["top20_verdict"].startswith("N/A")]
    declined = sum(1 for r in no_answer if r["top4_verdict"].startswith("PASS"))
    risk = v4.get("RISK", 0)
    pass4 = v4.get("PASS", 0) - declined
    head = summary["metrics"]["All primary evidence in top 4 (headline)"]
    lost20 = v20.get("PARTIAL", 0) + v20.get("FAIL", 0)
    lost_rerank = v20.get("PASS", 0) - pass4
    varied = sum(1 for r in rows if len(set(r["top4_per_run"].split(" | "))) > 1)
    runs = summary["runs"]

    reranker = config["reranker"] if config["reranker"] != "llm" else f"LLM reranker (`{config['rerank_model'] or config['chat_model']}`)"
    lines = [
        f"Run `{Path(folder).name}`"
        + (f", {config['run_date']}" if config.get("run_date") else "")
        + f": `{config['chat_model']}` ({config['llm_provider']}), `{config['embedding_model']}` embeddings, {reranker}, "
        f"{config['fetch_k']} candidates, top {config['top_k']}, rerank cutoff {config['min_rerank_score']}, "
        f"{runs} run{'s' if runs != 1 else ''} ([config]({rel(folder, 'config.json')})).",
        "",
        "| Stage | Questions | Result |",
        "| :--- | :--- | :--- |",
        f"| Top 20, after vector search | {n} | {v20.get('PASS', 0)} ({v20.get('PASS', 0) / n:.1%}) have all primary evidence: "
        f"PASS {v20.get('PASS', 0)}, PARTIAL {v20.get('PARTIAL', 0)}, FAIL {v20.get('FAIL', 0)} |",
        f"| Top 4, after the reranker (what the bot answers from) | {n} | {head['mean']:.1%} per run "
        f"({round(head['min'] * n)} to {round(head['max'] * n)} of {n}): PASS {pass4}, FAIL {v4.get('FAIL', 0)} by most runs |",
        f"| No answer in the documents | {len(no_answer)} | {declined} declined; {risk} let passages through to the answer step (RISK) |",
        "",
        f"In {lost20} of the {n} questions, search never puts a primary piece of evidence in the top 20, so no reranker "
        f"could keep it. In {lost_rerank} more, every primary piece is in the top 20 but the reranker drops at least one."
        + (f" The top 4 changed between runs for {varied} of the {len(rows)} questions, so a question can pass in one run "
           "and fail in the next." if runs > 1 else ""),
        "",
    ]
    if "answer_metrics" in summary:
        am, va = summary["answer_metrics"], summary["answer_verdicts"]
        pct = lambda name: f"{am[name]['mean']:.1%}"  # noqa: E731
        lines += [
            "",
            "**Answers.** The bot also wrote its answer from the same top 4, and each answer was checked against the "
            "passages its [n] citations name, with no judge:",
            "",
            "| Check | Result |",
            "| :--- | :--- |",
            f"| Answered, of the {n} questions with evidence | {pct('Answered (questions with evidence)')} |",
            f"| Answer cites a passage holding primary evidence | {pct('Answer cites primary evidence')} |",
            f"| Answer cites all primary evidence | {pct('Answer cites all primary evidence')} |",
            f"| Answer with no citation at all | {pct('Answer without any citation')} |",
            f"| Answer citing a passage that does not exist | {pct('Answer cites a passage that does not exist')} |",
            f"| Declined, of the {len(no_answer)} with no answer in the documents | {pct('Declined when the answer is not in the documents')} |",
            "",
            "By most runs: " + ", ".join(f"{k} {v}" for k, v in va.items()) + ". Citing the evidence does not prove the "
            "answer is right, and an answer that misses it can still be reasonable; this checks grounding only.",
        ]
    lines += [
        "",
        f"Per question, with each stage's verdict and the passages returned: [per_question.csv]({rel(folder, 'per_question.csv')}). "
        f"Every metric, mean and range over the runs: [summary.json]({rel(folder, 'summary.json')}).",
    ]
    return "\n".join(lines)


def rel(folder, name):
    """Link target as seen from where the section is written."""
    folder = Path(folder).resolve()
    base = HERE if folder == PUBLISHED.resolve() else folder
    return (folder / name).relative_to(base).as_posix()


def write_report(folder):
    folder = Path(folder).resolve()
    text = section(folder)
    if folder == PUBLISHED.resolve():
        readme = HERE / "README.md"
        doc = readme.read_text(encoding="utf-8")
        if START not in doc or END not in doc:
            sys.exit("README.md has no result markers")
        before, rest = doc.split(START, 1)
        _, after = rest.split(END, 1)
        readme.write_text(f"{before}{START}\n{text}\n{END}{after}", encoding="utf-8")
        print("README.md result section rewritten from results/openai")
    else:
        (folder / "report.md").write_text(f"# Result: {folder.name}\n\n{text}\n", encoding="utf-8")
        print(f"Wrote {folder / 'report.md'}")


if __name__ == "__main__":
    write_report(sys.argv[1] if len(sys.argv) > 1 else PUBLISHED)
