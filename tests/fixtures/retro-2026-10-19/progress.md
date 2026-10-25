# Progress: retro-2026-10-19

- Integration branch: `integration/retro-2026-10-19`, cut from `main` at `0e5d43f`. No worktree of its own: the
  merger lands each ticket onto the integration branch from the builder's worktree.
- Builders: SDK subagents, each in `.claude/worktrees/<NN-slug>` on `claude/<NN-slug>`.

- Resumed 2026-10-19: the first launch of 01 to 06 was lost before any worktree was cut. Relaunched all six, same
  worktree names.

## Task graph

- 01, 02, 03, 04, 05, 06: no blockers.
- 07: blocked by 03 and 05.

## Tickets

- 01-check-run-restores-temp-and-tmp: landed 99f531e (worktree kept for cleanup at the end)
- 02-the-warnings-count: landed 79969b5 (worktree kept for cleanup at the end)

All seven landed; integration tip 79969b5. `/code-review` since 0e5d43f done: `review.md` here.
- 08-review-fixes: landed f9f2e51 (worktree kept for cleanup at the end)

- 09-the-five-traps (ticket 02's five traps on the tools page, the owner's follow-up): landed d78266c

Done, 2026-10-20: on the owner's yes, `main` fast-forwarded 0e5d43f to d78266c; all seven tickets `Status: resolved`;
all nine worktrees and `claude/` branches pruned. `integration/retro-2026-10-19` kept, merged into `main`.
Left for the owner: one question from the review (`review.md`, *Not fixed*).
- 03-the-hook-wraps-markdown-at-120: landed 54db0b4 (worktree kept for cleanup at the end)
- 04-the-adr-index-and-the-maps-next-line: landed 6d61a4e (worktree kept for cleanup at the end)
- 05-the-doc-lines-counts-traps-evidence: landed 73ded37 (worktree kept for cleanup at the end)
- 06-the-main-page: landed 56ba200 (worktree kept for cleanup at the end)
- 07-building-a-ticket-on-its-own-page: landed 052c2a9 (worktree kept for cleanup at the end)

## ADR numbers

None foreseen by any ticket's brief. A builder needing one writes its line here first, one past the highest in
`docs/adr/`.

## Notes for later builders

- 04, 05 and 07 all add to the rules-pages test; 01 and 02 both add to the tools seam. Each adds its own test
  functions and merges the others' in by hand-back, keeping both sides.
- From 04 (landed): `docs/adr/` now holds an index opening "Highest number in use: ADR-NNNN"; a ticket adding an ADR
  adds its index line in the same commit.
- From 03 (landed), for 07: the hook now refuses CR, BOM and added `.md` lines past 120 columns.
- From 07 (landed), for 02 and the review: *Building a ticket* and *Done means* now live in
  `docs/agents/building-a-ticket.md` (under 70 lines, test-enforced); the project rules keep *Landing*.
