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
GREEN, RED = (0.05, 0.55, 0.3), (0.85, 0.1, 0.1)
X0, X1 = 362, 760  # from "Report No" to the end of "End Implementer/s"

CSS = """
body { font-family: sans-serif; color: #1b1f24; }
h1 { font-size: 22pt; margin: 0 0 6pt 0; }
p { font-size: 12pt; line-height: 1.35; margin: 0 0 8pt 0; }
.kept { color: #0d8c4d; font-weight: bold; font-size: 11pt; margin: 6pt 0 2pt 0; }
.lost { color: #d91a1a; font-weight: bold; font-size: 11pt; margin: 6pt 0 2pt 0; }
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


if __name__ == "__main__":
    lost_rows()
    answer()
    print("images written:", sorted(p.name for p in OUT.glob("*.png")))
