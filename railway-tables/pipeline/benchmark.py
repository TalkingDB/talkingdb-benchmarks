"""Reproduce the rail index result: five lookups on pages 1 to 4, 13 expected rows.

Part 1, plain Python: how many of the 13 expected rows survive table extraction,
without and with the TalkingDB page break fix.
Part 2, needs TTT (see setup.sh): the five questions asked through TTT without and
with the fix, scored on the results that fit in 300 words.

Usage: python benchmark.py         Part 1
       python benchmark.py --ttt   Parts 1 and 2, writes results/results.json
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from join_pages import tables  # noqa: E402
from score import score, within  # noqa: E402

# The eight column names printed on the index. Page 1 comes out of extraction with
# six merged columns, so its rows keep their cells in order under these names.
COLUMNS = [
    "Report Title",
    "Report No",
    "Event Date",
    "Recommendation No",
    "Recommendation Status",
    "RAIB Concern",
    "End Implementer/s",
    "Recommendation status report",
]
BUDGET_WORDS = 300
VARIANTS = (("standard_extraction", False), ("with_page_break_fix", True))


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def total(per_case):
    return {
        "found_rows": sum(c["found_rows"] for c in per_case),
        "expected_rows": sum(c["expected_rows"] for c in per_case),
        "complete_lookups": sum(c["complete"] for c in per_case),
        "lookups": len(per_case),
        "wrong_rows": sum(len(c["wrong"]) for c in per_case),
    }


def rows_as_results(row_tables):
    return [
        {"type": "table_row", "content": " | ".join(r["cells"] + [f"page {r['page']}"])}
        for t in row_tables
        for r in t
    ]


def part1(extracted, cases):
    out = {}
    for name, fix in VARIANTS:
        kept = rows_as_results(tables(extracted, fix=fix))
        out[name] = total([score(c, kept) for c in cases])
    return out


def part2(extracted, cases):
    from ask import ask, index  # needs the TTT environment

    out = {}
    for name, fix in VARIANTS:
        gid = index(
            tables(extracted, fix=fix),
            COLUMNS,
            "Index of RAIB recommendations, pages 1 to 4",
        )
        per_case = []
        for c in cases:
            shown = within(ask(gid, c["question"], top=10), BUDGET_WORDS)
            per_case.append(
                {**score(c, shown), "question": c["question"], "results": shown}
            )
        out[name] = {**total(per_case), "lookups_detail": per_case}
    return out


def main():
    extracted, cases = (
        load("results/extraction-raib-pages-1-4.json"),
        load("cases/raib-lookups.json"),
    )
    p1 = part1(extracted, cases)
    assert p1["standard_extraction"]["found_rows"] == 10, (
        p1
    )  # recorded result, see README
    assert (
        p1["with_page_break_fix"]["found_rows"] == 13
        and p1["with_page_break_fix"]["wrong_rows"] == 0
    ), p1
    print("Part 1, rows that survive extraction:", json.dumps(p1, indent=2))
    if "--ttt" not in sys.argv:
        return
    p2 = part2(extracted, cases)
    print(
        "Part 2, TTT at",
        BUDGET_WORDS,
        "words:",
        json.dumps(
            {k: {x: v[x] for x in v if x != "lookups_detail"} for k, v in p2.items()},
            indent=2,
        ),
    )
    out = {
        "document": "documents/raib-recommendations-index.pdf, pages 1 to 4",
        "budget_words": BUDGET_WORDS,
        "rows_surviving_extraction": p1,
        "ttt_answers": p2,
    }
    (ROOT / "results/results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
