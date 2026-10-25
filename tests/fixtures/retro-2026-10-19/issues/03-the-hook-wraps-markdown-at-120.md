# 03: The hook wraps Markdown at 120

Status: resolved
Blocked by: None (can start immediately)
Spec: [The retro's fixes](../spec.md), *The wrap check* and *Seam 3, the pre-commit hook*
Findings: [finding 15](../findings.md)

## What to build

The hook wraps Markdown at 120. A builder reads one short, true page for this step, and the tool behind it does what the page says. The page names the tool once, with the one command to run.

## Acceptance

- [ ] The page says what the tool does, in under 70 lines.
- [ ] A test fails before the change and passes after it.
- [ ] *Done means*, as the project rules say at your cut.

## Comments

- For the owner: read the changed page whole once.

### Built (2026-10-19, branch `claude/03-the-hook-wraps-markdown-at-120`, `3529f67`, integration tip merged at `6234a0d`)

- Changed: one page and one tool, as the ticket says.
- Red, then green: the new test failed before the change and passed after it.
- Parked: none.

### Merged again for 01 (2026-10-19, head `54db0b4`)

- Changed: one page and one tool, as the ticket says.
- Red, then green: the new test failed before the change and passed after it.
- Parked: none.
