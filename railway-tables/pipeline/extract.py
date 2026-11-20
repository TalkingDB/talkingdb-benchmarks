"""Step 1: read the tables out of a PDF with an open source table extractor.

Usage: python extract.py your.pdf tables.json [--first-page 1] [--last-page 4]

The output keeps every table cell, its row and column, the page it came from and
whether the extractor marked it as a column name. Step 2 works from this file.
"""

import argparse
import json
import time
from importlib.metadata import version
from pathlib import Path

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--first-page", type=int, default=1)
    ap.add_argument("--last-page", type=int, default=10_000)
    args = ap.parse_args()

    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.CPU, num_threads=4
    )
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.table_structure_options.do_cell_matching = True
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    start = time.perf_counter()
    result = converter.convert(args.pdf, page_range=(args.first_page, args.last_page))
    tables = [
        {
            "pages": [p.page_no for p in t.prov],
            "rows": t.data.num_rows,
            "columns": t.data.num_cols,
            "cells": [c.model_dump(mode="json") for c in t.data.table_cells],
        }
        for t in result.document.tables
    ]
    out = {
        "source": args.pdf.name,
        "page_range": [args.first_page, args.last_page],
        "extractor_version": version("docling"),
        "settings": {
            "ocr": False,
            "table_mode": "accurate",
            "match_pdf_cells": True,
            "device": "cpu",
        },
        "seconds": round(time.perf_counter() - start, 1),
        "tables": tables,
    }
    args.output.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"{len(tables)} tables from {args.pdf.name} in {out['seconds']} s")


if __name__ == "__main__":
    main()
