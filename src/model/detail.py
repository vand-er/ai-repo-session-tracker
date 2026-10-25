"""What the detail pane shows for a selected file: its kind, the command Copy command puts
on the clipboard, and its body. Pure: reads the one file asked for, imports nothing from
the GUI. A scan never calls this; a body is read only when a file is selected."""

import textwrap
from dataclasses import dataclass
from pathlib import Path

from src.model.effort import WAYFINDER
from src.model.ticket import SECTION

MAP = "map"
SPEC = "spec"
WAYFINDER_TICKET = "wayfinder ticket"
BUILD_TICKET = "build ticket"

# The skill that takes each kind of file. Data, not code.
SKILL = {
    MAP: "/wayfinder",
    WAYFINDER_TICKET: "/wayfinder",
    SPEC: "/to-tickets",
    BUILD_TICKET: "/implement",
}


# The sections of a Map the pane shows, in the Map's own order.
MAP_SECTIONS = ("Destination", "Decisions so far")


@dataclass(frozen=True)
class Detail:
    path: Path      # absolute
    kind: str       # MAP, SPEC, WAYFINDER_TICKET or BUILD_TICKET
    command: str    # what Copy command puts on the clipboard
    body: str       # the text the pane shows
    last_message: str | None = None   # a Ticket being built: its Builder's last message


def copy_command(kind, path):
    """The command to paste into a fresh session: the kind's skill, then the absolute path."""
    return f"{SKILL[kind]} {path}"


def fit_message(text, columns, lines):
    """A Builder's last message as the detail pane shows it without scrolling: its words
    on one flow, wrapped at words to `columns` characters, cut to `lines` lines, the cut
    ending in an ellipsis."""
    wrapped = textwrap.wrap(" ".join(text.split()), max(2, columns))
    if len(wrapped) <= lines:
        return "\n".join(wrapped)
    shown = wrapped[:max(1, lines)]
    last = shown[-1]
    while len(last) + 1 > columns:
        last = last.rsplit(" ", 1)[0] if " " in last else last[:columns - 1]
    shown[-1] = last + "…"
    return "\n".join(shown)


def file_kind(effort, path):
    """The kind of `path` within `effort`: its Map or Spec, or one of its Tickets."""
    wayfinder = effort.kind == WAYFINDER
    if Path(path).name in ("map.md", "spec.md") and Path(path).parent == Path(effort.path):
        return MAP if wayfinder else SPEC
    return WAYFINDER_TICKET if wayfinder else BUILD_TICKET


def read_detail(effort, path):
    """Read `path` (a Ticket, Map or Spec of `effort`) now, for the detail pane."""
    path = Path(path).resolve()
    kind = file_kind(effort, path)
    return Detail(path=path, kind=kind, command=copy_command(kind, path),
                  body=_body(kind, path))


def _sections(text):
    """(heading, text) for each `## ` section, the heading line included in the text."""
    sections, heading, lines = [], None, []
    for line in text.splitlines():
        match = SECTION.match(line)
        if match:
            if heading is not None:
                sections.append((heading, "\n".join(lines).strip()))
            heading, lines = match.group(1), []
        if heading is not None:
            lines.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def _body(kind, path):
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as err:
        return f"Could not read this file: {getattr(err, 'strerror', None) or err}"
    sections = _sections(text)
    if not sections:
        return "\n".join(text.splitlines()).strip()
    if kind == MAP:
        return "\n\n".join(t for h, t in sections if h in MAP_SECTIONS)
    return "\n\n".join(t for _h, t in sections)
