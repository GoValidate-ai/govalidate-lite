#!/usr/bin/env python3
# source: govalidate-lite
"""Parsed row count vs physical lines. Stdlib only. Read-only."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _whitespace_only_row(row: list[str]) -> bool:
    """True when every cell is blank and at least one cell is whitespace."""
    saw_whitespace = False
    for cell in row:
        if cell == "":
            continue
        if cell.strip() != "":
            return False
        saw_whitespace = True
    return saw_whitespace


def main() -> int:
    p = argparse.ArgumentParser(description="CSV parse integrity: rows vs lines")
    p.add_argument("file", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    path: Path = args.file
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2

    raw = path.read_bytes()
    # Prefer utf-8; fall back to latin-1 so byte count still works.
    # utf-8-sig strips a leading BOM (Excel exports) and reads plain UTF-8
    # identically, so the first column name stays clean.
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        encoding = "latin-1"

    physical_lines = text.count("\n")
    if text and not text.endswith("\n"):
        physical_lines += 1

    with path.open(newline="", encoding=encoding) as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            out = {
                "file": str(path),
                "encoding": encoding,
                "header": None,
                "data_rows": 0,
                "physical_lines": physical_lines,
                "field_count_mismatches": 0,
                "skipped_blank_lines": 0,
                "duplicate_column_names": [],
            }
            print(json.dumps(out, indent=2) if args.json else "empty file")
            return 0

        col_count = len(header)
        dup_names = sorted({n for n in header if header.count(n) > 1})
        mismatches = 0
        data_rows = 0
        skipped_blank_lines = 0
        for row in reader:
            # A truly empty physical line (csv yields []) is not a record.
            # A whitespace-only row is still a record, and it is a mismatch
            # even when a one-column header makes the field count match:
            # "   " is not a key. Empty cells ("") are records, not mismatches.
            if len(row) == 0:
                skipped_blank_lines += 1
                continue
            data_rows += 1
            if len(row) != col_count or _whitespace_only_row(row):
                mismatches += 1

    out = {
        "file": str(path),
        "encoding": encoding,
        "columns": col_count,
        "header": header,
        "duplicate_column_names": dup_names,
        "data_rows": data_rows,
        "physical_lines": physical_lines,
        "field_count_mismatches": mismatches,
        "skipped_blank_lines": skipped_blank_lines,
        "note": "Use data_rows as denominator. physical_lines can exceed rows+header when fields contain newlines.",
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"file: {path}")
        print(f"encoding: {encoding}")
        print(f"columns: {col_count}")
        print(f"data_rows (parsed): {data_rows}")
        print(f"physical_lines: {physical_lines}")
        print(f"field_count_mismatches: {mismatches}")
        print(f"skipped_blank_lines: {skipped_blank_lines}")
        if dup_names:
            print(f"duplicate_column_names: {dup_names}")
        else:
            print("duplicate_column_names: none")
        print("denominator: data_rows (real CSV parse, not line count)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
