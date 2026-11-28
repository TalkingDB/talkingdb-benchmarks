"""Draw images/where-questions-end-up.png from the published run, with no passage text.

Usage: python pipeline/make_images.py   (needs matplotlib: pip install -r requirements-images.txt)

Every number is counted from results/openai/per_question.csv and runs.jsonl and checked
against summary.json. The script stops if a count disagrees or a label leaves the image.
"""

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.family"] = "DejaVu Sans"  # ships with matplotlib, so the image is the same on every machine

HERE = Path(__file__).resolve().parent.parent
RUN = HERE / "results" / "openai"
OUT = HERE / "images"
INK, MUTED = "#191919", "#5f6368"
GOOD, WARN, BAD, GREY = "#0aac23", "#fbb315", "#dc3c3d", "#b9bcc1"


def counts():
    rows = list(csv.DictReader((RUN / "per_question.csv").open(encoding="utf-8")))
    summary = json.loads((RUN / "summary.json").read_text(encoding="utf-8"))
    runs = [json.loads(line) for line in (RUN / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    verdict = {r["id"]: (r["top20_verdict"].split()[0].rstrip(":"), r["top4_verdict"].split()[0].rstrip(":")) for r in rows}
    scored = [i for i, (t20, _) in verdict.items() if t20 != "N/A"]
    no_answer = [i for i, (t20, _) in verdict.items() if t20 == "N/A"]
    reached = sum(verdict[i] == ("PASS", "PASS") for i in scored)
    dropped = sum(verdict[i] == ("PASS", "FAIL") for i in scored)
    missed = sum(verdict[i][0] in ("PARTIAL", "FAIL") for i in scored)
    t20 = Counter(verdict[i][0] for i in scored)
    assert len(scored) == summary["questions_scored"] and len(no_answer) == summary["questions_answer_not_in_documents"]
    assert {k: v for k, v in summary["top20_verdicts"].items() if k != "N/A"} == dict(t20)
    assert reached + dropped + missed == len(scored) and reached + dropped == t20["PASS"]
    leaked = [r for r in runs if r["id"] in no_answer]
    got_through = sum(bool(r["kept"]) for r in leaked)
    assert len(leaked) == len(no_answer) * summary["runs"]
    return {"scored": len(scored), "reached": reached, "dropped": dropped, "missed": missed,
            "no_answer": len(no_answer), "no_answer_runs": len(leaked), "got_through": got_through,
            "headline": summary["metrics"]["All primary evidence in top 4 (headline)"]["mean"]}


def bar(ax, parts, total, title):
    """One stacked bar, the count inside each part and its name under it."""
    left, labels = 0, []
    for n, label, colour in parts:
        ax.barh(0, n, left=left, color=colour, height=0.6, edgecolor="white", linewidth=2)
        ax.text(left + n / 2, 0, str(n), ha="center", va="center", fontsize=14, fontweight="bold",
                color=INK if colour == WARN else "white")
        labels.append(ax.text(left + n / 2, -0.42, label, ha="center", va="top", fontsize=9.5, color=INK))
        left += n
    ax.set_xlim(0, total)
    ax.set_ylim(-1.0, 0.45)
    ax.axis("off")
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    return labels


def draw(c):
    fig = plt.figure(figsize=(12.6, 4.0))
    fig.text(0.03, 0.9, "Where the support bot's questions end up", fontsize=16, fontweight="bold", color=INK)
    fig.text(0.03, 0.82, f"{c['scored']} questions have evidence in the documents; {c['no_answer']} have none. "
             f"Top 4 is what the bot answers from, judged over {c['no_answer_runs'] // c['no_answer']} runs.",
             fontsize=11, color=MUTED)
    labels = bar(fig.add_axes([0.03, 0.17, 0.62, 0.52]),
                 [(c["reached"], "All primary evidence reaches\nthe top 4 in most runs", GOOD),
                  (c["dropped"], "In the top 20,\ndropped by the reranker", WARN),
                  (c["missed"], "Never all in the top 20", BAD)],
                 c["scored"], f"{c['scored']} questions with evidence")
    empty = c["no_answer_runs"] - c["got_through"]
    labels += bar(fig.add_axes([0.71, 0.17, 0.26, 0.52]),
                  [(c["got_through"], "Passages\ngot through", BAD), (empty, "Nothing\ngot through", GOOD)],
                  c["no_answer_runs"], f"{c['no_answer']} questions with no answer, {c['no_answer_runs']} runs")
    fig.text(0.03, 0.04, f"Headline: all primary evidence in the top 4 for {100 * c['headline']:.1f}% of questions per run. "
             "Counted from per_question.csv and runs.jsonl; no passage text is shown.", fontsize=9, color=MUTED)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tight = fig.get_tightbbox(renderer)
    w, h = fig.get_size_inches()
    assert tight.x0 >= -0.01 and tight.y0 >= -0.01 and tight.x1 <= w + 0.01 and tight.y1 <= h + 0.01, "a label leaves the image"
    boxes = [t.get_window_extent(renderer) for t in labels]
    assert not any(a.overlaps(b) for i, a in enumerate(boxes) for b in boxes[i + 1:]), "two labels overlap"
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / "where-questions-end-up.png", dpi=150, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    c = counts()
    draw(c)
    print("Wrote images/where-questions-end-up.png", c)
