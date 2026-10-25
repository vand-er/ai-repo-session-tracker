# 02: The warnings count

Status: resolved
Blocked by: None (can start immediately)
Spec: [The retro's fixes](../spec.md), *The warnings count* and *Seam 2, the lane*
Findings: [finding 2](../findings.md), and finding 11's trap on in-memory compilation

## What to build

The warnings count. A builder reads one short, true page for this step, and the tool behind it does what the page says. The page names the tool once, with the one command to run.

## Acceptance

- [ ] The page says what the tool does, in under 70 lines.
- [ ] A test fails before the change and passes after it.
- [ ] *Done means*, as the project rules say at your cut.

## Comments

- For the owner: read the changed page whole once.

### Builder, 2026-10-19 (branch `claude/02-the-warnings-count`, commit `79969b5`)

- Changed: one page and one tool, as the ticket says.
- Red, then green: the new test failed before the change and passed after it.
- Parked: none.
