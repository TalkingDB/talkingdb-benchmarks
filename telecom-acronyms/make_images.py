"""Draw the annotated images in images/ from the pinned ETSI PDFs and the saved results.

Usage: python make_images.py   (needs PyMuPDF; run python sources.py --fetch and
python fetch_data.py first so the PDFs and the per case results are present)

Every number and every answer drawn here is read from definitions.json, cases/,
results/evaluation/ and results/ttt/scored/. The script stops if any text does
not fit its box, so an image can never silently drop a label.
"""

import io
import json
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
PDFS = ROOT / ".cache/pdfs"
OUT = ROOT / "images"
GREEN, RED, AMBER, GREY = (
    (0.05, 0.55, 0.3),
    (0.82, 0.1, 0.1),
    (0.85, 0.5, 0.0),
    (0.55, 0.58, 0.62),
)

CSS = """
body { font-family: sans-serif; color: #1b1f24; }
h1 { font-size: 21pt; margin: 0 0 6pt 0; }
p { font-size: 12pt; line-height: 1.35; margin: 0 0 7pt 0; }
.q { font-size: 12.5pt; background-color: #f3f4f6; padding: 6pt; }
.label { font-size: 10.5pt; color: #57606a; margin: 6pt 0 2pt 0; }
.family { font-size: 14pt; font-weight: bold; margin: 12pt 0 0 0; }
.head-bad { color: #b42318; font-weight: bold; font-size: 13pt; margin: 10pt 0 3pt 0; }
.head-good { color: #0b6e4f; font-weight: bold; font-size: 13pt; margin: 10pt 0 3pt 0; }
.bad { color: #b42318; font-weight: bold; }
.good { color: #0b6e4f; font-weight: bold; }
.note { font-size: 10pt; color: #57606a; }
.big { font-size: 14pt; font-weight: bold; }
"""


def load():
    defs = {
        d["id"]: d
        for d in json.loads((ROOT / "definitions.json").read_text(encoding="utf-8"))
    }
    specs = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    cases = {
        c["id"]: c
        for c in json.loads(
            (ROOT / "cases/evaluation.json").read_text(encoding="utf-8")
        )
    }
    rows = [
        json.loads(line)
        for line in (ROOT / "results/evaluation/per-case.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    rows += [
        json.loads(line)
        for line in (ROOT / "results/ttt/scored/per-case.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    decisions = {(r["arm"], r["id"]): r for r in rows}
    summary = json.loads(
        (ROOT / "results/evaluation/summary.json").read_text(encoding="utf-8")
    )["arms"]
    summary["talkingdb_ttt"] = json.loads(
        (ROOT / "results/ttt/scored/summary.json").read_text(encoding="utf-8")
    )["arms"]["talkingdb_ttt"]
    return defs, specs, cases, decisions, summary


def where(d, specs):
    return f"TS {d['spec']} v{specs[d['spec']]['version']}, clause {d['clause']}, page {d['printed_page']}"


def crop(d, colour, name):
    """Render the real definition row from the ETSI PDF, framed, with one line of context."""
    with pymupdf.open(PDFS / f"{d['spec']}.pdf") as pdf:
        page = pdf[d["pdf_page"] - 1]
        lines = {}
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            lines.setdefault(round(y0, 1), []).append((x0, y0, x1, y1, word))
        order = sorted(lines)
        target, at = None, None
        for i, top in enumerate(order):
            words = sorted(lines[top])
            if " ".join(w[4] for w in words) == f"{d['acronym']} {d['expansion']}":
                target = pymupdf.Rect(
                    words[0][0],
                    min(w[1] for w in words),
                    max(w[2] for w in words),
                    max(w[3] for w in words),
                )
                at = i
        assert target is not None and at is not None, (
            f"row {d['id']} not found on page {d['pdf_page']} of TS {d['spec']}"
        )
        # one whole line of context above and below, never a line cut in half
        above = min(w[1] for w in lines[order[at - 1]]) if at > 0 else target.y0
        below = (
            max(w[3] for w in lines[order[at + 1]])
            if at + 1 < len(order)
            else target.y1
        )
        box = target + (-4, -2, 4, 2)
        page.draw_rect(
            box, color=colour, width=1.6
        )  # drawn in memory only; the PDF file is untouched
        clip = pymupdf.Rect(page.rect.x0 + 50, above - 0.5, page.rect.x0 + 430, below + 0.5)
        page.get_pixmap(clip=clip, dpi=220).save(OUT / name)
    return name


def render(html, name, height, width=640):
    """Lay the story out once to measure it, then draw it on a page cut to fit."""
    probe = pymupdf.Story(html=html, user_css=CSS, archive=pymupdf.Archive(str(OUT)))
    more, filled = probe.place(pymupdf.Rect(26, 22, width - 26, height - 14))
    assert not more, f"{name} overflows its page"
    height = filled[3] + 18  # place() returns the filled area as (x0, y0, x1, y1)
    story = pymupdf.Story(html=html, user_css=CSS, archive=pymupdf.Archive(str(OUT)))
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    dev = writer.begin_page(pymupdf.Rect(0, 0, width, height))
    more, _ = story.place(pymupdf.Rect(26, 22, width - 26, height - 14))
    assert not more, f"{name} overflows its page"
    story.draw(dev)
    writer.end_page()
    writer.close()
    pymupdf.open("pdf", buf.getvalue())[0].get_pixmap(dpi=150).save(OUT / f"{name}.png")


def two_meanings(defs, specs):
    pairs = [("CA", "E19", "E17"), ("CDF", "E20", "E21"), ("AMF", "E06", "E10")]
    html = """<h1>One acronym, two meanings</h1>
<p>The same letters mean different things in different 3GPP specifications.
These are the real definition rows, cut from the official ETSI PDFs.</p>"""
    for i, (acronym, a, b) in enumerate(pairs):
        da, db = defs[a], defs[b]
        assert (
            da["acronym"] == db["acronym"] == acronym
            and da["expansion"] != db["expansion"]
        )
        html += f"""<p class="family">{acronym}</p>
<p class="label">{da["expansion"]}, in {where(da, specs)} (row {a})</p><img src="{crop(da, GREY, f"_m{i}a.png")}" width="560"/>
<p class="label">{db["expansion"]}, in {where(db, specs)} (row {b})</p><img src="{crop(db, GREY, f"_m{i}b.png")}" width="560"/>"""
    html += f"""<p class="big" style="margin-top:12pt">{len(defs)} verified rows like these, from {len(specs)} specifications,
are the only evidence any method may cite.</p>"""
    render(html, "one-acronym-two-meanings", 760)


def with_and_without(defs, specs, cases, decisions, summary):
    case = cases["CDF-04"]
    none, ttt = (
        decisions[("no_glossary", "CDF-04")],
        decisions[("talkingdb_ttt", "CDF-04")],
    )
    assert none["shown"] == [] and none["verdict"] != "grounded_answer"
    assert ttt["verdict"] == "grounded_answer" and ttt["citation"] in ttt["shown"]
    assert (
        ttt["answer"] in case["expected"]["expansions"]
        and ttt["citation"] in case["expected"]["citations"]
    )
    shown = "".join(
        f"""<p class="label">Row {e}: {defs[e]["acronym"]} {defs[e]["expansion"]}, {where(defs[e], specs)}</p>
<img src="{crop(defs[e], GREEN if e == ttt["citation"] else GREY, f"_s{i}.png")}" width="560"/>"""
        for i, e in enumerate(ttt["shown"])
    )
    g, t, n = (
        summary[a]
        for a in ("glossary_in_system_prompt", "talkingdb_ttt", "no_glossary")
    )
    html = f"""<h1>The same question, without and with evidence</h1>
<p class="q"><b>Question:</b> {case["question"]}</p>
<p class="head-bad">Without evidence</p>
<p>The model answers <b>{none["answer"]}</b> and names row {none["citation"]}, but it was shown no rows,
so the answer cannot be checked. <span class="bad">Not counted.</span></p>
<p class="head-good">With TalkingDB Text-to-Tree</p>
<p>Text-to-Tree returns these rows from the specifications:</p>{shown}
<p>The model answers <b>{ttt["answer"]}</b> and cites row {ttt["citation"]}, which it was shown.
<span class="good">Grounded answer.</span></p>
<p class="note">Across all {t["answerable"]} answerable questions: glossary in the prompt {g["verdicts"]["grounded_answer"]} grounded answers,
Text-to-Tree {t["verdicts"]["grounded_answer"]} with {t["mean_input_tokens"]} input tokens on average against {g["mean_input_tokens"]},
no evidence {n["verdicts"].get("grounded_answer", 0)}. Same small model and the same choices for every method.</p>"""
    render(html, "question-with-and-without-evidence", 640)


def wrong_meaning(defs, specs, cases, decisions):
    case = cases["AMF-04"]
    ttt, glossary = (
        decisions[("talkingdb_ttt", "AMF-04")],
        decisions[("glossary_in_system_prompt", "AMF-04")],
    )
    right = case["expected"]["citations"][0]
    assert (
        ttt["verdict"] == "wrong_expansion"
        and right in ttt["shown"]
        and ttt["citation"] != right
    )
    assert glossary["verdict"] == "grounded_answer"
    rows = "".join(
        f"""<p class="label">Row {e}: {defs[e]["expansion"]}, {where(defs[e], specs)}</p>
<img src="{crop(defs[e], GREEN if e == right else RED, f"_w{i}.png")}" width="560"/>"""
        for i, e in enumerate(ttt["shown"])
    )
    html = f"""<h1>Where it goes wrong: right rows, wrong meaning</h1>
<p class="q"><b>Question:</b> {case["question"]}</p>
<p>Text-to-Tree returned both AMF rows from TS 33.501, so the right evidence was in view:</p>{rows}
<p>The small model chose <span class="bad">{ttt["answer"]}</span> (row {ttt["citation"]}).
AUTN carries the <span class="good">{defs[right]["expansion"]}</span> (row {right}).
The glossary in the prompt got this one right.</p>
<p class="note">Retrieval found the evidence; choosing between two meanings failed. That is the gap a
sense check after retrieval would have to close.</p>"""
    render(html, "wrong-meaning", 470)


def box(shape, texts, rect, text, fill, size=10.5, bold=False):
    """Queue a filled box; its text is drawn after the fills so nothing covers it."""
    shape.draw_rect(rect)
    shape.finish(color=GREY, fill=fill, width=0.8)
    texts.append((rect + (6, 5, -6, -4), text, size, bold))


def draw_texts(page, texts):
    for rect, text, size, bold in texts:
        rc = page.insert_textbox(
            rect,
            text,
            fontsize=size,
            fontname="hebo" if bold else "helv",
            align=pymupdf.TEXT_ALIGN_CENTER,
        )
        assert rc >= 0, f"text does not fit: {text!r}"


def arrow(shape, a, b):
    shape.draw_line(a, b)
    d = (b - a) / abs(b - a)
    n = pymupdf.Point(-d.y, d.x)
    shape.draw_polyline([b - d * 7 + n * 4, b, b - d * 7 - n * 4])
    shape.finish(color=GREY, width=1.2)


def how_it_works(defs, specs, cases):
    named = sum(c["kind"] == "named" for c in cases.values())
    implicit = sum(c["kind"] == "implicit" for c in cases.values())
    controls = len(cases) - named - implicit
    doc = pymupdf.open()
    page = doc.new_page(width=940, height=560)
    shape = page.new_shape()
    texts = []
    title = page.insert_textbox(
        pymupdf.Rect(20, 12, 920, 50),
        "How the benchmark works",
        fontsize=18,
        fontname="hebo",
    )
    assert title >= 0
    blue, sand, mint = (0.91, 0.94, 0.98), (0.98, 0.95, 0.88), (0.89, 0.96, 0.91)
    steps = [
        (
            f"1. {len(specs)} public 3GPP specifications, official ETSI PDFs pinned by SHA-256",
            blue,
        ),
        (
            f"2. {len(defs)} definition rows, each checked against its clause and page",
            blue,
        ),
        (
            f"3. {len(cases)} questions: {named} name the specification, {implicit} give a clue, {controls} have no right answer",
            blue,
        ),
    ]
    y = 60
    for i, (text, fill) in enumerate(steps):
        r = pymupdf.Rect(270, y, 670, y + 44)
        box(shape, texts, r, text, fill)
        if i:
            arrow(shape, pymupdf.Point(470, y - 16), pymupdf.Point(470, y))
        y += 60
    arms = [
        "No evidence",
        "Glossary in the prompt",
        "TalkingDB Text-to-Tree: top 3 rows",
        "Keyword search: top 3 rows",
        "Dense search: top 3 rows",
        "Scoped prototype: top 3 rows",
    ]
    arm_y = y + 24
    width = 140
    for i, name in enumerate(arms):
        x = 20 + i * (width + 10)
        r = pymupdf.Rect(x, arm_y, x + width, arm_y + 58)
        box(
            shape,
            texts,
            r,
            name,
            mint if "Text-to-Tree" in name else sand,
            size=10,
            bold="Text-to-Tree" in name,
        )
        arrow(shape, pymupdf.Point(470, y - 16), pymupdf.Point(x + width / 2, arm_y))
        arrow(
            shape,
            pymupdf.Point(x + width / 2, arm_y + 58),
            pymupdf.Point(470, arm_y + 96),
        )
    model = pymupdf.Rect(250, arm_y + 96, 690, arm_y + 140)
    box(
        shape,
        texts,
        model,
        "4. The same small model picks one shuffled option, or NONE",
        blue,
    )
    score = pymupdf.Rect(250, arm_y + 164, 690, arm_y + 214)
    box(
        shape,
        texts,
        score,
        "5. Counted only if the meaning is right AND the cited row was shown to the model",
        mint,
        bold=True,
    )
    arrow(shape, pymupdf.Point(470, model.y1), pymupdf.Point(470, score.y0))
    shape.commit()
    draw_texts(page, texts)
    doc[0].get_pixmap(dpi=150).save(OUT / "how-it-works.png")


def results_chart(summary):
    order = [
        ("glossary_in_system_prompt", "Glossary in the prompt"),
        ("glossary_full", "Full glossary"),
        ("bge_dense", "Dense search"),
        ("scoped_prototype", "Scoped prototype"),
        ("talkingdb_ttt", "TalkingDB Text-to-Tree"),
        ("bm25", "Keyword search (BM25)"),
        ("no_glossary", "No evidence"),
    ]
    doc = pymupdf.open()
    page = doc.new_page(width=900, height=420)
    shape = page.new_shape()
    assert (
        page.insert_textbox(
            pymupdf.Rect(20, 12, 880, 50),
            "Grounded answers out of 40, and average input tokens",
            fontsize=17,
            fontname="hebo",
        )
        >= 0
    )
    left, top, bar_max, row = 230, 64, 420, 44
    total = summary["talkingdb_ttt"]["answerable"]
    for i, (key, name) in enumerate(order):
        arm = summary[key]
        assert arm["answerable"] == total
        grounded = arm["verdicts"].get("grounded_answer", 0)
        y = top + i * row
        ttt = key == "talkingdb_ttt"
        assert (
            page.insert_textbox(
                pymupdf.Rect(20, y + 6, left - 10, y + 30),
                name,
                fontsize=11.5,
                fontname="hebo" if ttt else "helv",
                align=pymupdf.TEXT_ALIGN_RIGHT,
            )
            >= 0
        )
        shape.draw_rect(pymupdf.Rect(left, y + 6, left + bar_max, y + 30))
        shape.finish(color=None, fill=(0.94, 0.95, 0.96))
        if grounded:
            shape.draw_rect(
                pymupdf.Rect(left, y + 6, left + bar_max * grounded / total, y + 30)
            )
            shape.finish(color=None, fill=GREEN if ttt else (0.45, 0.55, 0.68))
        label = f"{grounded} of {total}   |   {arm['mean_input_tokens']} tokens"
        assert (
            page.insert_textbox(
                pymupdf.Rect(left + bar_max + 10, y + 8, 890, y + 30),
                label,
                fontsize=11,
                fontname="hebo" if ttt else "helv",
            )
            >= 0
        )
    note = (
        "Same small model, same shuffled choices, same 768 token cap for the budgeted methods. "
        "Text-to-Tree scored 2 fewer grounded answers than the glossary with 61% fewer input tokens; "
        "the difference in quality is uncertain on 40 questions."
    )
    assert (
        page.insert_textbox(
            pymupdf.Rect(20, top + len(order) * row + 6, 880, 410), note, fontsize=10.5
        )
        >= 0
    )
    shape.commit()
    doc[0].get_pixmap(dpi=150).save(OUT / "results.png")


def main():
    OUT.mkdir(exist_ok=True)
    defs, specs, cases, decisions, summary = load()
    two_meanings(defs, specs)
    with_and_without(defs, specs, cases, decisions, summary)
    wrong_meaning(defs, specs, cases, decisions)
    how_it_works(defs, specs, cases)
    results_chart(summary)
    saving = (
        1
        - summary["talkingdb_ttt"]["mean_input_tokens"]
        / summary["glossary_in_system_prompt"]["mean_input_tokens"]
    )
    assert round(saving * 100) == 61, saving
    for f in OUT.glob("_*.png"):
        f.unlink()
    print("Wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
