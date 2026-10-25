"""The pure parts of the Sessions tab and the Board's Session column: which Session is
on which Ticket, the "3m ago" text, and the sessions settings kept in the Workspace.
No GUI imports here, and no file reads: `scan_sessions` does those."""

import ntpath
import os
import posixpath
from datetime import timedelta
from pathlib import Path

from src.model.sessions import path_parts
from src.model.ticket import UNKNOWN
from src.system import WINDOWS


WINDOW_KEY = "sessions_window_minutes"
PROJECTS_KEY = "claude_projects_dir"
DEFAULT_WINDOW_MINUTES = 30


CONFIG_DIR_VAR = "CLAUDE_CONFIG_DIR"   # Claude Code's own folder, when it is moved


def default_projects_dir():
    """Claude Code's projects folder: `$CLAUDE_CONFIG_DIR/projects` when that variable is
    set, else `~/.claude/projects`, on every system."""
    config = os.environ.get(CONFIG_DIR_VAR, "")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "projects"


def sessions_settings(workspace):
    """`(projects_dir, window)` from the Workspace file's `claude_projects_dir` and
    `sessions_window_minutes` keys. A missing or bad value gives the default:
    `default_projects_dir()` and 30 minutes."""
    minutes = workspace.setting(WINDOW_KEY, DEFAULT_WINDOW_MINUTES)
    if minutes <= 0:
        minutes = DEFAULT_WINDOW_MINUTES
    folder = workspace.setting(PROJECTS_KEY, "")
    projects_dir = Path(folder).expanduser() if folder else default_projects_dir()
    return projects_dir, timedelta(minutes=minutes)


def ticket_key(path, windows=WINDOWS):
    """A path as a comparable key: separators unified, `.` and `..` folded, and on
    Windows lower-cased, since its paths are case-insensitive. Reads no disk."""
    text = str(path)
    if windows:
        return ntpath.normcase(ntpath.normpath(text))
    return posixpath.normpath(text)


def _relative(key):
    """Whether a mentioned path's key is relative to a repo root (`.scratch/...`)."""
    return key.startswith(".scratch")


def names(mentioned, key, windows=WINDOWS):
    """Whether a mentioned path, as its `ticket_key`, names the path whose key is `key`:
    the same path, or, when the mention is relative to a repo root (`.scratch/<effort>
    /...`), any path that ends with it."""
    if _relative(mentioned):
        return key.endswith(("\\" if windows else "/") + mentioned)
    return key == mentioned


def match_sessions(sessions, windows=WINDOWS):
    """A lookup `path -> Session or None`: the newest Session whose first prompt named
    that Ticket (or Map) path anywhere in it. A relative `.scratch/<effort>/...` mention
    matches every path that ends with it."""
    by_key, relative = {}, []
    for s in sessions:
        for mention in s.mentions:
            key = ticket_key(mention, windows)
            if _relative(key):
                relative.append((key, s))
            elif key not in by_key or s.modified > by_key[key].modified:
                by_key[key] = s

    def lookup(path):
        key = ticket_key(path, windows)
        found = [s for mentioned, s in relative if names(mentioned, key, windows)]
        if key in by_key:
            found.append(by_key[key])
        return max(found, key=lambda s: s.modified, default=None)
    return lookup


COLUMNS = ("Title", "Project", "Last message", "By", "Model", "Ticket")
NOT_GIVEN = UNKNOWN   # a Session field its transcript did not give: the Ticket module's name
NO_TICKET = "—"


def session_row(session, now):
    """The Sessions tab's cells for one Session, in COLUMNS order. A field the file did
    not give reads NOT_GIVEN; a Session on no Ticket reads NO_TICKET."""
    return (session.title or NOT_GIVEN, session.project or NOT_GIVEN,
            ago(session.last_message_at, now), session.sender or NOT_GIVEN,
            session.model or NOT_GIVEN, ticket_label(session.ticket))


SUBAGENT_MARK = "└ "   # a subagent's row, under its orchestrator's


def builder_row(builder, project, now):
    """The Sessions tab's cells for a subagent Builder (src/model/builders.py), drawn under
    its orchestrator's row: its description, the orchestrator's `project`, its last line's
    age, and the Ticket number it builds. Who spoke last and the model are not read."""
    number, efforts = builder.number, builder.efforts
    ticket = f"{path_parts(efforts[0])[-1]}/{number}" if number and efforts else NO_TICKET
    return (SUBAGENT_MARK + (builder.description or NOT_GIVEN), project or NOT_GIVEN,
            ago(builder.last_line_at, now), NO_TICKET, NO_TICKET, ticket)


def ticket_label(path):
    """A Ticket or Map path as `<effort>/<file>`, or NO_TICKET for none."""
    if path is None:
        return NO_TICKET
    parts = path_parts(path)
    if len(parts) >= 3 and parts[-2].lower() == "issues":
        return f"{parts[-3]}/{parts[-1]}"
    return "/".join(parts[-2:])


def ago(then, now):
    """How long before `now` `then` was, in its largest whole unit: "12s ago", "3m ago",
    "2h ago", "2d ago". None reads NOT_GIVEN."""
    if then is None:
        return NOT_GIVEN
    return f"{age(then, now)} ago"


def age(then, now):
    """How long before `now` `then` was, in its largest whole unit: "12s", "3m", "2h", "2d"."""
    seconds = max(0, int((now - then).total_seconds()))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"
