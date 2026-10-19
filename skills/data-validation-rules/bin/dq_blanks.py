#!/usr/bin/env python3
# source: govalidate-lite
"""Empty cells and disguised blank tokens by column. Stdlib only. Read-only."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

# Same members as paid loadAnalysis.BLANK_TOKENS. Cross-tier test pins set
# equality (tests/unit/skill-cli/crossTierParity.test.ts); edit both sides.
BLANK_TOKENS = {
    "NULL",
    "null",
    "N/A",
    "n/a",
    "NA",
    "na",
    "none",
    "None",
    "NONE",
    "-",
    "unknown",
    "Unknown",
    "UNKNOWN",
    "?",
    "nan",
    "NaN",
    "NAN",
    "undefined",
    "UNDEFINED",
}


def main() -> int:
    p = argparse.ArgumentParser(description="Disguised and true blanks by column")
    p.add_argument("file", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    path: Path = args.file
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2

    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
        # utf-8-sig strips a leading BOM (Excel exports) and reads plain
        # UTF-8 identically, so the first column name stays clean.
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "latin-1"

    with path.open(newline="", encoding=encoding) as f:
        # Positional reads, not DictReader: with duplicated headers a dict
        # collapses same-named columns into one entry (last wins), while
        # dq_grain keys series by position. Read by index like dq_grain so
        # the two helpers describe the same cells.
        reader = csv.reader(f)
        try:
            cols = next(reader)
        except StopIteration:
            cols = []
        if not cols:
            print("error: no header", file=sys.stderr)
            return 2
        empty = [0] * len(cols)
        disguised: list[Counter] = [Counter() for _ in cols]
        whitespace_only = [0] * len(cols)
        n = 0
        skipped_blank_lines = 0
        for row in reader:
            # Not a record; dq_rows and dq_grain skip these too.
            if len(row) == 0:
                skipped_blank_lines += 1
                continue
            n += 1
            for i in range(len(cols)):
                v = row[i] if i < len(row) else ""
                if v == "":
                    empty[i] += 1
                elif v.strip() == "":
                    whitespace_only[i] += 1
                elif v.strip() in BLANK_TOKENS or v in BLANK_TOKENS:
                    disguised[i][v] += 1

    columns = []
    for i, c in enumerate(cols):
        d = dict(disguised[i])
        entry = {
            "column": c,
            "empty": empty[i],
            "whitespace_only": whitespace_only[i],
            "disguised": d,
            "disguised_total": sum(d.values()),
            "naive_nonblank": n - empty[i],
            "effective_blank": empty[i]
            + whitespace_only[i]
            + sum(d.values()),
        }
        columns.append(entry)

    out = {
        "file": str(path),
        "encoding": encoding,
        "data_rows": n,
        "skipped_blank_lines": skipped_blank_lines,
        "blank_tokens": sorted(BLANK_TOKENS),
        "columns": columns,
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"file: {path}  data_rows: {n}  skipped_blank_lines: {skipped_blank_lines}")
        print(f"blank_tokens: {sorted(BLANK_TOKENS)}")
        any_hit = False
        for e in columns:
            if e["empty"] or e["whitespace_only"] or e["disguised_total"]:
                any_hit = True
                print(
                    f"  {e['column']}: empty={e['empty']} "
                    f"ws_only={e['whitespace_only']} "
                    f"disguised={e['disguised']} "
                    f"naive_nonblank={e['naive_nonblank']} "
                    f"effective_blank={e['effective_blank']}"
                )
        if not any_hit:
            print("  (no empty, whitespace-only, or disguised blanks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
