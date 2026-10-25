# 01: check_run restores TEMP and TMP

Status: resolved
Blocked by: None (can start immediately)
Spec: [The retro's fixes](../spec.md), *`check_run.ps1`* and *Seam 2, the lane*
Findings: [finding 5](../findings.md)

## What to build

check_run restores TEMP and TMP. A builder reads one short, true page for this step, and the tool behind it does what the page says. The page names the tool once, with the one command to run.

## Acceptance

- [ ] The page says what the tool does, in under 70 lines.
- [ ] A test fails before the change and passes after it.
- [ ] *Done means*, as the project rules say at your cut.

## Comments

- For the owner: read the changed page whole once.

### Built, 2026-10-19 (SDK builder, `claude/01-check-run-restores-temp-and-tmp`, commit `4b97147`, tip merged at `99f531e`)

- Changed: one page and one tool, as the ticket says.
- Red, then green: the new test failed before the change and passed after it.
- Parked: none.
