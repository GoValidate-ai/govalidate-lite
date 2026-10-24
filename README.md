# GoValidate Lite

Check CSV files for data validation and data quality problems, clean messy data, or compare delimited files with read-only Python helpers and clear rules.

## Install

### Claude (claude.ai or the desktop app)

1. Open **Customize > Plugins**.
2. Click **Add > Add marketplace > Add from a repository**.
3. Paste `GoValidate-ai/govalidate-lite`, then click **Sync**.
4. On the **GoValidate Lite** card, click **Try in chat**. This installs the plugin and opens a chat that asks Claude to walk you through what it can do.
5. If Claude says it can't run code, turn on **code execution** under Settings > Capabilities.

If you cannot add a marketplace, download the ZIP from <https://govalidate.ai/skill/>, then open **Customize > Skills > + > Upload a skill**.

### Claude Code

```
/plugin marketplace add GoValidate-ai/govalidate-lite
/plugin install govalidate-lite@govalidate-lite
```

### Coding agents (Cursor, Codex, and others)

```
npx govalidate-lite
```

Or install just the skill folder with `npx skills add GoValidate-ai/govalidate-lite`.

## What it runs and what it sends

The skill includes five standard-library-only Python scripts in `skills/data-validation-rules/bin/`. `dq_scorecard.py` reads the file you point at and starts the other four scripts as child processes to analyze it. When it finds rows with the wrong number of fields, it writes a temporary trimmed CSV copy for those child scripts to analyze, then deletes that copy. The scripts make no network calls and send nothing to GoValidate.

## Try it

- “Check customers.csv for problems before I load it into Postgres.”
- “Clean the phone and date columns in this export and show what you changed.”
- “Compare orders_old.csv and orders_new.csv using order_id as the key.”

## Requirements

`python3` 3.8 or newer on your PATH for the optional helpers.

## Contents

- `skills/data-validation-rules/SKILL.md` - the skill instructions
- `skills/data-validation-rules/references/` - the full guidance the skill reads when needed
- `skills/data-validation-rules/bin/` - read-only Python helpers (standard library only)

Privacy: <https://govalidate.ai/privacy/>.

Security: report vulnerabilities to support@govalidate.ai or via [GitHub issues](https://github.com/GoValidate-ai/govalidate-lite/issues).

More about GoValidate: <https://govalidate.ai/skill/>.

## License

Apache-2.0. See [LICENSE](LICENSE).
