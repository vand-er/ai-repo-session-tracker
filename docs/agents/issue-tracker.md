# Issue tracker: local markdown

Issues and specs for this repo live as markdown files in `.scratch/`, tracked in git and public. Write them for any reader, and the personal-strings check scans them like any other file.

The Board reads this layout, so keep to it exactly: a file named or shaped differently drops off the Board.

The slash commands named here come from Matt Pocock's skills (<https://github.com/mattpocock/skills>). They are optional; each bullet says what the command writes, so you can write the same file by hand.

## Conventions

- One Effort per directory: `.scratch/<effort-slug>/`.
- A build Effort's spec is `.scratch/<effort-slug>/spec.md` (what `/to-spec` writes: the problem, the solution, user stories and decisions).
- Its Tickets are one file each at `.scratch/<effort-slug>/issues/<NN>-<slug>.md` (what `/to-tickets` writes), numbered from `01`, never a single combined tickets file. Each has a `Status:` line near the top (see `triage-labels.md`), and a `Blocked by: NN, NN` line when it waits on others.
- While Tickets are built (what `/implement` does, one Builder per Ticket), `.scratch/<effort-slug>/progress.md` holds one line per Ticket: `- NN-slug: running`, `finished` or `landed <sha>`. The README says how the Board reads it.
- Comments and conversation history append to the bottom of a Ticket under a `## Comments` heading.

## Publishing and fetching

- To publish to the issue tracker, create a new file under `.scratch/<effort-slug>/`, creating the directory if needed.
- To fetch a Ticket, read the file at its path. The user normally passes the path or the number.

## Wayfinding

A Wayfinder Effort (what `/wayfinder` charts) is work too foggy to spec yet: a **map** with one Ticket per open question.

- **Map**: `.scratch/<effort>/map.md`, with the destination, then *Notes*, *Decisions so far* and *Fog*.
- **Ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the Ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `open`/`claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A Ticket is unblocked when every Ticket it lists is `resolved`.
- **Frontier**: the open, unblocked, unclaimed Tickets; the lowest number goes first.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then add one line (gist and link) to the map's *Decisions so far*.
