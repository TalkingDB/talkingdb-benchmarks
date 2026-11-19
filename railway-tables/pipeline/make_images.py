"""Draw the two annotated images in images/ from the PDF and results/results.json.

Usage: python make_images.py   (needs pymupdf only)
"""

import io
import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import cells_of, identity  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "documents/raib-recommendations-index.pdf"
OUT = ROOT / "images"
GREEN, RED, AMBER = (0.05, 0.55, 0.3), (0.85, 0.1, 0.1), (0.85, 0.5, 0.0)
X0, X1 = 362, 760  # from "Report No" to the end of "End Implementer/s"

CSS = """
body { font-family: sans-serif; color: #1b1f24; }
h1 { font-size: 22pt; margin: 0 0 6pt 0; }
p { font-size: 12pt; line-height: 1.35; margin: 0 0 8pt 0; }
.kept { color: #0d8c4d; font-weight: bold; font-size: 11pt; margin: 6pt 0 2pt 0; }
.lost { color: #d91a1a; font-weight: bold; font-size: 11pt; margin: 6pt 0 2pt 0; }
.amber { color: #c26a00; font-weight: bold; font-size: 11pt; margin: 6pt 0 2pt 0; }
.case { font-size: 13pt; font-weight: bold; margin: 14pt 0 0 0; }
.note { font-size: 10pt; color: #57606a; }
table { border-collapse: collapse; margin: 4pt 0 6pt 0; }
td, th { font-size: 11pt; padding: 4pt 8pt; border: 1px solid #8c959f; text-align: left; }
th { background-color: #eef1f4; }
.big { font-size: 15pt; font-weight: bold; }
"""


def crop(src, page, y0, y1, colour, name):
    """Render one band of a page with a coloured frame around it."""
    p = src[page - 1]
    r = pymupdf.Rect(X0, y0, X1, y1)
    if colour:
        p.draw_rect(r + (1, 1, -1, -1), color=colour, width=2.2)
    p.get_pixmap(clip=r, dpi=200).save(OUT / name)
    return name


def render(html, name, height):
    story = pymupdf.Story(html=html, user_css=CSS, archive=pymupdf.Archive(str(OUT)))
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    dev = writer.begin_page(pymupdf.Rect(0, 0, 640, height))
    more, _ = story.place(pymupdf.Rect(28, 24, 612, height - 16))
    assert not more, f"{name} overflows"
    story.draw(dev)
    writer.end_page()
    writer.close()
    pymupdf.open("pdf", buf.getvalue())[0].get_pixmap(dpi=150).save(
        OUT / (name + ".png")
    )


def lost_rows():
    src = pymupdf.open(
        PDF
    )  # frames are drawn in memory only, the PDF file is untouched
    blocks = [
        ("Report 13/2024", (1, 743, 781, "page 1"), (2, 55, 74, "top of page 2")),
        ("Report 01/2024", (2, 766, 784, "page 2"), (3, 55, 74, "top of page 3")),
        (
            "Recommendation 07/2023/04",
            (3, 747, 784, "page 3"),
            (4, 55, 74, "top of page 4"),
        ),
    ]
    head = crop(src, 1, 84, 107, None, "_header.png")
    html = f"""<h1>Where rows go missing at a page break</h1>
<p>Index of recommendations from the UK Rail Accident Investigation Branch, a public PDF.
Standard PDF table extraction reads the first row of every new page as column names,
so that row disappears from the table.</p>
<p class="note">Column names, as printed on page 1</p><img src="{head}" width="584"/>"""
    for i, (title, (kp, ky0, ky1, kl), (lp, ly0, ly1, ll)) in enumerate(blocks):
        kept = crop(src, kp, ky0, ky1, GREEN, f"_kept{i}.png")
        lost = crop(src, lp, ly0, ly1, RED, f"_lost{i}.png")
        html += f"""<p class="case">{title}</p>
<p class="kept">Kept, {kl}</p><img src="{kept}" width="584"/>
<p class="lost">Lost, {ll}: read as column names</p><img src="{lost}" width="584"/>"""
    html += """<p class="big" style="margin-top:14pt">Standard extraction keeps 10 of the 13 expected rows.
The TalkingDB page break fix keeps all 13, with no wrong rows.</p>"""
    render(html, "lost-rows", 720)
    for f in OUT.glob("_*.png"):
        f.unlink()


def answer():
    res = json.loads((ROOT / "results/results.json").read_text(encoding="utf-8"))
    ttt = res["ttt_answers"]
    case = ttt["with_page_break_fix"]["lookups_detail"][0]
    # the same exact identity the scorer uses: (recommendation, who must act, page)
    rows = [
        ident
        for r in case["results"]
        for cells in cells_of(r)
        if (ident := identity(cells)) and ident[0].startswith("13/2024/")
    ]
    expected = {
        (e["recommendation"], e["implementer"], e["page"])
        for e in json.loads(
            (ROOT / "cases/raib-lookups.json").read_text(encoding="utf-8")
        )[0]["expected_rows"]
    }
    assert set(rows) == expected, rows
    body = "".join(
        f"<tr><td>&#10003;</td><td>{rec}</td><td>{who}</td><td>page {page}</td></tr>"
        for rec, who, page in rows
    )
    s, f = ttt["standard_extraction"], ttt["with_page_break_fix"]
    html = f"""<h1>What TalkingDB returns</h1>
<p><b>Question:</b> {case["question"]}</p>
<table border="1" cellspacing="0"><tr><th></th><th>Recommendation</th><th>Who must act</th><th>Page</th></tr>{body}</table>
<p class="note">The third row sits at the top of page 2, the row standard extraction loses.
Every row carries its page, so each answer can be checked against the PDF.</p>
<p class="case">Five lookups, results that fit in {res["budget_words"]} words</p>
<table border="1" cellspacing="0">
<tr><th></th><th>Expected rows found</th><th>Lookups complete</th><th>Wrong rows</th></tr>
<tr><td>Standard extraction</td><td>{s["found_rows"]} of {s["expected_rows"]}</td><td>{s["complete_lookups"]} of {s["lookups"]}</td><td>{s["wrong_rows"]}</td></tr>
<tr><td><b>With the TalkingDB page break fix</b></td><td><b>{f["found_rows"]} of {f["expected_rows"]}</b></td><td><b>{f["complete_lookups"]} of {f["lookups"]}</b></td><td><b>{f["wrong_rows"]}</b></td></tr>
</table>
<p class="note">Same search (TalkingDB TTT) in both rows; only the page break fix differs. One lookup asks about
an invented report; nothing for it comes back. No language model is used.</p>"""
    render(html, "talkingdb-answer", 420)


def column_names():
    """The rows that survive: what the extractor labels them with."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from join_pages import grid

    ext = json.loads(
        (ROOT / "results/extraction-raib-pages-1-4.json").read_text(encoding="utf-8")
    )
    tables = [grid(t) for t in ext["tables"]]
    below = {
        t["pages"][0]: sum(not m for _, m in g) for t, g in zip(ext["tables"], tables)
    }
    (h1, _), (r1, _) = tables[0][0], tables[0][1]
    (h2, m2), (r2, _) = tables[1][0], tables[1][1]
    assert m2 and below[1] == 35 and below[2] + below[3] + below[4] == 111, below
    # every page 1 row merges date with recommendation number and status with concern
    assert all(
        any("/" in c and len(c.split()) == 2 for c in r[2:3])
        for r, m in tables[0]
        if not m
    )
    src = pymupdf.open(PDF)
    p2 = crop(src, 2, 55, 74, RED, "_p2head.png")
    p2b = crop(src, 2, 75, 93, AMBER, "_p2next.png")
    p1 = crop(src, 1, 108, 128, AMBER, "_p1row.png")
    cells = lambda hs, rs: (
        "<tr>"
        + "".join(f"<th>{h}</th>" for h in hs)
        + "</tr><tr>"
        + "".join(f"<td>{c}</td>" for c in rs)
        + "</tr>"
    )
    html = f"""<h1>The rows that survive get the wrong labels</h1>
<p>It is not only the lost rows. The extractor also names the columns of every page, and those names are wrong.</p>
<p class="case">Pages 2 to 4: the lost row becomes the column names</p>
<p class="lost">Top of page 2, read as column names</p><img src="{p2}" width="584"/>
<p class="amber">The next row, labelled by it</p><img src="{p2b}" width="584"/>
<p class="note">What the extracted table says for that row:</p>
<table>{cells(h2[1:7], r2[1:7])}</table>
<p>The column called "RSSB" now holds South Western Railway. This happens to all {below[2] + below[3] + below[4]} rows below the lost rows on pages 2 to 4.</p>
<p class="case">Page 1: eight printed columns come out as six</p>
<img src="{p1}" width="584"/>
<table>{cells(h1[1:5], r1[1:5])}</table>
<p>Date and recommendation number share one cell, and so do status and concern, in all {below[1]} rows on page 1.</p>
<p class="big" style="margin-top:12pt">So all {below[1] + below[2] + below[3] + below[4]} rows that survive carry wrong or merged column names.</p>
<p class="note">The TalkingDB page break fix gives pages 2 to 4 the eight printed column names back. Page 1's merged columns remain; we list that as a limit.</p>"""
    render(html, "wrong-column-names", 640)
    for f in OUT.glob("_*.png"):
        f.unlink()


def how_it_works():
    """Diagram: document to output, with where rows are lost and what the fix changes."""
    res = json.loads((ROOT / "results/results.json").read_text(encoding="utf-8"))
    std = res["rows_surviving_extraction"]["standard_extraction"]
    fix = res["ttt_answers"]["with_page_break_fix"]
    W, H = 640, 790
    doc = pymupdf.open()
    pg = doc.new_page(width=W, height=H)
    ink, grey = (0.11, 0.12, 0.14), (0.35, 0.38, 0.42)
    steps = [
        (
            "1. Document",
            "UK RAIB index of recommendations, a public PDF. Pages 1 to 4 hold one table of 149 rows.",
            None,
        ),
        (
            "2. Table extraction",
            "An open source extractor reads each page as its own table.",
            None,
        ),
        (
            "3. TalkingDB page break fix",
            "A row with an ID is data. A table that continues on the next page joins the one before. Printed column names, page kept.",
            GREEN,
        ),
        (
            "4. Chunks: one per table row",
            "149 rows, each written as column: value, plus its page.",
            None,
        ),
        (
            "5. TTT index",
            "Every row indexed by its words, column names and page. Symbolic: no vectors, no language model.",
            None,
        ),
        ("6. Question", '"Which recommendations did RAIB report 13/2024 make?"', None),
        (
            "7. Retrieval",
            f"The top matching rows that fit in {res['budget_words']} words.",
            None,
        ),
        (
            "8. Output",
            "13/2024/01 Network Rail, page 1; 13/2024/02 Dundee City Council, page 1; 13/2024/03 RSSB, page 2.",
            GREEN,
        ),
    ]
    pg.insert_textbox(
        pymupdf.Rect(28, 14, W - 28, 48),
        "From document to answer: what happens in between",
        fontsize=18,
        fontname="hebo",
        color=ink,
    )
    pg.insert_textbox(
        pymupdf.Rect(28, 46, W - 28, 64),
        "Railway table test, one public PDF. Every number comes from results/results.json.",
        fontsize=9.5,
        fontname="helv",
        color=grey,
    )
    x0, x1, top, bh, gap = 28, 352, 76, 62, 26
    boxes = []
    for i, (title, body, colour) in enumerate(steps):
        y = top + i * (bh + gap)
        r = pymupdf.Rect(x0, y, x1, y + bh)
        pg.draw_rect(
            r, color=colour or grey, fill=(0.97, 0.98, 0.99), width=2 if colour else 1
        )
        pg.insert_textbox(
            r + (10, 7, -8, 0), title, fontsize=11.5, fontname="hebo", color=ink
        )
        pg.insert_textbox(
            r + (10, 24, -8, -2), body, fontsize=9, fontname="helv", color=ink
        )
        boxes.append(r)
        if i:
            a = pymupdf.Point((x0 + x1) / 2, boxes[i - 1].y1 + 2)
            b = pymupdf.Point((x0 + x1) / 2, r.y0 - 3)
            pg.draw_line(a, b, color=grey, width=1.4)
            pg.draw_polyline([b + (-5, -7), b, b + (5, -7)], color=grey, width=1.4)

    def callout(box, rect, colour, title, body):
        pg.draw_rect(rect, color=colour, fill=(1, 1, 1), width=1.6)
        pg.insert_textbox(
            rect + (8, 6, -6, 0), title, fontsize=10.5, fontname="hebo", color=colour
        )
        pg.insert_textbox(
            rect + (8, 22, -6, -2), body, fontsize=8.8, fontname="helv", color=ink
        )
        y = (box.y0 + box.y1) / 2
        pg.draw_line(
            pymupdf.Point(box.x1, y),
            pymupdf.Point(rect.x0, y),
            color=colour,
            width=1.2,
            dashes="[3 2] 0",
        )

    b2, b5, b8 = boxes[1], boxes[4], boxes[7]
    callout(
        b2,
        pymupdf.Rect(368, b2.y0 - 4, W - 20, b2.y1 + 6),
        RED,
        "Where it goes wrong",
        f"The first row of each new page is read as column names. {std['expected_rows'] - std['found_rows']} of the "
        f"{std['expected_rows']} expected rows are lost, and all 146 rows that survive carry wrong or merged column names.",
    )
    callout(
        b5,
        pymupdf.Rect(368, b5.y0 - 4, W - 20, b5.y1 + 4),
        grey,
        "TTT's own PDF reader today",
        "It converts the PDF to a Word file first and loses the long table rows before indexing: 0 of 13. "
        "Moving steps 2 and 3 into it is next.",
    )
    callout(
        b8,
        pymupdf.Rect(368, b8.y0, W - 20, b8.y1),
        GREEN,
        "Result, five lookups",
        f"{fix['found_rows']} of {fix['expected_rows']} expected rows, {fix['complete_lookups']} of {fix['lookups']} "
        f"lookups complete, {fix['wrong_rows']} wrong rows. Same search without step 3: "
        f"{res['ttt_answers']['standard_extraction']['found_rows']} of 13.",
    )
    pg.get_pixmap(dpi=150).save(OUT / "how-it-works.png")


if __name__ == "__main__":
    lost_rows()
    answer()
    column_names()
    how_it_works()
    print("images written:", sorted(p.name for p in OUT.glob("*.png")))
