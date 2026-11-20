"""Step 2: the TalkingDB page break fix.

Table extractors often mark the first row of each new page as column names, so that
row drops out of the table. Here a row counts as data whenever one of its cells holds
a row ID (you describe the ID with a pattern; for the rail index it is a
recommendation number such as 13/2024/03). A table on the next page joins the one
before it when its first row is data. Every row keeps the page it came from.

Run with no arguments for the self check.
"""

import json
import re
import sys
from pathlib import Path

RAIB_ROW_ID = r"(?<![\d/])\d{2}/\d{4}/\d+(?![\d/])"


def grid(table):
    """Rows of one extracted table as (cells, marked_as_column_names)."""
    cells, marked = {}, {}
    for c in table["cells"]:
        r = c["start_row_offset_idx"]
        cells.setdefault(r, {})[c["start_col_offset_idx"]] = c["text"].strip()
        marked[r] = marked.get(r, False) or bool(c.get("column_header"))
    return [
        ([cells[r].get(i, "") for i in range(table["columns"])], marked[r])
        for r in sorted(cells)
    ]


def tables(extracted, row_id=RAIB_ROW_ID, fix=True):
    """Tables as lists of {"page", "cells"} rows.

    fix=False is what the extractor gives: rows it marked as column names are gone
    and every page is its own table. fix=True keeps every row with an ID and joins
    a next page table that starts with data.
    """
    rid = re.compile(row_id)
    out, last_page = [], -1
    for t in extracted["tables"]:
        page, rows = t["pages"][0], []
        g = grid(t)
        for cells, marked in g:
            if any(rid.search(c) for c in cells) and (fix or not marked):
                rows.append({"page": page, "cells": cells})
        starts_with_data = bool(g) and any(rid.search(c) for c in g[0][0])
        # ponytail: joins on page adjacency and an ID in the first row only; a different
        # table with the same ID format starting on the next page would be joined too.
        if fix and out and starts_with_data and page == last_page + 1:
            out[-1].extend(rows)
        else:
            out.append(rows)
        last_page = t["pages"][-1]
    return [rows for rows in out if rows]


def demo():
    here = Path(__file__).resolve().parent.parent
    extracted = json.loads(
        (here / "results/extraction-raib-pages-1-4.json").read_text(encoding="utf-8")
    )
    before, after = tables(extracted, fix=False), tables(extracted)
    rid = re.compile(RAIB_ROW_ID)
    first_rows = lambda ts: {  # (row ID, page) of every kept row
        (m.group(0), r["page"])
        for t in ts
        for r in t
        if (m := rid.search(" ".join(r["cells"])))
    }
    assert len(before) == 4 and len(after) == 1, (len(before), len(after))
    # the first row of pages 2, 3 and 4 is what the extractor turned into column names
    gained = first_rows(after) - first_rows(before)
    assert gained == {("13/2024/03", 2), ("01/2024/04", 3), ("07/2023/04", 4)}, gained
    print(
        "join_pages self check ok:",
        sum(map(len, before)),
        "rows before,",
        sum(map(len, after)),
        "after",
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        demo()
    else:
        ex = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        joined = tables(ex, sys.argv[2] if len(sys.argv) > 2 else RAIB_ROW_ID)
        print(json.dumps(joined, indent=2))
