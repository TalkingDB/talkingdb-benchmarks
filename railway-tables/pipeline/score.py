"""Exact scoring for the rail index lookups. No language model, no judge.

A returned row counts only when it holds:
1. exactly one recommendation number, as a whole token (13/2024/030 never counts as 13/2024/03)
2. the right organisation that must act: the cell just before the source link
3. the right page: the "page N" cell every row carries
A lookup is complete when the rows found equal the expected rows, nothing extra.
The invented report fails if any row for it comes back.

Run with no arguments for the self check.
"""

import html
import re
from html.parser import HTMLParser

REC = re.compile(r"(?<![\d/])(\d{2}/\d{4}/\d+)(?![\d/])")
PAGE = re.compile(r"^page (\d+)$")
TAG = re.compile(r"<[^>]+>")


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def cells_of(result):
    """Cell lists held by one search result (a row, or a whole table)."""
    text, kind = result.get("content") or "", result.get("type")
    if kind == "table":
        p = _Rows()
        p.feed(text)
        return p.rows
    if kind in ("table_row", "table_cell"):
        return [
            [
                html.unescape(part.split(": ", 1)[-1]).strip()
                for part in text.split(" | ")
            ]
        ]
    return []


def identity(cells):
    recs = {m for c in cells for m in REC.findall(c)}
    link = next((i for i, c in enumerate(cells) if c.startswith("https://")), None)
    page = next((int(m.group(1)) for c in cells if (m := PAGE.match(c))), None)
    if len(recs) != 1 or not link or page is None:
        return None
    return recs.pop(), cells[link - 1].strip(), page


def score(case, results):
    gold = {
        (r["recommendation"], r["implementer"], r["page"])
        for r in case["expected_rows"]
    }
    rec = case.get("recommendation")
    got = {
        ident
        for res in results
        for cells in cells_of(res)
        if (ident := identity(cells))
        and ident[0].startswith(case["report"] + "/")
        and (rec is None or ident[0] == rec)
    }
    return {
        "report": case["report"],
        "expected_rows": len(gold),
        "found_rows": len(gold & got),
        "complete": got == gold,
        "missing": sorted(gold - got),
        "wrong": sorted(got - gold),
    }


def within(results, words):
    """The top results that fit in a word budget, in rank order."""
    out, used = [], 0
    for r in results:
        n = len(TAG.sub(" ", r.get("content") or "").split())
        if used + n > words:
            break
        out.append(r)
        used += n
    return out


def demo():
    case = {
        "report": "13/2024",
        "expected_rows": [
            {"recommendation": "13/2024/03", "implementer": "RSSB", "page": 2},
        ],
    }
    row = {
        "type": "table_row",
        "content": "Rec: 13/2024/03 | Who: RSSB | Link: https://x | Page: page 2",
    }
    near = dict(row, content=row["content"].replace("13/2024/03", "13/2024/030"))
    wrong_page = dict(row, content=row["content"].replace("page 2", "page 3"))
    assert score(case, [row])["complete"]
    assert not score(case, [near])["complete"], "13/2024/030 must not count"
    assert not score(case, [wrong_page])["complete"], "the page must match"
    invented = {"report": "99/1999", "expected_rows": []}
    fake = dict(row, content=row["content"].replace("13/2024/03", "99/1999/01"))
    assert (
        score(invented, [row])["complete"] and not score(invented, [fake])["complete"]
    )
    assert within([row, row], words=len(row["content"].split())) == [row]
    print("score self check ok")


if __name__ == "__main__":
    demo()
