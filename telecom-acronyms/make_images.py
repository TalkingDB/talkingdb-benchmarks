"""Draw every image in images/ from the pinned ETSI PDFs and the saved results.

Usage: python make_images.py
Needs: pip install -r requirements-images.txt, then python sources.py --fetch and
python fetch_data.py so the PDFs and the per question results are present.

Every number and answer drawn here is read from definitions.json, cases/ and
results/. Definition rows are cut from the real PDF pages. The script stops if a
row is not on its page, if a label runs outside its image, if two labels overlap,
or if an example no longer shows what its caption says.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pdfplumber  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parent
PDFS = ROOT / ".cache/pdfs"
OUT = ROOT / "images"
FONTS = Path(matplotlib.get_data_path()) / "fonts/ttf"

INK, MUTED, RULE, PANEL = "#191919", "#5f6368", "#d9dce0", "#f3f4f6"
GOOD, WARN, BAD, NONE_GREY = "#0aac23", "#fbb315", "#dc3c3d", "#b9bcc1"
GOOD_TEXT, BAD_TEXT, FOCUS = "#0b6e4f", "#b42318", "#257de0"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
                     "axes.edgecolor": RULE, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})

ARMS = ["no_glossary", "glossary_in_system_prompt", "glossary_full", "talkingdb_ttt",
        "bm25", "bge_dense", "scoped_prototype"]
NAMES = {"no_glossary": "No evidence", "glossary_in_system_prompt": "Glossary in the prompt",
         "glossary_full": "Full glossary", "talkingdb_ttt": "TalkingDB Text-to-Tree",
         "bm25": "Keyword search", "bge_dense": "Dense search", "scoped_prototype": "Scoped prototype"}
KINDS = [("named", "Names the specification"), ("implicit", "Gives a clue"),
         ("ambiguous", "Control: no context"), ("unsupported", "Not in scope")]


# ---------------------------------------------------------------- data

def jsonl(rel):
    return [json.loads(line) for line in (ROOT / rel).read_text(encoding="utf-8").splitlines()]


def load():
    data = {
        "defs": {d["id"]: d for d in json.loads((ROOT / "definitions.json").read_text(encoding="utf-8"))},
        "specs": json.loads((ROOT / "sources.json").read_text(encoding="utf-8")),
        "cases": {c["id"]: c for c in json.loads((ROOT / "cases/evaluation.json").read_text(encoding="utf-8"))},
        "balanced": json.loads((ROOT / "results/balanced/summary.json").read_text(encoding="utf-8")),
    }
    published = jsonl("results/evaluation/per-case.jsonl") + jsonl("results/ttt/scored/per-case.jsonl")
    data["published"] = {(r["arm"], r["id"]): r for r in published}
    runs = defaultdict(list)
    for r in jsonl("results/balanced/per-run.jsonl"):
        runs[(r["arm"], r["id"])].append(r)
    data["runs"] = runs
    order = {kind: i for i, (kind, _) in enumerate(KINDS)}
    data["order"] = sorted(data["cases"], key=lambda cid: (order[data["cases"][cid]["kind"]], cid))
    return data


def where(d, specs):
    return f"TS {d['spec']} v{specs[d['spec']]['version']}, clause {d['clause']}, page {d['printed_page']}"


# ---------------------------------------------------------------- checks

def assert_text_inside(fig, name):
    """Everything matplotlib actually draws, labels included, must sit inside the image."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tight = fig.get_tightbbox(renderer)
    w, h = fig.get_size_inches()
    assert tight.x0 >= -0.01 and tight.y0 >= -0.01 and tight.x1 <= w + 0.01 and tight.y1 <= h + 0.01, \
        f"{name}: something is drawn outside the image ({tight.bounds} inside {w} x {h} inches)"
    return renderer


def assert_apart(texts, renderer, name):
    boxes = [(t.get_text(), t.get_window_extent(renderer)) for t in texts]
    for i, (a, ba) in enumerate(boxes):
        for b, bb in boxes[i + 1:]:
            assert not ba.overlaps(bb), f"{name}: labels overlap: {a!r} and {b!r}"


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=150, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- PDF rows

def crop(d, colour):
    """The real definition row from the ETSI PDF, framed, with one whole line above and below."""
    with pdfplumber.open(PDFS / f"{d['spec']}.pdf") as pdf:
        page = pdf.pages[d["pdf_page"] - 1]
        lines = []
        for w in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
            if lines and abs(lines[-1][0]["top"] - w["top"]) < 2:
                lines[-1].append(w)
            else:
                lines.append([w])
        text = [" ".join(w["text"] for w in sorted(line, key=lambda w: w["x0"])) for line in lines]
        hits = [i for i, t in enumerate(text) if t == f"{d['acronym']} {d['expansion']}"]
        assert len(hits) == 1, f"row {d['id']} not found once on page {d['pdf_page']} of TS {d['spec']}"
        at = hits[0]
        row = lines[at]
        top = min(w["top"] for w in (lines[at - 1] if at else row))
        bottom = max(w["bottom"] for w in (lines[at + 1] if at + 1 < len(lines) else row))
        x0 = page.bbox[0] + 50
        near = [w for line in lines[max(at - 1, 0):at + 2] for w in line]
        x1 = min(max(w["x1"] for w in near) + 8, page.bbox[2])
        image = page.crop((x0, top - 1.5, x1, bottom + 1.5)).to_image(resolution=200).original.convert("RGB")
        scale = 200 / 72
        rx0 = (min(w["x0"] for w in row) - x0 - 4) * scale
        rx1 = (max(w["x1"] for w in row) - x0 + 4) * scale
        ry0 = (min(w["top"] for w in row) - (top - 1.5) - 2) * scale
        ry1 = (max(w["bottom"] for w in row) - (top - 1.5) + 2) * scale
        ImageDraw.Draw(image).rectangle([rx0, ry0, rx1, ry1], outline=colour, width=4)
        return image


# ---------------------------------------------------------------- document images

class Doc:
    """A column of headings, wrapped text and PDF crops; every line is measured before it is drawn."""

    W, M = 1300, 56

    def __init__(self):
        self.blocks = []

    @staticmethod
    def font(size, bold=False):
        return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)

    def text(self, runs, size=21, colour=INK, bold=False, gap=10, fill=None, indent=0):
        if isinstance(runs, str):
            runs = [(runs, {})]
        self.blocks.append(("text", runs, size, colour, bold, gap, fill, indent))

    def image(self, image, gap=6, indent=24):
        self.blocks.append(("image", image, gap, indent))

    def rule(self, gap=14):
        self.blocks.append(("rule", gap))

    def table(self, header, rows, fractions, size=17, gap=14):
        """rows: lists of cells; a cell is a list of runs, or (runs, fill)."""
        self.blocks.append(("table", header, rows, fractions, size, gap))

    def _lines(self, runs, size, colour, bold, width):
        words, open_space = [], True
        for text, style in runs:
            f = self.font(size, style.get("bold", bold))
            c = style.get("colour", colour)
            for i, word in enumerate(text.split(" ")):
                if word:
                    # glue to the previous word only when neither side of the run boundary has a space
                    words.append((word, f, c, i == 0 and not open_space))
            open_space = text.endswith(" ")
        lines, line, used = [], [], 0
        space = self.font(size).getlength(" ")
        for word, f, c, glued in words:
            w = f.getlength(word)
            assert w <= width, f"word wider than the image: {word!r}"
            extra = 0 if (not line or glued) else space
            if line and used + extra + w > width:
                lines.append(line)
                line, used, extra = [], 0, 0
            line.append((word, f, c, extra))
            used += extra + w
        if line:
            lines.append(line)
        return lines

    def render(self, name):
        width = self.W - 2 * self.M
        plan, y = [], 40
        for block in self.blocks:
            if block[0] == "text":
                _, runs, size, colour, bold, gap, fill, indent = block
                pad = 12 if fill else 0
                lines = self._lines(runs, size, colour, bold, width - indent - 2 * pad)
                height = len(lines) * int(size * 1.42) + 2 * pad
                plan.append(("text", y, lines, size, fill, pad, indent, height))
                y += height + gap
            elif block[0] == "image":
                _, image, gap, indent = block
                assert image.width + indent <= width, f"{name}: image wider than the column"
                plan.append(("image", y, image, indent))
                y += image.height + gap
            elif block[0] == "table":
                _, header, rows, fractions, size, gap = block
                assert abs(sum(fractions) - 1) < 1e-9
                widths = [int(width * f) for f in fractions]
                laid = []
                for r, row in enumerate([header] + rows):
                    cells = []
                    for cell, w in zip(row, widths):
                        runs, fill = cell if isinstance(cell, tuple) else (cell, None)
                        if r == 0:
                            runs, fill = [B(t, MUTED) for t, _ in runs], PANEL
                        cells.append((self._lines(runs, size, INK, False, w - 20), fill, w))
                    height = max(len(c[0]) for c in cells) * int(size * 1.42) + 20
                    laid.append((cells, height))
                plan.append(("table", y, laid, size))
                y += sum(h for _, h in laid) + gap
            else:
                plan.append(("rule", y + block[1] // 2))
                y += block[1]
        canvas = Image.new("RGB", (self.W, y + 30), "white")
        draw = ImageDraw.Draw(canvas)
        for item in plan:
            if item[0] == "text":
                _, top, lines, size, fill, pad, indent, height = item
                if fill:
                    draw.rectangle([self.M + indent, top, self.W - self.M, top + height], fill=fill)
                for i, line in enumerate(lines):
                    x = self.M + indent + pad
                    for word, f, c, extra in line:
                        x += extra
                        draw.text((x, top + pad + i * int(size * 1.42)), word, font=f, fill=c)
                        x += f.getlength(word)
                    assert x <= self.W - self.M - pad + 0.5, f"{name}: a line runs past the margin"
            elif item[0] == "image":
                _, top, image, indent = item
                canvas.paste(image, (self.M + indent, top))
            elif item[0] == "table":
                _, top, laid, size = item
                for cells, height in laid:
                    x = self.M
                    for lines, fill, w in cells:
                        draw.rectangle([x, top, x + w, top + height], fill=fill or "white", outline=RULE, width=2)
                        for i, line in enumerate(lines):
                            tx = x + 10
                            for word, f, c, extra in line:
                                tx += extra
                                draw.text((tx, top + 10 + i * int(size * 1.42)), word, font=f, fill=c)
                                tx += f.getlength(word)
                            assert tx <= x + w - 9.5, f"{name}: a table cell overflows"
                        x += w
                    top += height
            else:
                draw.line([self.M, item[1], self.W - self.M, item[1]], fill=RULE, width=2)
        canvas.save(OUT / f"{name}.png", optimize=True)


def B(text, colour=INK):
    return (text, {"bold": True, "colour": colour})


def P(text, colour=INK):
    return (text, {"colour": colour})


def two_meanings(data):
    defs, specs = data["defs"], data["specs"]
    pairs = [("CA", "E19", "E17"), ("CDF", "E20", "E21"), ("AMF", "E06", "E10")]
    doc = Doc()
    doc.text("One acronym, two meanings", size=34, bold=True, gap=8)
    doc.text("The same letters mean different things in different 3GPP specifications. "
             "These are the real definition rows, cut from the official ETSI PDFs.", gap=18)
    for acronym, a, b in pairs:
        da, db = defs[a], defs[b]
        assert da["acronym"] == db["acronym"] == acronym and da["expansion"] != db["expansion"]
        doc.text(acronym, size=24, bold=True, gap=6)
        for d in (da, db):
            doc.text(f"{d['expansion']}, in {where(d, specs)} (row {d['id']})", size=17, colour=MUTED, gap=4)
            doc.image(crop(d, "#8a9099"), gap=10)
        doc.rule()
    doc.text(f"{len(defs)} verified rows like these, from {len(specs)} specifications, "
             "are the only evidence any method may cite.", size=21, bold=True)
    doc.render("one-acronym-two-meanings")


def stable(runs):
    """The one row chosen in every rotation, or None if the choice moved with the letters."""
    chosen = {r["chosen"] for r in runs}
    return chosen.pop() if len(chosen) == 1 else None


VERDICT_TEXT = {"grounded_answer": ("grounded", GOOD_TEXT), "wrong_or_missing_citation": ("right meaning, no row shown", "#8a5a00"),
                "wrong_expansion": ("wrong meaning", BAD_TEXT), "missed_answer": ("declined", MUTED),
                "correct_abstention": ("correct decline", GOOD_TEXT), "guessed_on_control": ("guessed", BAD_TEXT)}


def end_to_end(data, cid):
    """One question, every option order: the evidence was in view, the choice followed the letter."""
    defs, specs, case = data["defs"], data["specs"], data["cases"][cid]
    none = sorted(data["runs"][("no_glossary", cid)], key=lambda r: r["rotation"])
    ttt = sorted(data["runs"][("talkingdb_ttt", cid)], key=lambda r: r["rotation"])
    gold = set(case["expected"]["citations"])
    shown = ttt[0]["shown"]
    assert gold & set(shown), f"{cid}: Text-to-Tree did not show the right row"
    assert [r["chosen"] for r in none] == [r["chosen"] for r in ttt], f"{cid}: evidence changed the choice"
    assert all(r["selected"] == "C" for r in none + ttt), f"{cid}: not every choice was C"
    doc = Doc()
    doc.text("One question, every option order", size=34, bold=True, gap=6)
    doc.text("The right row was in view. The small model's answer still followed the letter.", size=22, colour=MUTED, gap=14)
    doc.text([B("Question: "), P(case["question"])], size=22, fill=PANEL, gap=14)
    doc.text("TalkingDB Text-to-Tree returned these rows, cut here from the official PDF:", gap=6)
    for e in shown:
        d = defs[e]
        doc.text(f"Row {e}: {d['acronym']} {d['expansion']}, {where(d, specs)}", size=17, colour=MUTED, gap=4)
        doc.image(crop(d, GOOD if e in gold else "#8a9099"), gap=10)
    doc.text(f"Then the same {len(ttt)} options were shown in {len(ttt)} orders, once with no rows and once with "
             "Text-to-Tree's rows:", gap=8)

    def option(e):
        return "NONE" if e == "NONE" else f"{defs[e]['expansion']} [{e}]"

    def outcome(r):
        label, colour = VERDICT_TEXT[r["verdict"]]
        return [B(f"{r['selected']}: "), P(option(r["chosen"]) + ", "), B(label, colour)]

    rows = []
    for a, b in zip(none, ttt):
        order = []
        for letter, e in zip("ABCDEF", a["order"]):
            order += [B(f"{letter} ", FOCUS if letter == "C" else INK), P(option(e) + "  ")]
        rows.append([order, outcome(a), outcome(b)])
    doc.table([[P("Options, in the order shown")], [P("Chosen with no rows")], [P("Chosen with Text-to-Tree's rows")]],
              rows, [0.46, 0.27, 0.27])
    every = [r for runs in data["runs"].values() for r in runs]
    c = sum(r["selected"] == "C" for r in every)
    doc.text([P("Both columns are the same: whatever sat at "), B("C", FOCUS), P(" was chosen. Across all "),
              B(f"{len(every):,} rotated runs"), P(", the model chose C "), B(f"{c:,} times"),
              P(". Retrieval put the right row in view; this answer model did not read it.")], gap=6)
    doc.render("one-question-every-order")


def where_it_misses(data, arm, cids):
    """Questions where the method did not return any accepted row."""
    defs, specs, cases = data["defs"], data["specs"], data["cases"]
    doc = Doc()
    doc.text(f"Where {NAMES[arm]} missed the row", size=34, bold=True, gap=8)
    misses = [cid for cid in data["order"] if (g := set(cases[cid]["expected"].get("citations", [])))
              and not g & set(data["published"][(arm, cid)]["shown"])]
    assert misses == cids, f"{arm} missed {misses}, the image expects {cids}"
    answerable = sum("citations" in c["expected"] for c in cases.values())
    doc.text(f"It returned an accepted row for {answerable - len(misses)} of {answerable} answerable questions. "
             f"These are the {len(misses)} it missed, with the row that answers each one.", size=19, colour=MUTED, gap=16)
    for cid in cids:
        case, shown = cases[cid], data["published"][(arm, cid)]["shown"]
        doc.text([B(f"{cid}: "), P(case["question"])], size=20, fill=PANEL, gap=8)
        doc.text("It returned:", size=18, gap=4)
        for e in shown:
            d = defs[e]
            doc.text(f"Row {e}: {d['acronym']} {d['expansion']}, {where(d, specs)}", size=16, colour=MUTED, gap=3)
            doc.image(crop(d, BAD), gap=6)
        for e in sorted(case["expected"]["citations"]):
            d = defs[e]
            doc.text(f"Not returned, the row that answers it: {e}, {where(d, specs)}", size=16, colour=GOOD_TEXT, gap=3)
            doc.image(crop(d, GOOD), gap=6)
        doc.rule()
    doc.render("where-it-misses")


# ---------------------------------------------------------------- charts

def position_bias(data):
    published = list(data["published"].values())
    letters = Counter(r["selected"] for r in published)
    total = len(published)
    assert total == 7 * len(data["cases"])
    fig = plt.figure(figsize=(12.6, 5.6))
    fig.text(0.035, 0.94, "The flaw in the published run: the model picked a letter, not an answer",
             fontsize=16, fontweight="bold")
    same = sum(len({data["published"][(a, cid)]["selected"] for a in ARMS}) == 1 for cid in data["cases"])
    fig.text(0.035, 0.885, f"{letters['C']} of {total} decisions chose option C. In {same} of {len(data['cases'])} "
             "questions all seven methods chose the same letter, whatever rows they showed.", fontsize=11, color=MUTED)
    ax = fig.add_axes([0.06, 0.13, 0.3, 0.62])
    order = list("ABCDEF")
    values = [letters.get(k, 0) for k in order]
    bars = ax.bar(order, values, color=[FOCUS if k == "C" else NONE_GREY for k in order], width=0.62)
    labels = [ax.text(b.get_x() + b.get_width() / 2, v + 6, str(v), ha="center", fontsize=10)
              for b, v in zip(bars, values)]
    ax.set_ylim(0, total)
    ax.set_title(f"Letter chosen, all {total} decisions", fontsize=11, loc="left", color=INK)
    ax.set_yticks([0, 100, 200, 300])
    ax.tick_params(length=0)
    ax.grid(axis="y", color="#eeeeee")
    ax.set_axisbelow(True)

    # what sat at C, against the verdicts it produced
    cats = [("right row at C", "grounded_answer", GOOD), ("right meaning, other row at C", "wrong_or_missing_citation", WARN),
            ("wrong meaning at C", "wrong_expansion", BAD), ("NONE at C", "missed_answer", NONE_GREY)]
    at_c = Counter()
    from benchmark import answer_options  # the same seeded order the benchmark used
    entries = list(data["defs"].values())
    answerable = [c for c in data["cases"].values() if "citations" in c["expected"]]
    for case in answerable:
        o = answer_options(case, entries)["C"]
        exp = case["expected"]
        if o is None:
            at_c["missed_answer"] += 1
        elif o["id"] in exp["citations"]:
            at_c["grounded_answer"] += 1
        elif o["expansion"].casefold() in {e.casefold() for e in exp["expansions"]}:
            at_c["wrong_or_missing_citation"] += 1
        else:
            at_c["wrong_expansion"] += 1
    assert sum(at_c.values()) == len(answerable)
    ax2 = fig.add_axes([0.49, 0.13, 0.48, 0.62])
    series = [("What the shuffle put at C", None), ("Glossary in the prompt, verdicts", "glossary_in_system_prompt"),
              ("Text-to-Tree, verdicts", "talkingdb_ttt")]
    h = 0.26
    value_labels = []
    short = ["put at C by the shuffle", "Glossary in the prompt", "Text-to-Tree"]
    for j, (label, arm) in enumerate(series):
        if arm:
            v = Counter(data["published"][(arm, c["id"])]["verdict"] for c in answerable)
        else:
            v = at_c
        ys = [i + (j - 1) * h for i in range(len(cats))]
        xs = [v.get(key, 0) for _, key, _ in cats]
        ax2.barh(ys, xs, height=h - 0.04, color=[c for *_, c in cats], alpha=[1.0, 0.55, 0.55][j],
                 hatch=[None, None, "///"][j], edgecolor="white", linewidth=0.5)
        for y, x in zip(ys, xs):
            value_labels.append(ax2.text(x + 0.3, y, f"{x}  {short[j]}", va="center", fontsize=8.5,
                                         color=INK if j == 0 else MUTED))
    ax2.set_yticks(range(len(cats)))
    ax2.set_yticklabels([c[0] for c in cats], fontsize=10)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 25)
    ax2.set_xticks([0, 5, 10, 15, 20])
    ax2.set_xlabel(f"answerable questions, out of {len(answerable)}")
    ax2.tick_params(length=0)
    ax2.set_title("What sat at C, against the published verdicts", fontsize=11, loc="left", color=INK)
    renderer = assert_text_inside(fig, "answer-position-bias")
    assert_apart(labels, renderer, "answer-position-bias")
    assert_apart(value_labels, renderer, "answer-position-bias")
    save(fig, "answer-position-bias")
    return letters, at_c


def results(data):
    arms, cases = data["balanced"]["arms"], data["cases"]
    answerable = [c for c in cases.values() if "citations" in c["expected"]]
    shown = {a: sum(bool(set(c["expected"]["citations"]) & set(data["published"][(a, c["id"])]["shown"]))
                    for c in answerable) for a in ARMS}
    tokens = {a: round(sum(data["published"][(a, cid)]["input_tokens"] for cid in cases) / len(cases), 1) for a in ARMS}
    n = arms[ARMS[0]]["answerable_runs"]
    order = ARMS
    fig = plt.figure(figsize=(13.2, 5.8))
    fig.text(0.02, 0.94, "What this pilot can and cannot tell apart", fontsize=16, fontweight="bold")
    fig.text(0.02, 0.885, "Left and middle: what each method put in front of the model. Right: what the model did with it, "
             "after every option was moved through every letter.", fontsize=11, color=MUTED)
    panels = [fig.add_axes([0.17, 0.17, 0.22, 0.6]), fig.add_axes([0.44, 0.17, 0.2, 0.6]),
              fig.add_axes([0.69, 0.17, 0.29, 0.6])]
    titles = [f"Accepted row shown, of {len(answerable)} questions", "Mean input tokens per question",
              f"Grounded runs, of {n}"]
    labels = []
    for p, (ax, title) in enumerate(zip(panels, titles)):
        ax.set_title(title, fontsize=10.5, loc="left", color=INK)
        ax.set_ylim(len(order) - 0.5, -0.5)
        ax.tick_params(length=0)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([NAMES[a] for a in order] if p == 0 else [], fontsize=10.5)
        ax.grid(axis="x", color="#eeeeee")
        ax.set_axisbelow(True)
        for i, arm in enumerate(order):
            colour = FOCUS if arm == "talkingdb_ttt" else "#9aa3ad"
            if p == 0:
                ax.barh(i, shown[arm], height=0.6, color=colour)
                labels.append(ax.text(shown[arm] + 0.6, i, f"{shown[arm]}", va="center", fontsize=9.5))
            elif p == 1:
                ax.barh(i, tokens[arm], height=0.6, color=colour)
                labels.append(ax.text(tokens[arm] + 8, i, f"{tokens[arm]}", va="center", fontsize=9.5))
            else:
                a = arms[arm]
                ax.plot([a["letter_only_grounded_runs"], a["grounded_runs"]], [i, i], color="#cfd3d8", linewidth=2)
                ax.plot(a["letter_only_grounded_runs"], i, marker="o", markersize=8, markerfacecolor="white",
                        markeredgecolor=INK, markeredgewidth=1.5)
                ax.plot(a["grounded_runs"], i, marker="o", markersize=8, color=colour)
                labels.append(ax.text(max(a["grounded_runs"], a["letter_only_grounded_runs"]) + 3.5, i,
                                      f"{a['grounded_runs']}  (letter alone {a['letter_only_grounded_runs']})",
                                      va="center", fontsize=9.5))
    for tick, arm in zip(panels[0].get_yticklabels(), order):
        if arm == "talkingdb_ttt":
            tick.set_fontweight("bold")
    panels[0].set_xlim(0, len(answerable) + 8)
    panels[1].set_xlim(0, 760)
    panels[2].set_xlim(0, 92)
    panels[2].plot([], [], marker="o", color=FOCUS, linestyle="none", label="the model, options rotated")
    panels[2].plot([], [], marker="o", markerfacecolor="white", markeredgecolor=INK, linestyle="none",
                   label="always picking the same letter")
    legend = panels[2].legend(loc="upper left", bbox_to_anchor=(-0.02, -0.08), ncol=1, fontsize=9, frameon=False)
    renderer = assert_text_inside(fig, "results")
    for ax in panels:
        assert_apart([t for t in labels if t.axes is ax], renderer, "results")
    box = legend.get_window_extent(renderer)
    assert not any(box.overlaps(t.get_window_extent(renderer)) for t in labels), "results: legend covers a label"
    save(fig, "results")
    return shown, tokens


def every_question(data):
    order, cases = data["order"], data["cases"]
    fig = plt.figure(figsize=(16, 7.9))
    fig.text(0.02, 0.955, f"Every question, every method: {len(order)} questions by {len(ARMS)} methods",
             fontsize=16, fontweight="bold")
    fig.text(0.02, 0.918, "Top: the published run, one fixed option order per question; each cell shows the letter "
             "the model chose. Bottom: the share of rotations that were grounded, or correctly declined for controls.",
             fontsize=11, color=MUTED)
    colours = {"grounded_answer": GOOD, "correct_abstention": GOOD, "wrong_or_missing_citation": WARN,
               "wrong_expansion": BAD, "guessed_on_control": BAD, "missed_answer": NONE_GREY}
    panels = [fig.add_axes([0.13, 0.575, 0.86, 0.265]), fig.add_axes([0.13, 0.185, 0.86, 0.265])]
    group_labels = []
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("share", ["#f5f5f5", "#7fcf8c", GOOD])
    for p, ax in enumerate(panels):
        for i, arm in enumerate(ARMS):
            for j, cid in enumerate(order):
                if p == 0:
                    r = data["published"][(arm, cid)]
                    ax.add_patch(Rectangle((j, i), 0.92, 0.88, color=colours[r["verdict"]]))
                    ax.text(j + 0.46, i + 0.47, r["selected"], ha="center", va="center", fontsize=6.5,
                            color="white" if r["verdict"] in ("wrong_expansion", "guessed_on_control", "grounded_answer",
                                                               "correct_abstention") else INK)
                else:
                    runs = data["runs"][(arm, cid)]
                    good = sum(r["verdict"] in ("grounded_answer", "correct_abstention") for r in runs)
                    ax.add_patch(Rectangle((j, i), 0.92, 0.88, color=cmap(good / len(runs))))
                    gold = set(cases[cid]["expected"].get("citations", []))
                    if gold and not gold & set(runs[0]["shown"]):
                        ax.plot(j + 0.46, i + 0.44, marker="x", color=INK, markersize=4, mew=1)
        ax.set_xlim(0, len(order))
        ax.set_ylim(len(ARMS), 0)
        ax.set_yticks([i + 0.44 for i in range(len(ARMS))])
        ax.set_yticklabels([NAMES[a] for a in ARMS], fontsize=9)
        ax.set_xticks([j + 0.46 for j in range(len(order))])
        ax.set_xticklabels(order if p == 1 else [], rotation=90, fontsize=6.5)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        start = 0
        for kind, label in KINDS:
            count = sum(cases[c]["kind"] == kind for c in order)
            if p == 0:
                last = kind == KINDS[-1][0]
                group_labels.append(ax.text(start + count if last else start + count / 2, -0.25, f"{label} ({count})",
                                            ha="right" if last else "center", va="bottom", fontsize=9, color=MUTED))
            if start:
                ax.axvline(start - 0.04, color=INK, linewidth=1)
            start += count
    panels[0].set_title("Published run", loc="left", fontsize=11, pad=16)
    panels[1].set_title("Position balanced rerun", loc="left", fontsize=11, pad=6)
    legend = [Rectangle((0, 0), 1, 1, color=c) for c in (GOOD, WARN, BAD, NONE_GREY)]
    panels[0].legend(legend, ["grounded or correct decline", "right meaning, wrong row", "wrong meaning or guessed",
                              "declined though answerable"], loc="lower left", bbox_to_anchor=(-0.14, -0.25),
                     ncol=4, fontsize=8.5, frameon=False)
    sm = matplotlib.cm.ScalarMappable(cmap=cmap, norm=matplotlib.colors.Normalize(0, 1))
    bar = fig.colorbar(sm, cax=fig.add_axes([0.79, 0.075, 0.18, 0.016]), orientation="horizontal")
    bar.set_ticks([0, 0.5, 1])
    bar.set_ticklabels(["never", "half the rotations", "every rotation"], fontsize=8)
    bar.outline.set_visible(False)
    fig.text(0.13, 0.07, "x = the right row was not among the rows this method showed", fontsize=8.5, color=MUTED)
    renderer = assert_text_inside(fig, "every-question")
    assert_apart(group_labels, renderer, "every-question")
    ticks = [t for t in panels[1].get_xticklabels() if t.get_text()]
    assert all(not t.get_window_extent(renderer).overlaps(bar.ax.get_window_extent(renderer)) for t in ticks), \
        "every-question: the colour key covers a question id"
    save(fig, "every-question")


def main():
    OUT.mkdir(exist_ok=True)
    data = load()
    position_bias(data)
    results(data)
    every_question(data)
    two_meanings(data)
    end_to_end(data, "CDF-04")
    where_it_misses(data, "talkingdb_ttt", ["SCS-01", "SCS-03"])
    print("Wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
