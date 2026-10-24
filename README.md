# GoValidate Lite

A free skill that helps an AI assistant check, clean, and compare CSV and other delimited files, using small Python helpers that run on your computer.

Your files stay with your assistant. GoValidate never receives them. The helpers only read the file you point them at.

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

## Requirements

`python3` 3.8 or newer on your PATH for the optional helpers in `skills/data-validation-rules/bin/`.

## Contents

- `skills/data-validation-rules/SKILL.md` - the skill instructions
- `skills/data-validation-rules/references/` - the full guidance the skill reads when needed
- `skills/data-validation-rules/bin/` - read-only Python helpers (standard library only)

More at <https://govalidate.ai/skill/>.

## License

Apache-2.0. See [LICENSE](LICENSE).
