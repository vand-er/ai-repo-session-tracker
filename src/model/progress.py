"""An Effort's Progress file (`progress.md`), read as plain lines `- <NN-slug>: <state> ...`.
Pure: reads the one file, imports nothing from the GUI.

`running` is Active, `finished` is Finished and `landed <sha>` is Landed (Family Done);
any other state (`waiting`, a note) says nothing. A line is matched to a Ticket by its
`NN-slug` (the file name without `.md`), falling back to a line naming its number alone.
When several lines name the same Ticket, the furthest along counts. A missing, unreadable
or non-UTF-8 Progress file says nothing about any Ticket.

The commit shas each Ticket's lines name (whatever their state) are kept too: when
Efforts share a Ticket number, a main commit subject counts for the Effort whose line for
that Ticket names that commit (`src/model/main_branch.py`)."""

import os
import re
from collections import namedtuple
from dataclasses import dataclass, field

from src.model.marks import FINISHED, reach
from src.model.ticket import ACTIVE, DONE, append_to_section

PROGRESS_FILE = "progress.md"

STATE_FAMILY = {"running": ACTIVE, "finished": FINISHED, "landed": DONE}

# `- 07-slug: landed 1234abc ...` or `- 07: running ...`; the key is digits, then an
# optional `-slug` with no spaces.
_LINE = re.compile(r"^\s*[-*]\s+(\d+(?:-[^\s:]+)?)\s*:\s*([A-Za-z]+)")
_KEYED = re.compile(r"^\s*[-*]\s+(\d+(?:-[^\s:]+)?)\s*:(.*)")   # any line for one Ticket
_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")


Candidate = namedtuple("Candidate", "family word")   # a Ticket's Family and state word here


def _for(mapping, ticket):
    """`mapping`'s entry for `ticket`: by its `NN-slug`, else by its number alone."""
    found = mapping.get(ticket.path.stem.lower())
    if found is None and ticket.number:
        found = mapping.get(ticket.number)
    return found


@dataclass(frozen=True)
class Progress:
    mtime: float                                 # 0.0 when there is no file
    states: dict = field(default_factory=dict)   # key (lower case) -> state word
    shas: dict = field(default_factory=dict)     # key -> shas named on that key's lines

    def names(self, ticket, sha):
        """Whether a line for `ticket` names commit `sha` (a full sha), in full or
        abbreviated (7 to 40 hex digits). A sha named on any other line does not count."""
        return any(sha.startswith(short) for short in _for(self.shas, ticket) or ())

    def shas_of(self, ticket):
        """The commit shas named on `ticket`'s lines, sorted (the Ticket check prints them)."""
        return tuple(sorted(_for(self.shas, ticket) or ()))

    def candidate(self, ticket):
        """`Candidate(family, word)` the Progress file gives `ticket`, or None."""
        word = _for(self.states, ticket)
        return Candidate(STATE_FAMILY[word], word) if word else None


NONE = Progress(mtime=0.0)


def read_progress(folder, last=None):
    """The Progress file of the Effort in `folder`. Given the `last` Progress read from
    it, a file whose modification time has not changed is not read again."""
    path = os.path.join(folder, PROGRESS_FILE)
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return NONE
    if last is not None and last.mtime == mtime and mtime:
        return last
    try:
        with open(path, "rb") as file:
            text = file.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return Progress(mtime=mtime)
    states, shas = {}, {}
    for line in text.splitlines():
        keyed = _KEYED.match(line)
        if keyed:
            named = _SHA.findall(keyed.group(2).lower())
            if named:
                key = keyed.group(1).lower()
                shas[key] = shas.get(key, frozenset()) | frozenset(named)
        match = _LINE.match(line)
        if not match:
            continue
        key, word = match.group(1).lower(), match.group(2).lower()
        if word not in STATE_FAMILY:
            continue
        if key not in states or reach(STATE_FAMILY[word]) > reach(STATE_FAMILY[states[key]]):
            states[key] = word
    return Progress(mtime=mtime, states=states, shas=shas)


_BULLET = re.compile(r"^(\s*[-*]\s+)")


def landed_lines(lines, ticket, sha):
    """A Progress file's lines (no line endings) with `ticket`'s line set to
    `- <NN-slug>: landed <sha>`. The line replaced is the first one for that Ticket (by
    `NN-slug`, else by its number) whose state is a state above or `waiting`; a note
    keyed to its number stays. With no such line, one is added at the end of the
    `## Tickets` section, else at the end of the file. Pure; the Ticket check tool
    (tools/ticket_check.py) does the reading and writing."""
    lines = list(lines)
    keys = (ticket.path.stem.lower(), ticket.number)
    new = f"{ticket.path.stem}: landed {sha}"
    for wanted in keys:
        for index, line in enumerate(lines):
            match = _LINE.match(line)
            if (match and match.group(1).lower() == wanted
                    and match.group(2).lower() in (*STATE_FAMILY, "waiting")):
                lines[index] = _BULLET.match(line).group(1) + new
                return lines
    return append_to_section(lines, "tickets", f"- {new}", [f"- {new}"])
