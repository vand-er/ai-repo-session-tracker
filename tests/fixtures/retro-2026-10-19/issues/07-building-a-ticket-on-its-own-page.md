# 07: Building a ticket, on its own page

Status: resolved
Blocked by: 03 (the hook wraps Markdown at 120), 05 (the doc lines: counts, traps, evidence and ADR numbers)
Spec: [The retro's fixes](../spec.md), *Building a ticket* and *Seam 1, the rules-pages test*
Findings: [findings 3, 4, 11 and 15](../findings.md)

## What to build

Building a ticket, on its own page. A builder reads one short, true page for this step, and the tool behind it does what the page says. The page names the tool once, with the one command to run.

## Acceptance

- [ ] The page says what the tool does, in under 70 lines.
- [ ] A test fails before the change and passes after it.
- [ ] *Done means*, as the project rules say at your cut.

## Comments

- For the owner: read the changed page whole once.

### Evidence (builder, 2026-10-19)

- Changed: one page and one tool, as the ticket says.
- Red, then green: the new test failed before the change and passed after it.
- Parked: none.
