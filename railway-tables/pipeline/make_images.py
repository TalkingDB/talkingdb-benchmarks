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
.q { font-size: 12pt; background-color: #f3f4f6; padding: 6pt; }
.head-bad { color: #b42318; font-weight: bold; font-size: 13pt; margin: 10pt 0 3pt 0; }
.head-good { color: #0b6e4f; font-weight: bold; font-size: 13pt; margin: 10pt 0 3pt 0; }
td.ok { color: #0b6e4f; font-weight: bold; }
td.miss { color: #b42318; font-weight: bold; }
.why { color: #b42318; font-size: 9.5pt; }
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


def _box(pg, r, title, body, edge, fill=(0.97, 0.98, 0.99), width=1.2):
    pg.draw_rect(r, color=edge, fill=fill, width=width)
    assert pg.insert_textbox(r + (8, 6, -6, 0), title, fontsize=11, fontname="hebo", color=(0.11, 0.12, 0.14)) >= 0, title
    if body:
        assert pg.insert_textbox(r + (8, 24, -6, -2), body, fontsize=9.2, fontname="helv", color=(0.11, 0.12, 0.14)) >= 0, body


def _arrow(pg, a, b, colour):
    pg.draw_line(a, b, color=colour, width=1.6)
    pg.draw_polyline([b + (-7, -5), b, b + (-7, 5)], color=colour, width=1.6)


def how_it_works():
    """Two lanes, same PDF and same search: without and with the TalkingDB page break fix."""
    res = json.loads((ROOT / "results/results.json").read_text(encoding="utf-8"))
    std, fix = res["ttt_answers"]["standard_extraction"], res["ttt_answers"]["with_page_break_fix"]
    q_std, q_fix = std["lookups_detail"][0], fix["lookups_detail"][0]
    ink, grey = (0.11, 0.12, 0.14), (0.45, 0.48, 0.52)
    W, H = 940, 440
    doc = pymupdf.open()
    pg = doc.new_page(width=W, height=H)
    pg.insert_textbox(pymupdf.Rect(24, 14, W - 24, 46), "What happens between the PDF and the answer", fontsize=18, fontname="hebo", color=ink)
    pg.insert_textbox(pymupdf.Rect(24, 44, W - 24, 62), "Same PDF, same extractor, same search. The only difference is step 3.", fontsize=10, fontname="helv", color=grey)
    stages = ["1. PDF", "2. Read the tables", "3. Fix page breaks", "4. Chunks", "5. TTT search", "6. Answer"]
    x0, bw, gap = 24, 134, 18
    xs = [x0 + k * (bw + gap) for k in range(6)]
    for x, s in zip(xs, stages):
        pg.insert_textbox(pymupdf.Rect(x, 74, x + bw, 92), s, fontsize=10, fontname="hebo", color=grey)
    lanes = [
        ("Without the fix", RED, 104, [
            ("149 rows", "One table over 4 pages"),
            ("146 rows kept", "First row of each new page read as column names, so 3 rows lost and labels wrong"),
            ("No fix", ""),
            ("146 chunks", "Wrong or merged column names"),
            ("Same search", "Symbolic index, no language model"),
            (f"{q_std['found_rows']} of {q_std['expected_rows']} rows", "The RSSB row on page 2 never comes back"),
        ]),
        ("With the TalkingDB fix", GREEN, 256, [
            ("149 rows", "One table over 4 pages"),
            ("Same extraction", "Same 3 rows read as column names"),
            ("Rows put back", "A row with an ID is data; tables join across pages; printed column names"),
            ("149 chunks", "One per row, with column names and page"),
            ("Same search", "Symbolic index, no language model"),
            (f"{q_fix['found_rows']} of {q_fix['expected_rows']} rows", "Including RSSB on page 2, each with its page"),
        ]),
    ]
    for name, colour, top, boxes in lanes:
        assert pg.insert_textbox(pymupdf.Rect(x0, top, W - 24, top + 24), name, fontsize=12, fontname="hebo", color=colour) >= 0
        y0, y1 = top + 26, top + 126
        for k, (t, body) in enumerate(boxes):
            r = pymupdf.Rect(xs[k], y0, xs[k] + bw, y1)
            skipped = t == "No fix"
            edge = grey if skipped else (colour if k in (2, 5) or (k == 1 and colour == RED) else grey)
            fill = (0.95, 0.95, 0.96) if skipped else ((0.99, 0.94, 0.94) if edge == RED else ((0.93, 0.98, 0.95) if edge == GREEN else (0.97, 0.98, 0.99)))
            _box(pg, r, t, body, edge, fill, 2 if edge != grey else 1.1)
            if k:
                _arrow(pg, pymupdf.Point(xs[k - 1] + bw + 2, (y0 + y1) / 2), pymupdf.Point(xs[k] - 3, (y0 + y1) / 2), grey)
    q = q_fix["question"]
    pg.insert_textbox(pymupdf.Rect(x0, 396, W - 24, 414), f"Question asked in both lanes: \"{q}\"", fontsize=9.5, fontname="helv", color=ink)
    pg.insert_textbox(pymupdf.Rect(x0, 413, W - 24, 432),
                      f"All five lookups: {std['found_rows']} of {std['expected_rows']} rows without the fix, {fix['found_rows']} of {fix['expected_rows']} with it, {fix['wrong_rows']} wrong rows. TTT's own PDF reader loses these rows today, so step 2 uses an open source extractor.",
                      fontsize=9, fontname="helv", color=grey)
    pg.get_pixmap(dpi=150).save(OUT / "how-it-works.png")


def query_compare():
    """The same plain English question, without and with the fix: what comes back for report 13/2024."""
    res = json.loads((ROOT / "results/results.json").read_text(encoding="utf-8"))
    budget = res["budget_words"]
    expected = json.loads((ROOT / "cases/raib-lookups.json").read_text(encoding="utf-8"))[0]["expected_rows"]

    def got(variant):
        case = res["ttt_answers"][variant]["lookups_detail"][0]
        rows = [i for r in case["results"] for cells in cells_of(r) if (i := identity(cells))]
        return case["question"], rows

    question, std_rows = got("standard_extraction")
    _, fix_rows = got("with_page_break_fix")
    std_ids = {(a, b, c) for a, b, c in std_rows}
    fix_ids = {(a, b, c) for a, b, c in fix_rows}
    gold = [(e["recommendation"], e["implementer"], e["page"]) for e in expected]
    assert len([g for g in gold if g in std_ids]) == 2 and all(g in fix_ids for g in gold)

    def column(title, ids, ok_class):
        rows = ""
        for rec, who, page in gold:
            hit = (rec, who, page) in ids
            mark = "&#10003;" if hit else "&#10007;"
            cls = "ok" if hit else "miss"
            note = "" if hit else "<br/><span class='why'>Missing: read as column names</span>"
            rows += f"<tr><td class='{cls}'>{mark}</td><td>{rec}</td><td>{who}{note}</td><td>page {page}</td></tr>"
        n = sum((g in ids) for g in gold)
        return (f"<p class='{ok_class}'>{title}: {n} of {len(gold)} rows</p>"
                f"<table><tr><th></th><th>Recommendation</th><th>Who must act</th><th>Page</th></tr>{rows}</table>")

    html = f"""<h1>Same question, without and with the fix</h1>
<p class="q"><b>Question:</b> {question}</p>
{column("Without the fix", std_ids, "head-bad")}
{column("With the TalkingDB fix", fix_ids, "head-good")}
<p class="note">What TTT returned within {budget} words, rows for report 13/2024. The other results were rows from other reports.
Same PDF, same extractor, same search in both. No language model.</p>"""
    render(html.replace("class='ok'", "class='ok'"), "query-fails-and-succeeds", 470)


if __name__ == "__main__":
    lost_rows()
    answer()
    column_names()
    how_it_works()
    query_compare()
    print("images written:", sorted(p.name for p in OUT.glob("*.png")))
