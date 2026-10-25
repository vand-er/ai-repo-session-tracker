# Files are the source of truth; no central state JSON

The Board shows Wayfinder maps and local-markdown tickets that agents and skills write to disk. We considered a central JSON file holding the Wayfinder state that every tab reads from. We rejected it: it would be a second copy of state that agents never update, so it would drift from the files the moment an agent marks a ticket resolved. Instead the model parses the Source folder into an in-memory snapshot on every poll, and the only JSON the app keeps is `workspace.json`, which holds app state (open tabs, their folders, the palette), never ticket state.

## Consequences

- Every status, family, blocked flag and frontier mark is derived from the files on each scan; nothing is cached across runs.
- The parser must absorb the mixed formats found on disk (plain and bold `Status:` lines, `Blocked by:` with reasons) rather than expect a clean schema.
- Editing from the app, if added later, rewrites the markdown files; it never writes to a parallel store.
