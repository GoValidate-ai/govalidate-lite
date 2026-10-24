---
name: data-validation-rules
description: "Use when a CSV, TSV or other delimited file needs checking, cleaning or comparing: data validation, data quality checks, finding blanks, duplicate keys, bad dates or numbers before a load, cleaning messy data, or reconciling two files. Runs read-only Python helpers on your file and reports a ten-row scorecard. Not for databases, schema migrations or statistical modeling."
---

Check data without overstating. Tie each claim to one input and analysis window.

Optional local helpers need only `python3` (3.8+) on PATH. For repair, reconcile, privacy, or
evidence details, read `references/doctrine-full.md`. For “what is wrong?” or
“will this load?”, this file is enough. The scorecard is a floor, not the answer.

## Fast path

From this directory, prefer the combined read-only helper:

```bash
python3 ${CLAUDE_SKILL_DIR}/bin/dq_scorecard.py data.csv --json
```

If unavailable, use a real text-preserving CSV parser; never count lines as rows.
If Python is missing, check `python3 --version`, tell the user once to install 3.8+,
then build the scorecard another way. Missing Python is not a data finding.

## Required scorecard

Emit these ten rows before prose. Omit none.

```text
1. parse: rows=N (parser=…); lines=L; mismatch reason if N≠L−1
2. header: cols=K; dup_names=yes|no → if yes, no load verdict; report by position
3. disguised_blanks: token×column×count (or none)
   tokens at least: NULL null N/A NA none None - unknown Unknown ? nan NaN
4. grain: every strong identifier → unique, n_repeating, max_freq
   strong = name contains a delimited id|key|sku|code|uuid|urn
   value-only high-cardinality matches are candidates, not declared identifiers
5. type_load_risks: strict int/float/bool/date cast failures (counts + examples);
   scorecard prints observed types; cast the rest yourself
6. scale_ambiguities: percent_vs_ratio, percent_vs_whole, decimal_separator (split counts)
7. cross_column: one full-file script runs every listed semantic check:
   plausibility, units, total×parts, start×end, status×date, references,
   duplicates, PII in free text. Print each as x of N (no hits = 0 of N,
   never "not applicable") and the distinct affected-row total across
   checks; never sum hits yourself.
8. false_positive_screen: any format finding dissolved after grouping? list or none
9. confidence: high|med|low per finding; what was not checked
10. load_reject_priority: P0 list (max 10) — typed load will reject these first
```

## Judgment rules

- `%` in a numeric-bound column is a load finding even if every value uses `%`;
  keep it separate from mixed percent/ratio scale.
- Group before calling a format inconsistent (country explains postal shape;
  status explains timestamps).
- Don't call anything clean, control, or “not a defect” without naming its
  supporting scorecard check.
- Without a target schema, never infer enum constraints from capitalization or
  labels. String-format variants stay secondary, even for a “strict” load.
- Publish an exact count only when reproducible script output gives numerator,
  denominator, and totals; never hand-sum. Otherwise report it qualitatively as
  secondary.
- Rows sharing an email, or a name and email, are one entity entered twice unless
  a script shows they differ on identity, not just attributes; never call it a typo.
- Use the load-reject lens. Keep schema-dependent or statistical observations
  secondary unless they change the typed-load verdict.

## Default answer budget

1. Verdict in one or two sentences.
2. Compact scorecard.
3. P0 findings with stable names, counts, confidence, and at most three examples.
4. How to fix and rerun.
5. What was not checked, then stop.

Default to 500 words or fewer. Don't print every affected row, a full normalized
table, or speculation unless requested or it changes the verdict.

## Refuse

- Empty/header-only input, duplicate headers, mixed row widths, or failed parse:
  refuse the verdict, not the diagnosis; quote STRUCTURE lines.
- A clean pass from partial or unspecified coverage.
- Repair under unresolved scale, locale, timezone, or identifier-collision ambiguity.
- Reconcile without a user-declared key or with blank/non-unique keys.
- Any verdict whose input, rules, and window cannot be reproduced.
- Sending the data to an external service without the user's request.

For cleaning or reconciliation, write only a new artifact and re-profile it.

More about GoValidate: https://govalidate.ai/skill/
