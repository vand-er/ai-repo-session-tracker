# 05: The doc lines: counts, traps, evidence and ADR numbers

Status: resolved
Blocked by: None (can start immediately)
Spec: [The retro's fixes](../spec.md), *The check guide*, *Traps*, *Evidence and ADR numbers*, *The issue tracker's
write rule* and *Seam 1, the rules-pages test*
Findings: [findings 1 (this repo's line), 6, 8 and 11](../findings.md)

## What to build

The doc lines: counts, traps, evidence and ADR numbers. A builder reads one short, true page for this step, and the tool behind it does what the page says. The page names the tool once, with the one command to run.

## Acceptance

- [ ] The page says what the tool does, in under 70 lines.
- [ ] A test fails before the change and passes after it.
- [ ] *Done means*, as the project rules say at your cut.

## Comments

- For the owner: read the changed page whole once.

### Builder, 2026-10-19 (branch `claude/05-the-doc-lines-counts-traps-evidence`, commit `73ded37`)

- Changed: one page and one tool, as the ticket says.
- Red, then green: the new test failed before the change and passed after it.
- Parked: none.
