"""One Ticket file to one Ticket. Pure: reads the file, imports nothing from the GUI."""

import re
from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path

# Every Family, by name. This is the one module that writes them; every other module
# imports these and never retypes them (a guard test, tests/guards/test_families.py).
NEEDS_ME, WAITING, READY, ACTIVE = "Needs me", "Waiting", "Ready", "Active"
DONE, DROPPED, UNKNOWN = "Done", "Dropped", "Unknown"
FINISHED = "Finished"   # no Status falls into it: only a mark reaches it (src/model/marks.py)

# Status -> Family. Data, not code: a new Status, or a new Family, is one entry here.
STATUS_FAMILY = {
    "open": NEEDS_ME,
    "needs-triage": NEEDS_ME,
    "ready-for-human": NEEDS_ME,
    "needs-info": WAITING,
    "ready-for-agent": READY,
    "claimed": ACTIVE,
    "running": ACTIVE,
    "resolved": DONE,
    "landed": DONE,
    "wontfix": DROPPED,
}

# Where a section starts, for the header (everything before the first section) and for
# the detail pane's sections alike: a level-2 heading, `## Name`. `###` stays inside.
SECTION = re.compile(r"^##(?!#)\s*(.*?)\s*$")

_NUMBER = re.compile(r"^(\d+)")
_TITLE = re.compile(r"^#\s+(?:\d+:\s*)?(.*?)\s*$")


def _field(name):
    # `Name: value` or `**Name:** value`
    return re.compile(r"^\s*(?:\*\*)?" + name + r":(?:\*\*)?\s*(.*?)\s*$", re.IGNORECASE)


_FIELDS = {key: _field(label) for key, label in
           (("status", "Status"), ("type", "Type"), ("area", "Area"),
            ("blocked_by", "Blocked by"), ("waits_on", "Waits on"))}
_PARENS = re.compile(r"\([^()]*\)")
_BLOCKER = re.compile(r"^\d{2}$")


@dataclass(frozen=True)
class Ticket:
    path: Path
    number: str
    title: str
    status: str
    family: str
    type: str
    area: str
    blockers: tuple
    mtime: float
    parsed: bool


def family_of(status):
    return STATUS_FAMILY.get(status.lower(), UNKNOWN)


Blockers = namedtuple("Blockers", "numbers readable")   # what read_blocked_by gives
Header = namedtuple("Header", "title status fields")    # what read_header gives


def read_blocked_by(value):
    """A `Blocked by:` value -> `Blockers(numbers, readable)`.

    `07, 08, 09` or `03 (why), 05 (why)` -> the numbers. Reasons in brackets are
    dropped first, then it stops at the first item that is not a bare two-digit number,
    so `none`, `None. ...` and `08 (why), so ...` read right and nothing inside a
    reason (a commit hash, an ADR number) ever counts.

    `readable` says whether that stop was a reading the Board means, not a value it
    silently misread: an empty value, one starting with the word None, and prose after at
    least one number are readable; stopping on the first item (`01–12`, `the shell
    ticket`) or on a later item that starts with a digit (`01, 02-05`) is not."""
    if not value.strip() or re.match(r"(?i)none\b", value.strip()):
        return Blockers((), True)
    previous = None
    while previous != value:
        previous, value = value, _PARENS.sub("", value)
    value = value.split("(", 1)[0]
    numbers = []
    for item in value.split(","):
        item = item.strip()
        if not _BLOCKER.match(item):
            return Blockers(tuple(numbers), bool(numbers) and not item[:1].isdigit())
        numbers.append(item)
    return Blockers(tuple(numbers), True)


def read_header(path):
    """The header of a Ticket, Map or Spec: everything before the first SECTION heading.
    Returns `Header(title, status, fields)`, where status is the first word of the `Status:`
    line and fields holds the raw `Status`, `Type`, `Area`, `Blocked by` and `Waits on`
    values found (keys `status`, `type`, `area`, `blocked_by`, `waits_on`).
    Returns None when the file is missing or its header is not UTF-8.

    Reads line by line and stops at the first section, so a scan never reads a body."""
    try:
        with open(path, "rb") as file:
            lines = []
            for raw in file:
                line = raw.decode("utf-8").rstrip("\r\n")
                if SECTION.match(line):
                    break
                lines.append(line)
    except (OSError, UnicodeDecodeError):
        return None
    title = ""
    found = {}
    for line in lines:
        if not title:
            title_match = _TITLE.match(line)
            if title_match:
                title = title_match.group(1)
                continue
        for key, pattern in _FIELDS.items():
            if key not in found:
                field_match = pattern.match(line)
                if field_match:
                    found[key] = field_match.group(1)
    words = found.get("status", "").split()
    return Header(title, (words[0] if words else ""), found)


def number_of(name):
    """A Ticket's number from its file name (`07-slug.md` -> "07"), "" when it has none."""
    match = _NUMBER.match(name)
    return match.group(1) if match else ""


def parse_ticket(path, mtime=None):
    """One Ticket file to one Ticket. `mtime` is the file's modification time when the
    caller already has it (from a directory listing); else the file is statted."""
    return ticket_of(path, read_header(path), mtime)


def ticket_of(path, header, mtime=None):
    """The Ticket at `path` whose header (from `read_header`, None when unreadable) is
    `header`: for a caller that needs the header's raw fields too, so the file is read
    once. `mtime` as for `parse_ticket`."""
    path = Path(path)
    number = number_of(path.name)
    if mtime is None:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
    if header is None:
        return Ticket(path=path, number=number, title="", status="", family=UNKNOWN,
                      type="", area="", blockers=(), mtime=mtime, parsed=False)
    return Ticket(
        path=path,
        number=number,
        title=header.title,
        status=header.status,
        family=family_of(header.status),
        type=header.fields.get("type", ""),
        area=header.fields.get("area", ""),
        blockers=read_blocked_by(header.fields.get("blocked_by", "")).numbers,
        mtime=mtime,
        parsed=bool(header.status),
    )


_OPEN_BOX = re.compile(r"^(\s*[-*]\s+\[) \]")


def closed_lines(lines, comment):
    """A Ticket's lines (no line endings) closed out: the header's Status line says
    `resolved`, every box is ticked, and `comment` is appended as a bullet under
    `## Comments` (made at the end when there is none). Pure; the Ticket check tool
    (tools/ticket_check.py) does the reading and writing. Raises ValueError when the
    header has no Status line."""
    lines = list(lines)
    found = False
    for index, line in enumerate(lines):
        if SECTION.match(line):
            break
        match = _FIELDS["status"].match(line)
        if match:
            lines[index] = line[:match.start(1)] + "resolved" + line[match.end(1):]
            found = True
            break
    if not found:
        raise ValueError("no Status line before the first section")
    lines = [_OPEN_BOX.sub(r"\1x]", line) for line in lines]

    bullet = comment if comment.startswith(("- ", "* ")) else f"- {comment}"
    return append_to_section(lines, "comments", bullet, ["", "## Comments", "", bullet],
                             blank_under_heading=True)


def append_to_section(lines, heading, new, missing, blank_under_heading=False):
    """`lines` (no line endings) with the line `new` added at the end of the first
    `## heading` section (matched without case), above its trailing blank lines. An empty
    section gets a blank line under its heading first when `blank_under_heading`. With no
    such section, the trailing blank lines are dropped and the lines `missing` appended.
    Pure: the Ticket and Progress close-outs share it."""
    lines = list(lines)
    start = next((i for i, line in enumerate(lines)
                  if SECTION.match(line) and SECTION.match(line).group(1).lower() == heading),
                 None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        return lines + list(missing)
    end = next((i for i in range(start + 1, len(lines)) if SECTION.match(lines[i])), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    if blank_under_heading and end == start + 1:
        lines.insert(end, "")
        end += 1
    lines.insert(end, new)
    return lines
