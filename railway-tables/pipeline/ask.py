"""Step 3: index table rows in TalkingDB TTT and ask questions in plain English.

Usage: python ask.py tables.json "your question" [--row-id PATTERN] [--columns "A,B,C"]

Every row is indexed with its column names and the page it came from, so you can
check each answer against the PDF. No language model is used anywhere.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="ttt-"))
os.environ["GRAPH_DB"] = str(WORK / "graphs.db")
os.environ.setdefault("CLIENT_MODE", "direct")
os.environ.setdefault("CE_DOCX_PAGINATE", "0")

import docx  # noqa: E402
from starlette.datastructures import UploadFile  # noqa: E402
from talkingdb.clients.sqlite import GRAPH_DB, sqlite_conn  # noqa: E402
from talkingdb.helpers.client import config as ce_config  # noqa: E402
from talkingdb.models.document.document import DocumentModel  # noqa: E402
from talkingdb.models.document.indexes.index import FileIndexModel  # noqa: E402
from talkingdb.models.graph.graph import GraphModel  # noqa: E402
from talkingdb_ce.client import CEClient  # noqa: E402
from app.services.extractor import ExtractorService  # noqa: E402
from app.services.indexer import IndexerService  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from join_pages import RAIB_ROW_ID, tables  # noqa: E402

with sqlite_conn(GRAPH_DB) as _conn:
    GraphModel.init_db(_conn)


def index(row_tables, columns, title):
    """Write the rows as Word tables (TTT's document path) and index them. Returns the graph id."""
    path = WORK / f"{len(list(WORK.glob('*.docx')))}.docx"
    d = docx.Document()
    d.add_heading(title, level=1)
    for rows in row_tables:
        width = max(len(r["cells"]) for r in rows)
        # ponytail: rows narrower than the widest keep their cells in order, so their
        # column names may not line up; pass --columns for the widest layout.
        names = (columns + [f"Column {i + 1}" for i in range(len(columns), width)])[
            :width
        ]
        t = d.add_table(rows=len(rows) + 1, cols=width + 1)
        for j, name in enumerate(names + ["Page"]):
            t.cell(0, j).text = name
        for i, r in enumerate(rows, 1):
            for j, value in enumerate(r["cells"]):
                t.cell(i, j).text = value
            t.cell(i, width).text = f"page {r['page']}"
        d.add_paragraph("")
    d.save(path)
    with open(path, "rb") as fh:
        parsed = asyncio.run(
            CEClient(ce_config).parse_file(file=UploadFile(filename=path.name, file=fh))
        )
    ix = IndexerService()
    ix.graph_file_index(FileIndexModel(**parsed["file_index"]))
    ix.index_document(DocumentModel.from_dict(parsed["document"]))
    return ix.gm.graph_id


def ask(graph_id, question, top=10):
    results = ExtractorService([graph_id], max_matches=top).extract(query=question)[
        "elements"
    ]
    return [{"type": r["type"], "content": r["content"]} for r in results]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tables", type=Path, help="output of extract.py")
    ap.add_argument("question")
    ap.add_argument(
        "--row-id", default=RAIB_ROW_ID, help="regular expression for a row ID"
    )
    ap.add_argument("--columns", default="", help="column names, comma separated")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    extracted = json.loads(args.tables.read_text(encoding="utf-8"))
    columns = [c.strip() for c in args.columns.split(",") if c.strip()]
    gid = index(
        tables(extracted, args.row_id), columns, extracted.get("source", "document")
    )
    for i, r in enumerate(ask(gid, args.question, args.top), 1):
        print(f"{i}. [{r['type']}] {r['content'][:400]}")


if __name__ == "__main__":
    main()
