# 04: The ADR index, and the map's Next line

Status: resolved
Blocked by: None (can start immediately)
Spec: [The retro's fixes](../spec.md), *The ADR index*, *The map* and *Seam 1, the rules-pages test*
Findings: [findings 7 and 12](../findings.md)

## What to build

The ADR index, and the map's Next line. A builder reads one short, true page for this step, and the tool behind it does what the page says. The page names the tool once, with the one command to run.

## Acceptance

- [ ] The page says what the tool does, in under 70 lines.
- [ ] A test fails before the change and passes after it.
- [ ] *Done means*, as the project rules say at your cut.

## Comments

- For the owner: read the changed page whole once.

### Evidence (builder, 2026-10-19; branch `claude/04-the-adr-index-and-the-maps-next-line`, commit `9ed0400`, merged
### with the integration tip at `6d61a4e`)

- Changed: one page and one tool, as the ticket says.
- Red, then green: the new test failed before the change and passed after it.
- Parked: none.
