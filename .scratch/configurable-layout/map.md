# A configurable layout: the map

Label: wayfinder:map

A later Effort, noted at the first release (`v0.1.0`) and not yet started. Nobody has charted it: its first job is to
turn the Fog below into Tickets.

## Destination

Anyone who tracks work in markdown can point the Board at their own layout (their own folder names, file names and
status words) and see their work as a Board, without rewriting their files into the Wayfinder layout.

## Notes

- **Today's layout is fixed.** The Board reads only `.scratch/<effort>/`, with `map.md` or `spec.md`, Tickets at
  `issues/NN-<slug>.md` with `Status:`, `Type:` and `Blocked by:` lines, and `progress.md`. See
  [the issue tracker doc](../../docs/agents/issue-tracker.md).
- **The layout is read in several modules** (Efforts and Tickets, the Progress file, main's commit subjects, Builder
  and Session linking). Gathering it into one module was left for after the release; it likely comes first, so that a
  layout setting has one place to land.
- **The Wayfinder layout stays the default.** Nothing changes for anyone who sets nothing.

## Decisions so far

<!-- one line per resolved ticket: [title](issues/NN-slug.md): gist -->

## Fog

- Which parts of the layout vary: the root folder, the Effort folders, Ticket file names and numbering, the Status
  words and the Family each falls in, how blockers are written, where the map or spec lives.
- Where a layout is set: per tab in the Workspace file, or in a file inside the repo it describes.
- Whether Builder and Session linking, which finds `.scratch/<effort>/` paths in Claude Code prompts, follows the
  layout too.
- Who asks for it, and with what layouts: real ones collected from issues before any design.
