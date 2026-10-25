# Progress: progress-marks

Integration branch: `integration/progress-marks`

## Task graph

- 01, 02, 03: no blockers
- 06 ← 02; 09 ← 01

## Tickets

- 01-stale-landed: landed 1111111
- 02-finished: finished .worktrees/02
- 03-running: running sdk .worktrees/03
- 04-dropped: landed 4444444
- 05-ahead: running sdk .worktrees/05
- 06-waits-on-finished: waiting
- 07: landed 7777777
- 09-waits-on-landed: waiting
- 10-finished-too: finished .worktrees/10

## Notes for later builders

- 08: read the notes first (a note, not a state)
