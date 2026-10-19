#!/usr/bin/env python3
# source: govalidate-lite
"""Run the four Free helpers once and emit one compact load-scorecard input."""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


HELPERS = ("dq_rows.py", "dq_blanks.py", "dq_grain.py", "dq_rates.py")
# The one-command path must also surface value-only grain candidates; they
# stay visibly candidates (identifier_basis "values", both semantic booleans
# false) rather than being silently absent from the scorecard.
HELPER_ARGS = {"dq_grain.py": ("--include-candidates",)}
MANUAL_REQUIRED = (
    "strict casts for columns whose intended type the values do not show",
    "at least one relevant cross-column check",
    "false-positive screen after grouping",
    "confidence and what was not checked",
    "P0 load-reject priority",
)


def validate_quote_grammar(text: str) -> None:
    """Reject quotes outside RFC-style quoted fields before csv.reader normalizes them."""
    state = "field_start"
    for offset, char in enumerate(text):
        if state == "field_start":
            if char == '"':
                state = "quoted"
            elif char not in ",\r\n":
                state = "unquoted"
        elif state == "unquoted":
            if char == '"':
                raise csv.Error(f"bare quote in unquoted field at offset {offset}")
            if char in ",\r\n":
                state = "field_start"
        elif state == "quoted":
            if char == '"':
                state = "after_quote"
        elif state == "after_quote":
            if char == '"':
                state = "quoted"
            elif char in ",\r\n":
                state = "field_start"
            else:
                raise csv.Error(
                    f"unexpected character after closing quote at offset {offset}"
                )

    if state == "quoted":
        raise csv.Error("unterminated quoted field")


def validate_strict_csv(target: Path) -> None:
    raw = target.read_bytes()
    # utf-8-sig strips a leading BOM (Excel exports) and reads plain UTF-8
    # identically, so a BOM'd quoted header is not misread as a bare quote.
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        encoding = "latin-1"

    try:
        validate_quote_grammar(text)
        with target.open(newline="", encoding=encoding) as source:
            for _row in csv.reader(source, strict=True):
                pass
    except (csv.Error, OSError, UnicodeError) as error:
        raise RuntimeError(f"strict CSV parse failed: {error}") from error


def run_helper(helper_dir: Path, name: str, target: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(helper_dir / name), str(target), "--json", *HELPER_ARGS.get(name, ())],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic"
        raise RuntimeError(f"{name} exited {result.returncode}: {detail}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{name} returned invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} returned {type(value).__name__}, expected an object")
    return value


def read_header(target: Path) -> list[str]:
    raw = target.read_bytes()
    try:
        raw.decode("utf-8")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "latin-1"
    with target.open(newline="", encoding=encoding) as source:
        reader = csv.reader(source)
        try:
            return next(reader)
        except StopIteration:
            return []


# A column's intended type is the strictest type at least this share of its
# non-blank values already passes. Below it the values do not show an intent,
# and the cast stays manual.
TYPE_EVIDENCE_SHARE = 0.8
INT_PATTERN = re.compile(r"[+-]?\d+")
FLOAT_PATTERN = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
ISO_DATE_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"
)


def _is_iso_date(value: str) -> bool:
    match = ISO_DATE_PATTERN.fullmatch(value)
    if not match:
        return False
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return False
    return True


PERCENT_PATTERN = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)\s?%")

# (intended type, evidence test, strict cast). A column shows its intended type
# when the evidence test passes on enough values; the strict cast decides which
# values fail. Numbers written as "12%" are evidence of a numeric column but
# fail the strict float cast, so a mixed percent/ratio column is still reported.
TYPE_CHECKS = (
    ("int", lambda v: INT_PATTERN.fullmatch(v) is not None,
     lambda v: INT_PATTERN.fullmatch(v) is not None),
    ("float",
     lambda v: FLOAT_PATTERN.fullmatch(v) is not None or PERCENT_PATTERN.fullmatch(v) is not None,
     lambda v: FLOAT_PATTERN.fullmatch(v) is not None),
    ("date", _is_iso_date, _is_iso_date),
)


def type_load_risks(target: Path, blank_tokens: set[str]) -> list[dict[str, Any]]:
    """Strict int/float/ISO-date casts for columns whose values show the intended type.

    Read by position, like dq_grain, so duplicated header names stay distinct.
    Empty, whitespace-only, and known blank-token cells are not cast; they are
    reported by disguised_blanks instead.
    """
    raw = target.read_bytes()
    try:
        raw.decode("utf-8")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "latin-1"
    with target.open(newline="", encoding=encoding) as source:
        reader = csv.reader(source)
        header = next(reader, [])
        rows = [row for row in reader if row]
    risks = []
    for index, name in enumerate(header):
        cells = [row[index] for row in rows if index < len(row) and row[index].strip()]
        tokens = [value for value in cells if value in blank_tokens]
        values = [value for value in cells if value not in blank_tokens]
        if not values:
            continue
        for kind, evidence, passes in TYPE_CHECKS:
            if sum(1 for value in values if evidence(value)) < TYPE_EVIDENCE_SHARE * len(values):
                continue
            failing = [value for value in values if not passes(value)]
            if failing or tokens:
                risks.append({
                    "column": name,
                    "column_index": index,
                    "intended": kind,
                    "failing": len(failing),
                    "non_blank": len(values),
                    "examples": list(dict.fromkeys(failing))[:3],
                    # A typed load rejects these too unless they are mapped to NULL first.
                    "blank_tokens": dict(Counter(tokens)),
                })
            break
    return risks


STRUCTURAL_EVIDENCE_LIMIT = 20


def is_structural_defect(row: list[str], header_width: int) -> bool:
    """A record whose width differs from the header, or a whitespace-only physical line.

    A header-width row of empty cells is data (all nulls), not a defect.
    """
    return len(row) != header_width or (len(row) == 1 and row[0] != "" and not row[0].strip())


def structural_problems(target: Path) -> dict[str, Any]:
    """Name the exact structural defects instead of refusing without evidence.

    Duplicate header names by position, and every record whose field count
    differs from the header (physical line, field count, short preview). These
    block a load verdict; they do not block saying what is wrong.
    """
    raw = target.read_bytes()
    try:
        raw.decode("utf-8")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "latin-1"
    with target.open(newline="", encoding=encoding) as source:
        reader = csv.reader(source)
        header = next(reader, [])
        width_mismatches = []
        mismatch_count = 0
        for row in reader:
            if not row:
                continue
            if is_structural_defect(row, len(header)):
                mismatch_count += 1
                if len(width_mismatches) < STRUCTURAL_EVIDENCE_LIMIT:
                    width_mismatches.append({
                        "line": reader.line_num,
                        "fields": len(row),
                        "preview": ",".join(row)[:80],
                    })
    positions: dict[str, list[int]] = {}
    for index, name in enumerate(header):
        positions.setdefault(name, []).append(index + 1)
    duplicates = {name: cols for name, cols in positions.items() if len(cols) > 1}
    text = raw.decode(encoding)
    physical_lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return {
        "physical_lines": physical_lines,
        "source_encoding": encoding,
        "header_width": len(header),
        "duplicate_header_columns": duplicates,
        "width_mismatch_count": mismatch_count,
        "width_mismatches": width_mismatches,
    }


def header_width_copy(target: Path, header_width: int) -> Path:
    """Write the header and only the header-width records to a temporary file."""
    raw = target.read_bytes()
    try:
        raw.decode("utf-8")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "latin-1"
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    )
    with target.open(newline="", encoding=encoding) as source, handle:
        writer = csv.writer(handle)
        reader = csv.reader(source)
        writer.writerow(next(reader, []))
        for row in reader:
            if row and not is_structural_defect(row, header_width):
                writer.writerow(row)
    return Path(handle.name)


def build_scorecard(target: Path) -> dict[str, Any]:
    validate_strict_csv(target)
    if not read_header(target):
        raise RuntimeError(f"empty file: {target}")
    structure = structural_problems(target)
    analysed = target
    if structure["width_mismatch_count"]:
        # Analyse only the records that match the header width, and say so.
        analysed = header_width_copy(target, structure["header_width"])
    try:
        report = _scorecard(target, analysed, structure)
    finally:
        if analysed != target:
            analysed.unlink(missing_ok=True)
    return report


def _scorecard(target: Path, analysed: Path, structure: dict[str, Any]) -> dict[str, Any]:
    helper_dir = Path(__file__).resolve().parent
    outputs = {
        name.removesuffix(".py"): run_helper(helper_dir, name, analysed) for name in HELPERS
    }
    rows = outputs["dq_rows"]
    blanks = outputs["dq_blanks"]
    grain = outputs["dq_grain"]
    rates = outputs["dq_rates"]

    data_rows = rows.get("data_rows")
    if not isinstance(data_rows, int) or data_rows < 1:
        if structure["width_mismatch_count"]:
            lines = ", ".join(str(item["line"]) for item in structure["width_mismatches"])
            raise RuntimeError(
                f"no record matches the {structure['header_width']}-field header; "
                f"{structure['width_mismatch_count']} structurally broken record(s), first at lines {lines}"
            )
        raise RuntimeError("no data rows; refusing to report a clean scorecard")

    duplicate_names = rows.get("duplicate_column_names")
    if not isinstance(duplicate_names, list):
        raise RuntimeError("row helper did not report duplicate_column_names")

    mismatches = rows.get("field_count_mismatches")
    if mismatches != 0:
        raise RuntimeError(
            f"{mismatches!r} header-width rows still differ after filtering; refusing analysis"
        )

    helper_row_counts = {
        name: output.get("data_rows")
        for name, output in outputs.items()
        if "data_rows" in output
    }
    if any(value != data_rows for value in helper_row_counts.values()):
        raise RuntimeError(f"helpers disagree on data row count: {helper_row_counts}")

    skipped_blank_lines = rows.get("skipped_blank_lines", 0)
    blank_columns = []
    for column in blanks.get("columns", []):
        if (
            column.get("empty", 0)
            or column.get("whitespace_only", 0)
            or column.get("disguised_total", 0)
        ):
            blank_columns.append(column)

    filtered = structure["width_mismatch_count"] > 0
    blocked = filtered or bool(structure["duplicate_header_columns"])
    return {
        "schema_version": 1,
        "file": str(target),
        "analysis_window": {
            "kind": "header_width_rows_only" if filtered else "full_file",
            "data_rows": data_rows,
            "excluded_records": structure["width_mismatch_count"],
        },
        "structure": {
            "load_verdict": (
                "blocked until the structural problems below are fixed" if blocked else "not blocked"
            ),
            **structure,
        },
        "parse": {
            "physical_lines": structure["physical_lines"],
            "field_count_mismatches": mismatches,
            # header_width_copy rewrites as UTF-8; report what the file was read as
            "encoding": structure["source_encoding"] if filtered else rows.get("encoding"),
            "skipped_blank_lines": skipped_blank_lines,
        },
        "header": {
            "columns": rows.get("columns"),
            "names": rows.get("header"),
            "duplicate_names": duplicate_names,
        },
        "disguised_blanks": {
            "blank_tokens": blanks.get("blank_tokens", []),
            "columns": blank_columns,
        },
        "grain": grain.get("columns", []),
        "rates": rates.get("columns", []),
        "type_load_risks": type_load_risks(analysed, set(blanks.get("blank_tokens", []))),
        "manual_required": list(MANUAL_REQUIRED),
    }


def render_structure(report: dict[str, Any]) -> list[str]:
    structure = report["structure"]
    if structure["load_verdict"] == "not blocked":
        return []
    lines = [f"STRUCTURE: load verdict {structure['load_verdict']}"]
    for name, cols in structure["duplicate_header_columns"].items():
        lines.append(
            f"  duplicate header {name!r} at columns {', '.join(map(str, cols))}; "
            "the facts below read each column by position"
        )
    if structure["width_mismatch_count"]:
        lines.append(
            f"  {structure['width_mismatch_count']} records do not have the header's "
            f"{structure['header_width']} fields; the facts below cover only the "
            f"{report['analysis_window']['data_rows']} header-width records"
        )
        for item in structure["width_mismatches"]:
            lines.append(f"    line {item['line']}: {item['fields']} fields: {item['preview']!r}")
    return lines


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"file: {report['file']}",
        *render_structure(report),
        (
            f"parse: rows={report['analysis_window']['data_rows']} "
            f"lines={report['parse']['physical_lines']} "
            f"width_mismatches={report['parse']['field_count_mismatches']} "
            f"skipped_blank_lines={report['parse'].get('skipped_blank_lines', 0)} "
            f"encoding={report['parse'].get('encoding')}"
        ),
        (
            f"header: cols={report['header']['columns']} "
            f"duplicate_names={report['header']['duplicate_names'] or 'none'}"
        ),
        "disguised_blanks:",
    ]
    blank_columns = report["disguised_blanks"]["columns"]
    if not blank_columns:
        lines.append("  none")
    for column in blank_columns:
        lines.append(
            f"  {column['column']}: empty={column['empty']} "
            f"whitespace={column['whitespace_only']} "
            f"disguised={column['disguised_total']}"
        )

    lines.append("grain:")
    if not report["grain"]:
        lines.append("  none detected")
    for column in report["grain"]:
        lines.append(
            f"  {column['column']} ({column['identifier_basis']}): "
            f"unique={column['unique']} "
            f"n_repeating={column['n_repeating_keys']} max_freq={column['max_freq']}"
        )

    lines.append("rates:")
    if not report["rates"]:
        lines.append("  none detected")
    for column in report["rates"]:
        findings = column["findings"]
        lines.append(
            f"  {column['column']}: percent_suffix="
            f"{column['counts']['percent_suffix']} "
            f"mixed_percent_ratio_scale={findings['mixed_percent_ratio_scale']} "
            "mixed_percent_outside_ratio_range="
            f"{findings['mixed_percent_outside_ratio_range']}"
        )

    lines.append("type_load_risks:")
    if not report["type_load_risks"]:
        lines.append("  none detected")
    for risk in report["type_load_risks"]:
        line = (
            f"  {risk['column']} (col {risk['column_index'] + 1}) -> {risk['intended']}: "
            f"{risk['failing']}/{risk['non_blank']} values fail a strict cast"
        )
        if risk["examples"]:
            line += "; e.g. " + ", ".join(repr(value) for value in risk["examples"])
        if risk["blank_tokens"]:
            line += "; plus blank tokens a typed load rejects unless mapped to NULL: " + ", ".join(
                f"{token} {count}" for token, count in risk["blank_tokens"].items()
            )
        lines.append(line)

    lines.append("manual_required:")
    lines.extend(f"  - {item}" for item in report["manual_required"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compose rows, blanks, grain, and rates into one Free scorecard input"
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"error: not a file: {args.file}", file=sys.stderr)
        return 2

    try:
        report = build_scorecard(args.file)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(json.dumps(report, separators=(",", ":")) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
