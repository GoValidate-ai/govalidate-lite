<!-- source: govalidate-lite -->
---
name: data-validation-rules
description: Use when checking, cleaning, or comparing a data file and the answer has to hold up — profiling a dataset for quality problems, repairing columns, or reconciling two files to find missing rows and changed values. Gives the procedure and the judgement, not a tool: follow it with whatever you already have (pandas, DuckDB, SQL, awk). Reach for it when asked what is wrong with a dataset, whether an export matches its source, whether a fix actually worked, or before loading a file into anything that matters. Not for schema migrations, statistical modelling, or querying databases.
version: 0.9.0
user-invocable: true
argument-hint: "[profile|clean|reconcile|report] [target]"
---

How to check data so the answer survives being questioned.

This skill carries no tool. It gives you the order to do things in, and the
judgement calls at each step. Follow it with whatever you already have.

## The one idea

**The failure mode of data work is not a crash. It is a confident wrong number.**

A crash tells you it failed. A reconciliation run on the wrong key returns a clean,
specific, plausible answer, and nobody checks a clean-looking result. Every
procedure below is ordered to make that outcome impossible rather than unlikely.

The test for anything you are about to report: **would it come out the same way
twice?** Know what you would need to re-run to get the identical result — the exact
input, the exact rules, the exact declarations. If you cannot state that, you have
an impression, not a finding.

Two limits that travel with every claim:

- **Determinism is relative to a rule version.** Change the rules and findings
  change, correctly. Say which version produced a finding.
- **Floating-point statistics vary by engine.** Same data, different runtime, last
  digits differ. Do not claim identical numbers across languages you have not
  actually compared.

---

## Step 0 — always, before anything else

**Do this, in order:**

1. **Read the header before the data.** Get the column names and count.
2. **Check for duplicate column names.** If any name repeats, stop. Columns are
   selected by name, so a repeated name has no unambiguous meaning and every
   name-based result you produce will be arbitrary. Ask which one they mean.
3. **Count rows with a real parser, never by counting lines.** A quoted field can
   contain the delimiter and can contain a newline, so line count is not row count
   and splitting on commas is not parsing. Get this wrong and you have a wrong
   denominator under every ratio in the report, plus a batch of invented findings
   about "malformed" rows that are perfectly well formed. Verify by checking that
   every parsed row has the same field count as the header.
4. **Establish how much you actually read.** Full file, or a sample? If a sample,
   seed it so it is repeatable, and record the row count you saw. **Then use that
   one window for every number in the report.** A severity computed from 50,000
   sampled rows next to a non-blank count taken from the full file produces fields
   that describe different populations — each number defensible alone, the report
   unreadable as a whole.
5. **Refuse a header with no data rows.** A header alone cannot support a verdict,
   and reporting "no findings" for one reads as a pass. This is the shape a
   truncated export and a misidentified file both arrive in.
6. **Note what parsing did to the values.** Did `007` become `7`? Did a leading-zero
   postal code become an integer? Did a date string become a timestamp? If so, every
   finding from here describes your parse, not their data.

**Watch out for:** a file that parses without error and still parsed wrong.
Delimiter and encoding guesses fail silently.

---

## When you are asked "what is wrong with this file?"

**Do this, in order:**

1. Complete step 0.
2. For each column, establish: how many values are non-blank, what type they
   appear to be, and how many distinct values there are.
3. **Find the blanks that are disguised as values.** `NULL`, `null`, `N/A`, `NA`,
   `none`, `-`, `unknown`, `?` are blanks someone typed. Count them as blanks or
   your blank ratio is understated and a column reported as fully populated is not.
   They also break type inference: one `N/A` makes a numeric column non-numeric, and
   whatever consumes it downstream will either crash or coerce silently.
4. **Identify the grain before anything else uses it.** Which column, if any, is
   unique across all rows? A column that looks like an identifier and repeats tells
   you what a row actually is — if a quarter of the order IDs appear twice, the
   grain is line-items and not orders, and anyone who later joins on it gets
   fan-out. Report how many identifiers repeat *and* how often, because "29 IDs
   appear twice" and "one ID appears 29 times" are different files.
5. Flag the problems you can name — blanks above what the column implies, mixed
   types, mixed date formats, mixed casing, stray whitespace, control characters,
   values that look like identifiers with inconsistent prefixes or leading zeros,
   numbers carrying currency symbols or thousands separators, likely personal data.
6. **Then check the columns against each other** — see below. This is not optional
   polish; per-column analysis alone produces false positives and false negatives at
   the same time.
7. **Give every finding a stable name** you would use again next week for the same
   problem. `mixed_date_formats` beats "date issues." A name you reuse is a name
   someone can search, count, and hold you to.
8. Attach to each finding: the column, the affected count, the total, and a handful
   of offending values. Not a dump.
9. **Say what you did not check** — the rows beyond your sample, the columns you
   skipped, the checks you do not have.

### Columns do not validate alone

**A per-column check can be wrong in both directions at once**, and this is the most
common way a careful-looking profile misleads.

A real example. A `postal_code` column shows eight different shapes across 164 rows.
Per-column, that reads as "mixed formats" — a finding you would report, and it would
be **wrong**, because the file covers six countries and Britain alone legitimately
has five postal shapes.

Group the same column by `country` and one row separates from the rest: a US row
whose postal code has four digits where the other thirty-two have five. A dropped
leading zero, invisible at the column level, obvious the moment the column is read
against its neighbour. The same row also carries a Canadian province on a US
address — and `state_province`, viewed alone, looks entirely plausible.

So: **before reporting a format finding, ask what other column explains the
variation.** Group by it. The finding either dissolves, or it sharpens into
something specific enough to fix.

The pairs worth checking almost every time: country against postal code, region and
currency; a total against the parts that should sum to it; a start date against an
end date; a status against the timestamps that status implies. Anything that carries
a unit or a locale governs every column measured in it.

**Watch out for:**

- **Sampled scans described as full ones.** A seeded sample is perfectly
  reproducible — same answer every run — and still not a full read. *Reproducible is
  not complete.* Put the scope in the sentence carrying the finding, not in a
  footnote.
- **Confidence presented as certainty.** "This column looks like email addresses"
  and "this column is email addresses" are different claims. Detection is inference.
  Label it as inference.

---

## When you are asked "clean this up"

**Do this, in order:**

1. **Profile first.** You cannot repair what you have not measured, and you will
   need the before-picture to prove the repair worked.
2. **Propose, and change nothing.** List what you would do to which columns and
   why. *A proposal is not consent.* Stop here and let them choose.
3. **Screen every proposed repair against the four ambiguities** below. Any that is
   unresolved kills that repair — name which one and move on.
4. **Screen for value collisions.** Would this transform make two currently-distinct
   values identical? Count how many before you decide.
5. **Apply by named column, to a new file.** Never blanket across every column,
   never in place over their original.
6. **Re-profile the output in full** — not the sample, the whole thing.
7. **Check each repair's exact claim, one at a time:** the named problem is gone
   from the named column. Then check for anything in the output that was not in the
   input.
8. **Report what the re-check said**, including when it says the repair did not
   hold.

### The four ambiguities that block an automatic repair

**First, a precondition that is easy to skip and manufactures ambiguity when you
do:** these four apply only to columns whose values are *measurements* — rates,
amounts, dates, timestamps. Run them against an identifier, a row counter, or a
status code and they will fire on nothing. A plain `id` column of 1…30 has values
both below and above 1, which is the exact shape of a ratio-versus-percent
ambiguity and means nothing at all here. **Establish what the column is for before
asking what its numbers mean.** Step 4 of profiling already tells you which columns
are identifiers; use it.

When any of these is unresolved, refuse that repair and say which one it is. These
are where a helpful-looking transform silently corrupts every row:

1. **Percent versus ratio.** Is `0.15` fifteen percent, or fifteen hundredths of one
   percent? Without a clear majority scale in the column, any rescale is a coin flip
   applied to the whole file.
2. **Decimal separator.** `1,234` is one thousand two hundred thirty-four in one
   locale and one-point-two-three-four in another. If both readings appear in the
   same column, there is no safe parse.
3. **Locale more broadly.** Date order (`03/04` — March 4th or April 3rd), thousands
   grouping, negatives written as parentheses.
4. **Unresolved timezone policy.** Naive timestamps cannot be normalized until
   someone says what zone they were recorded in. Guessing shifts every row by hours.

### The collision screen

**Trimming, lowercasing, or stripping punctuation on an identifier column can
collapse two different IDs into one.** That is not a formatting fix — it is silent
row-merging, and it is unrecoverable from the output alone.

Before applying any normalizing transform: count how many values would become
duplicates of another value. Pick the threshold **before** you see the number — one
percent of non-empty rows is a defensible default — and refuse above it, handing the
count back.

**If you cannot count the collisions, refuse.** An estimate you were unable to
compute is not the same as an estimate that came back zero, and treating them alike
is how the screen gets skipped exactly when the data is weird enough to need it.

**Also needs a human regardless:** anything destructive, and anything you would
want confirmed before running.

**Watch out for:**

- **Declaring success because the targeted finding disappeared.** Losing the reason
  is not the same as fixing the column. If invalid values remain and only the
  detection stopped firing, the repair failed and the check is what changed.
- **Regressions.** Anything in the output that was not in the input counts against
  the repair even when the target is genuinely gone. A repair that trades one
  finding for two is not a repair.
- **Success inferred from an exit code.** A command that ran is not a repair that
  worked.

---

## When you are asked "do these two files agree?"

**Do this, in order:**

1. Complete step 0 on **both** files.
2. **Get the key declared.** Which column, or columns, identify a row. If the user
   has not said, ask — do not infer it from filenames, column order, or which names
   appear on both sides. A tool that guesses the key will eventually guess a
   *different* one and give a different answer for the same two files.
3. **Decide key normalization now, and keep it minimal.** This comes *before* the
   uniqueness check, because uniqueness has to be measured on the key you will
   actually pair on. See "the key is not a value" below — this is the step most
   likely to produce a clean, wrong answer.
4. **Check the normalized key is unique on both sides, before comparing anything.**
   Grain is one row per key, per side, and it is checked rather than assumed. A
   duplicate key is not a reconciliation with fan-out — it is a declaration that was
   wrong about what a row means. Stop and go back to step 2.
5. **Refuse blank keys.** A blank is not an identifier, and pairing on one silently
   reconciles unrelated records. Dropping or grouping them is defensible in other
   contexts, but it is **a different operation than the reconciliation you were
   asked for** — so if you do it, say so, and do not report the result as a
   reconciliation of the two files as given.
6. **Get the compared columns declared and mapped.** Which column on the left
   corresponds to which on the right. Never inferred.
7. **Start with every value normalization off.** Trimming, case-folding, type
   coercion, rounding, blank-equals-null — all off, the strictest reading. Turn on
   only what the user declares.
8. **Compare, and classify every row** into: matched, mismatched, near-match,
   left-only, right-only.
9. **Report the counts** with bounded samples, and both normalization sets —
   key and value — stated separately.

### The key is not a value

**Normalization that is correct for compared values is catastrophic for join keys.**
Loosen how you compare amounts all you like; loosen how you *match rows* and you
pair unrelated records and reconcile them clean.

Three ways this actually happens:

- **Numeric normalization on an identifier.** Route a key through a float and
  `10000000000000000001` and `10000000000000000002` both become
  `10000000000000000000`. Two different invoices pair, agree, and report as
  matched. **Never let an identifier pass through a floating-point number** — not
  in a key, not in a comparison, not in a spreadsheet round-trip.
- **Whitespace stripping on an identifier.** A flag that means "treat blank-like
  values as missing" may strip *all* whitespace, not just the ends — so SKU
  `AB 12` pairs with `AB12`. Nothing in the flag's name suggests it rewrites join
  keys.
- **Composite keys joined with a character a cell can contain.** Concatenate with
  `|` and `("x|y","z")` collides with `("x","y|z")` — two unrelated rows silently
  match. Use a separator that cannot appear in a value, or compare the parts as a
  tuple without concatenating at all.

**Your duplicate-key check will not save you here** — not if you run it first. That
check runs per side, and a normalization that merges a left row with the wrong right
row does its damage *across* sides, where a per-side uniqueness check structurally
cannot see it. **Uniqueness measured before normalization says nothing about
pairing after it.** That is why step 3 precedes step 4.

So: decide key normalization separately, keep it minimal, measure uniqueness on the
result, and state it separately from value normalization in the report.

**Watch out for:**

- **Near-matches folded into matches.** A close value is review evidence, never
  agreement. Its own bucket, and counted as unresolved when you summarize.
- **Fuzzy matching applied to the wrong types.** Similarity matching is for
  free-text typos. Never for amounts, for dates, for anything carrying digits, or
  for compact all-caps codes — `1000` and `100` are one edit apart and mean
  entirely different things, and `ACME-01` against `ACME-02` is two customers.
- **Blank-versus-blank counted as agreement.** Two empty cells matching is a
  *choice*, not a fact. Often the right choice. State it.
- **Truncation reported as difference.** A file cut off at a row limit shows
  thousands of left-only rows. That is a read failure wearing the costume of a
  finding.
- **Tolerance chosen after seeing the data.** Decide what counts as agreement before
  you look at how far apart things are.

---

## Before you report a pass: the false-pass check

**Do this:** for every clean result, ask whether the pass could be an artifact of
something going wrong.

Could an empty response, a read error, a truncated file, a partial scan, a column
that failed to parse, a type nothing matched, or a filter that removed every row
produce this same clean result?

If yes, the check does not distinguish success from failure and it has told you
nothing. **Zero findings on an empty read looks identical to zero findings on a
clean file.** Prove which one you have — usually by confirming the check fires on
something you know is bad.

---

## When you report

**Do this, in order:**

1. **Lead with what was checked, on what, and with what fidelity.** Full read or
   sample. Real source or fixture.
2. **Give numbers and column names, not adjectives.** "412 of 8,300 rows in
   `postal_code` are 4 digits where the column is otherwise 5" — never "some
   formatting issues in the address fields."
3. **State what you refused, and why.** A refusal is a result. It belongs in the
   report, not omitted because it is not a number.
4. **State what would need to be re-run to reproduce this** — the input, the rules,
   the declarations.

**Watch out for:**

- **Paraphrasing a finding into something vaguer than what was found.** Carry the
  specifics up. The summary is where findings go to die.
- **Routing around a refusal.** If a check would not run because the input
  was ambiguous, that is the answer. Reaching for a looser method to produce a
  number anyway defeats the reason you were careful.
- **Claiming equivalence between two paths you have not compared.** A sampled check
  and a full read, a browser run and a server run — they agree on the rules and
  diverge on how the data got in.
- **Sample fidelity passed off as the real thing.** A result from a sample, a mock,
  or a demo fixture is not a result about production.

---

## Privacy: what leaves the machine

**Do this:** keep the data where it is. Checking a file does not require sending it
anywhere, and most of the time it should not.

**Design rule worth stealing:** make the unsafe thing *unrepresentable* rather than
forbidden. If your summary structure only accepts numbers and short strings, raw
rows cannot end up in it by accident. A rule that says "don't include rows" is
followed right up until someone is in a hurry.

**Its sibling, for anything you build:** name your options so that *off* is the
strict reading. A `caseSensitive` setting punishes whoever forgets to set it; a
`--case-insensitive` flag defaults to strictness and makes leniency something a
person chose and can be shown. Whoever forgets a flag should get the careful answer,
not the convenient one.

**Watch out for:**

- **Pasting contents into an external service** — a search, an issue tracker, a
  message — on the user's behalf without them asking for exactly that.
- **Schema leaking too.** Column names and findings are not raw data, but they are
  not nothing: `Email: likely personal data` on a file called
  `Customer_Export_Q3.csv` tells a reader plenty. Descriptive, not anonymous.
- **Keys in shared output.** Row identifiers are the user's own references and the
  part of a result most likely to be forwarded onward. Counts answer whether two
  files reconciled; the identifiers usually need not travel with the answer.
- **Error messages that quote the data to explain themselves.** "Duplicate key
  `9182-JSMITH-PRIVATE`" is a useful message and a bad thing to write into a log or
  a ticket. Record the *kind* of problem; re-run to see the specifics.

---

## Keeping evidence

**Do this:** if the run matters, write down what would let someone who was not
watching believe it — what was checked, what was declared, the counts, the verdict.

**Derive the run's identifier from the input and the declarations**, not from a
counter or a clock. Then two identical runs produce the same identifier, and a
reader can *verify* reproducibility instead of trusting you. When a run is genuinely
repeated, the timestamp should be the only thing that differs.

**Include the outcome class in that identifier.** A run that refused and a run that
produced a verdict are different runs even over identical bytes under identical
settings. Leave the outcome out and their identifiers collide, and the log reads as
one run recorded twice rather than two runs that disagreed.

**Watch out for:**

- **Recording only the runs that succeeded.** A log of passes with refusals silently
  dropped misrepresents what was examined. Record what you would not answer for.
- **Reporting a failure to write evidence as a failed check.** If the log could not
  be written — bad path, no permission, disk full — the findings above it still
  stand and the verdict is unchanged. Say the record failed, not that the check did.
  Writing evidence must never be able to change the answer it is recording.

---

## What to refuse

These are refusals, not preferences. Say the refusal plainly and stop.

- **A comparison with no declared key**, a key that is not unique on both sides, or
  a column declared as both a key and a compared value.
- **Any file with duplicate column names**, until the user says which one they mean.
- **A repair under any of the four ambiguities**, or one that would merge distinct
  identifiers.
- **Any check on input that failed to read fully**, until the read is fixed or the
  partial scope is stated in the finding itself.
- **Applying a repair the user did not ask to apply**, or applying one in place over
  their original file.
- **Sending the user's data, filenames, column names, or findings to any external
  service** they did not specifically ask you to send it to.
- **Reporting a verdict you cannot say how to reproduce.**

---

## Where this stops

Follow the procedures above and you will produce careful, defensible answers with
whatever you already have. The judgement is the hard part, and the judgement is
here.

What discipline cannot give you is the guarantee. Every run is still assembled
fresh: finding names stay stable only while you remember them, the re-check compares
what you thought to compare, the collision screen runs when you remember to run it,
and the run identifier is whatever you decided to write down. None of it is enforced
when the next person is in a hurry.

GoValidate builds a deterministic engine that executes the data-processing half of
this procedure — the same file and the same rule version producing byte-identical
findings with citable reason codes, the repair and comparison refusals enforced in
the engine rather than left to discipline, and receipts a reviewer can recompute
rather than trust.

**The rest stays yours.** No engine can decide whether to paste a column name into a
ticket, whether a summary carried the specifics up, or whether the answer you gave
was the one the check supports. Those refusals live with whoever is doing the work,
which is why the procedure above is worth following either way.
See **govalidate.ai**.
