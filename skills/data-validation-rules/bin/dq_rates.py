#!/usr/bin/env python3
# source: govalidate-lite
"""Percent-suffix vs bare-ratio split for rate-like columns. Stdlib only."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

# ASCII-only digits (`[0-9]`, not `\d`). Python's `\d` matches Unicode Nd
# (Arabic-Indic, fullwidth, Devanagari, …); JS RegExp `\d` does not. Both tiers
# use ASCII so a cell that a warehouse NUMERIC cast rejects is non-numeric in
# free rates and paid loadAnalysis alike. Cross-tier test:
# tests/unit/skill-cli/crossTierParity.test.ts
NUMBER_BODY = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
# Whitespace is ASCII-only for the same reason as the digits. Shared `\s` still
# diverges after the digit fix in exactly six code points (swept all 1,114,112
# against both engines): Python-only U+001C-U+001F and U+0085 (NEL), JS-only
# U+FEFF; both engines also match Unicode spaces (NBSP, …) that a Postgres-style
# CAST AS NUMERIC rejects. Cross-tier test:
# tests/unit/skill-cli/crossTierParity.test.ts
WS = r"[ \t\n\r\f\v]"
PCT = re.compile(rf"^{WS}*[+-]?{NUMBER_BODY}{WS}*%{WS}*$")
NUM = re.compile(rf"^{WS}*[+-]?{NUMBER_BODY}{WS}*$")
# Default column picker for this tool only ("which headers look like rates?").
# NOT the paid loadAnalysis MEASURE_NAME grain filter — different product
# question, different token list (this has discount; paid has amount/price/…).
# Do not merge the two lists to "fix" a non-bug.
RATE_NAME = re.compile(r"(rate|pct|percent|margin|discount|tax|ratio|share)", re.I)


def classify(v: str) -> str:
    if v is None or v == "":
        return "empty"
    if PCT.match(v):
        return "percent_suffix"
    if NUM.match(v):
        try:
            x = float(v)
        except ValueError:
            return "other"
        if not math.isfinite(x):
            return "other"
        if -1 <= x <= 1:
            return "bare_ratio_neg1_1"
        return "bare_outside_ratio_range"
    return "other"


def main() -> int:
    p = argparse.ArgumentParser(description="Rate column percent vs ratio profile")
    p.add_argument("file", type=Path)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--cols",
        default="",
        help="Comma-separated columns (default: name-heuristic rate-like columns)",
    )
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
        # Positional reads, not DictReader: a repeated header collapses to one
        # dict entry (last wins), so two columns named "rate" would both be
        # described as the last column's cells.
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            header = []
        if not header:
            print("error: no header", file=sys.stderr)
            return 2
        if args.cols.strip():
            requested = [c.strip() for c in args.cols.split(",") if c.strip()]
            missing = [c for c in requested if c not in header]
            if missing:
                print(f"error: unknown columns: {missing}", file=sys.stderr)
                return 2
            indexes = [
                i
                for name in requested
                for i, header_name in enumerate(header)
                if header_name == name
            ]
        else:
            indexes = [i for i, name in enumerate(header) if RATE_NAME.search(name)]
        series: list[list[str]] = [[] for _ in indexes]
        n = 0
        skipped_blank_lines = 0
        for row in reader:
            # DictReader skipped these; keep the same data_rows as dq_rows
            # and report the skip so text and JSON match the other helpers.
            if len(row) == 0:
                skipped_blank_lines += 1
                continue
            n += 1
            for slot, index in enumerate(indexes):
                series[slot].append(row[index] if index < len(row) else "")

    results = []
    for slot, index in enumerate(indexes):
        c = header[index]
        buckets = {
            "percent_suffix": 0,
            "bare_ratio_neg1_1": 0,
            "bare_outside_ratio_range": 0,
            "empty": 0,
            "other": 0,
        }
        examples = {k: [] for k in buckets}
        bare_non_integer = False
        for v in series[slot]:
            kind = classify(v)
            buckets[kind] += 1
            if len(examples[kind]) < 3 and v != "":
                examples[kind].append(v)
            if kind in ("bare_ratio_neg1_1", "bare_outside_ratio_range") and not float(v).is_integer():
                bare_non_integer = True
        # A column whose bare numbers are all whole numbers and include one
        # outside [-1,1] (a 1-5 bucket) holds integers, not ratios: its 1s are
        # counts. A column of only -1/0/1 (a 0/1 flag, or 1 meaning 100% beside
        # 50%) keeps ratio semantics. Same column-level rule as the paid tier's
        # loadAnalysis.
        if (
            buckets["bare_ratio_neg1_1"] > 0
            and buckets["bare_outside_ratio_range"] > 0
            and not bare_non_integer
        ):
            buckets["bare_outside_ratio_range"] += buckets["bare_ratio_neg1_1"]
            buckets["bare_ratio_neg1_1"] = 0
            examples["bare_outside_ratio_range"] = (
                examples["bare_ratio_neg1_1"] + examples["bare_outside_ratio_range"]
            )[:3]
            examples["bare_ratio_neg1_1"] = []
        mixed_ratio_scale = (
            buckets["percent_suffix"] > 0 and buckets["bare_ratio_neg1_1"] > 0
        )
        mixed_outside_ratio_form = (
            buckets["percent_suffix"] > 0
            and buckets["bare_outside_ratio_range"] > 0
        )
        non_numeric_form = buckets["percent_suffix"] > 0
        results.append(
            {
                "column": c,
                "counts": buckets,
                "examples": {k: v for k, v in examples.items() if v},
                "findings": {
                    "non_numeric_percent_suffix": non_numeric_form,
                    "mixed_percent_ratio_scale": mixed_ratio_scale,
                    "mixed_percent_outside_ratio_range": mixed_outside_ratio_form,
                    "note": (
                        "percent_suffix is always a type/load finding for strict float columns, "
                        "even when scale is consistent (not mixed)."
                    ),
                },
            }
        )

    out = {
        "file": str(path),
        "encoding": encoding,
        "data_rows": n,
        "skipped_blank_lines": skipped_blank_lines,
        "columns": results,
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"file: {path}  data_rows: {n}  skipped_blank_lines: {skipped_blank_lines}")
        if not results:
            print("  (no rate-like columns; pass --cols=a,b)")
        for r in results:
            c = r["counts"]
            print(f"  {r['column']}:")
            print(
                f"    percent_suffix={c['percent_suffix']} "
                f"bare_ratio_neg1_1={c['bare_ratio_neg1_1']} "
                f"bare_outside_ratio_range={c['bare_outside_ratio_range']} "
                f"other={c['other']} empty={c['empty']}"
            )
            print(
                f"    non_numeric_percent_suffix={r['findings']['non_numeric_percent_suffix']} "
                f"mixed_percent_ratio_scale={r['findings']['mixed_percent_ratio_scale']} "
                "mixed_percent_outside_ratio_range="
                f"{r['findings']['mixed_percent_outside_ratio_range']}"
            )
            if r["examples"]:
                print(f"    examples: {r['examples']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
