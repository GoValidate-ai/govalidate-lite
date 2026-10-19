#!/usr/bin/env python3
# source: govalidate-lite
"""Grain table for header-declared identifiers. Stdlib only."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ID_NAME = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:id|key|sku|code|uuid|urn)(?:[^A-Za-z0-9]|$)",
    re.I,
)


def _blank_cell(value: str) -> bool:
    """Empty and whitespace-only cells are not keys. dq_rows says so too."""
    return value.strip() == ""


def name_boundaries(name: str) -> str:
    # camelCase seams count as token boundaries (orderId, OrderID, itemSku),
    # without reviving the substring false positives (grid, valid, paid).
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)


def identifier_basis(name: str, vals: list[str], n: int) -> str | None:
    if ID_NAME.search(name_boundaries(name or "")):
        return "name"
    if n == 0:
        return None
    non_empty = [v for v in vals if not _blank_cell(v)]
    if not non_empty:
        return None
    distinct = len(set(non_empty))
    # High uniqueness is a review candidate, not an identifier declaration.
    # Deliberately no MEASURE_NAME / SKIP_GRAIN_NAME filters here: #607 reserves
    # id_like / is_unique_key for header-declared names; value-path columns stay
    # opt-in via --include-candidates with identifier_basis "values". Porting
    # the paid tier's value-path filters would silently undo that tiering.
    if distinct >= max(2, int(0.8 * len(non_empty))):
        avg_len = sum(len(v) for v in non_empty) / len(non_empty)
        if avg_len <= 64:
            return "values"
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Identifier grain / frequency table")
    p.add_argument("file", type=Path)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--include-candidates",
        action="store_true",
        help="Also report high-uniqueness value-only identifier candidates",
    )
    p.add_argument(
        "--all-columns",
        action="store_true",
        help="Report grain for every column",
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
        reader = csv.reader(f)
        try:
            cols = next(reader)
        except StopIteration:
            cols = []
        if not cols:
            print("error: no header", file=sys.stderr)
            return 2
        # Keyed by position, not name: a duplicated header must not merge two
        # columns' values into one self-contradictory grain entry.
        duplicated_names = {name for name in cols if cols.count(name) > 1}
        series: list[list[str]] = [[] for _ in cols]
        n = 0
        skipped_blank_lines = 0
        for row in reader:
            # Truly empty physical lines are not records (csv yields []).
            # They are counted separately so helpers agree on data_rows.
            # A whitespace-only cell is not a key (same as ""). The row stays
            # a record; dq_rows counts it as a mismatch so the scorecard refuses.
            if len(row) == 0:
                skipped_blank_lines += 1
                continue
            n += 1
            for i in range(len(cols)):
                series[i].append(row[i] if i < len(row) else "")

    grains = []
    for i, c in enumerate(cols):
        vals = series[i]
        basis = identifier_basis(c, vals, n)
        if (
            not args.all_columns
            and basis != "name"
            and not (args.include_candidates and basis == "values")
        ):
            continue
        ctr = Counter(vals)
        # frequencies among real keys; whitespace-only cells count as blank
        non_empty = {k: v for k, v in ctr.items() if not _blank_cell(k)}
        unique = len(non_empty)
        repeating = {k: v for k, v in non_empty.items() if v > 1}
        n_repeating = len(repeating)
        max_freq = max(repeating.values()) if repeating else (1 if non_empty else 0)
        freq_of_freq = Counter(repeating.values())
        top = sorted(repeating.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        grains.append(
            {
                "column": c,
                # A value pattern can nominate a review candidate, but only a
                # declared identifier header supplies identifier semantics.
                "id_like": basis == "name",
                "identifier_basis": basis,
                "non_empty": sum(1 for v in vals if not _blank_cell(v)),
                "unique": unique,
                "n_repeating_keys": n_repeating,
                "max_freq": max_freq,
                "freq_histogram": {str(k): v for k, v in sorted(freq_of_freq.items())},
                "top_repeating": [{"value": a, "count": b} for a, b in top],
                "is_unique_key": (
                    basis == "name"
                    and c not in duplicated_names
                    and unique == n
                    and n > 0
                    and not any(_blank_cell(value) for value in ctr)
                ),
            }
        )

    out = {
        "file": str(path),
        "encoding": encoding,
        "data_rows": n,
        "skipped_blank_lines": skipped_blank_lines,
        "columns": grains,
        "note": (
            "Default reports header-declared identifiers. "
            "Use --include-candidates for high-uniqueness value-only candidates."
        ),
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"file: {path}  data_rows: {n}  skipped_blank_lines: {skipped_blank_lines}")
        if not grains:
            print("  (no header-declared identifiers; try --include-candidates)")
        for g in grains:
            print(
                f"  {g['column']} ({g['identifier_basis'] or 'all-columns'}): "
                f"unique={g['unique']}/{n} "
                f"n_repeating={g['n_repeating_keys']} max_freq={g['max_freq']} "
                f"unique_key={g['is_unique_key']}"
            )
            if g["top_repeating"]:
                ex = ", ".join(f"{t['value']!r}×{t['count']}" for t in g["top_repeating"][:3])
                print(f"    top: {ex}")
            if g["freq_histogram"]:
                print(f"    freq_histogram: {g['freq_histogram']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
