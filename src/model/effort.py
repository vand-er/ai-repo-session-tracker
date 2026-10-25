"""One Effort folder to one Effort, and one Source folder to one Snapshot.
Pure: reads the files, imports nothing from the GUI."""

import os
from dataclasses import dataclass
from pathlib import Path

from src.model.files import entry_stats
from src.model.main_branch import NONE as NO_MAIN, read_main
from src.model.marks import FINISHED, finished, mark_of, reach
from src.model.progress import read_progress
from src.model.ticket import (DONE, DROPPED, STATUS_FAMILY, UNKNOWN, Ticket, family_of,
                              parse_ticket, read_header)

WAYFINDER = "wayfinder"
BUILD = "build"


def _display_order():
    """Every Family, in display order: the Status Families in the order STATUS_FAMILY
    first gives them, Finished (no Status's Family: only a Ticket's mark reaches it,
    src/model/marks.py) just before Done, then Unknown."""
    order = list(dict.fromkeys(STATUS_FAMILY.values()))
    order.insert(order.index(DONE), FINISHED)
    return (*order, UNKNOWN)


# Every Family, in display order, so counts always carry each one (zero included).
FAMILIES = _display_order()
RESOLVED = frozenset({DONE, DROPPED})   # relieves Blocked; Finished does not
# The Frontier's Families: not yet Active, Finished, Done or Dropped, and known.
TAKEABLE = frozenset(f for f in FAMILIES if reach(f) == 0) - {DROPPED, UNKNOWN}


@dataclass(frozen=True)
class TrackedTicket:
    """A Ticket plus what only its Effort can tell: its mark (the Family it is shown in,
    and the word on its badge), whether it is Blocked or on the Frontier, and which
    blocker numbers have no Ticket file (they count as unresolved)."""
    ticket: Ticket
    blocked: bool
    frontier: bool
    missing_blockers: tuple
    mark: str        # the Family shown: the furthest along of every record
    mark_word: str   # the word on the badge: the Status, or the record that won


@dataclass(frozen=True)
class Effort:
    path: Path
    name: str
    kind: str          # WAYFINDER (has map.md), BUILD (has spec.md), or "" (neither)
    title: str         # the Map's or Spec's title
    status: str        # the Map's or Spec's Status, first word, "" when none
    tickets: tuple     # TrackedTicket, in file-name order
    counts: dict       # Family -> number of Tickets by mark, every Family present
    stale_spec: bool   # Spec not Done while every Ticket is Done or Dropped
    progress: object = None   # the Progress file as last read, for the next scan

    def find(self, path):
        """The TrackedTicket whose file is at `path`, or None."""
        return next((t for t in self.tickets if t.ticket.path == path), None)


@dataclass(frozen=True)
class Snapshot:
    source: Path
    efforts: tuple     # Effort, in name order
    main: object = None   # main's commit subjects as last read, for the next scan

    def tickets(self):
        """Every TrackedTicket of every Effort, Effort by Effort."""
        return (t for effort in self.efforts for t in effort.tickets)

    def find(self, path):
        """The TrackedTicket whose file is at `path`, in any Effort, or None."""
        return next((t for t in self.tickets() if t.ticket.path == path), None)


def _is_effort(folder):
    return any((folder / name).exists() for name in ("map.md", "spec.md", "issues"))


def _markdown_files(issues):
    """`(path, mtime)` for each `*.md` in `issues`, in name order, or none when it is not a
    readable folder. Listed from its directory entries, which carry their stat on Windows,
    so no file is opened or statted one by one."""
    try:
        stats = entry_stats(issues, "*.md")
    except OSError:
        return []
    return sorted((issues / name, stat.st_mtime if stat else 0.0) for name, stat in stats.items())


def scan_effort(folder, known=None, last=None, builder_for=None, main=NO_MAIN):
    """`known` maps a Ticket path to its Ticket from an earlier scan: a file whose
    modification time is still that Ticket's is not read again. `last` is this Effort
    from an earlier scan, whose Progress file is likewise not read again if unchanged.
    `builder_for(ticket)` gives the Builder on a Ticket, or None (`src/model/builders.py`).
    `main` is the repo's MainHistory (src/model/main_branch.py), as `scan` reads it.

    Each Ticket's mark is derived here, on every scan, from its Status line, the
    Progress file, its Builder's finished flag and main's commit subjects; Blocked, the
    Frontier, the counts and the Spec warning go by it."""
    builder_for = builder_for or (lambda _ticket: None)
    folder = Path(folder)
    known = known or {}
    progress = read_progress(folder, last.progress if last is not None else None)
    if (folder / "map.md").is_file():
        kind, header_file = WAYFINDER, folder / "map.md"
    elif (folder / "spec.md").is_file():
        kind, header_file = BUILD, folder / "spec.md"
    else:
        kind, header_file = "", None
    header = read_header(header_file) if header_file else None
    title, status = (header[0], header[1]) if header else ("", "")

    tickets = []
    for path, mtime in _markdown_files(folder / "issues"):
        earlier = known.get(path)   # this Ticket as an earlier scan read it
        unchanged = earlier is not None and mtime and earlier.mtime == mtime
        tickets.append(earlier if unchanged else parse_ticket(path, mtime))
    marks = [mark_of(t.family, t.status, (progress.candidate(t), finished(builder_for(t)),
                                          main.candidate(t, progress)))
             for t in tickets]
    family_by_number = {}
    for ticket, mark in zip(tickets, marks):
        if ticket.number:
            family_by_number.setdefault(ticket.number, set()).add(mark.family)

    tracked = []
    for ticket, mark in zip(tickets, marks):
        missing = tuple(n for n in ticket.blockers if n not in family_by_number)
        blocked = bool(missing) or any(
            not family_by_number[n] <= RESOLVED for n in ticket.blockers if n in family_by_number)
        tracked.append(TrackedTicket(
            ticket=ticket,
            blocked=blocked,
            frontier=not blocked and mark.family in TAKEABLE,
            missing_blockers=missing,
            mark=mark.family,
            mark_word=mark.word,
        ))

    counts = {family: 0 for family in FAMILIES}
    for mark in marks:
        counts[mark.family] = counts.get(mark.family, 0) + 1

    stale_spec = (kind == BUILD and bool(tickets)
                  and family_of(status) != DONE
                  and all(mark.family in RESOLVED for mark in marks))

    return Effort(path=folder, name=folder.name, kind=kind, title=title, status=status,
                  tickets=tuple(tracked), counts=counts, stale_spec=stale_spec,
                  progress=progress)


def _repo_efforts(source, folders, repo):
    """Every Effort folder in the repo at `repo`: the `folders` scanned from `source`, and,
    when `source` is not the repo's root, the Effort folders under the repo's `.scratch/`."""
    found = {os.path.normcase(os.path.abspath(f)): f for f in folders}
    scratch = repo / ".scratch"
    if os.path.normcase(os.path.abspath(source)) != os.path.normcase(str(repo)):
        try:
            with os.scandir(scratch) as entries:
                others = [scratch / e.name for e in entries if e.is_dir()]
        except OSError:
            others = []
        for folder in others:
            if _is_effort(folder):
                found.setdefault(os.path.normcase(str(folder)), folder)
    return list(found.values())


def scan(source_folder, previous=None, builder_for=None, git=True, branch=None):
    """A Source folder holding `.scratch/` is a repo root: every Effort folder under
    `.scratch/` (one with `map.md`, `spec.md` or `issues/`) is scanned. Any other
    folder is one Effort.

    Given the `previous` Snapshot of the same folder, a Ticket file whose modification
    time has not changed since is taken from it instead of being read again, and main's
    commit subjects are not read again while main's tip has not moved. With `git` False
    the scan runs no git: main's subjects count only as `previous` read them.
    `builder_for(ticket)` gives each Ticket's Builder, whose finished flag counts
    towards its mark. `branch` is the tab's branch setting: the branch read as main,
    when set (src/model/main_branch.py)."""
    source = Path(source_folder)
    scratch = source / ".scratch"
    if scratch.is_dir():
        with os.scandir(scratch) as entries:
            found = [scratch / e.name for e in entries if e.is_dir()]
        folders = sorted((f for f in found if _is_effort(f)),
                         key=lambda f: (f.name.lower(), f.name))
    else:
        folders = [source]
    known = ({t.ticket.path: t.ticket for t in previous.tickets()}
             if previous is not None else {})
    lasts = {e.path: e for e in previous.efforts} if previous is not None else {}
    main = read_main(source, previous.main if previous is not None else None, git, branch)
    if main.shas:
        main = main.among(_repo_efforts(source, folders, main.repo))
    return Snapshot(source=source, main=main,
                    efforts=tuple(scan_effort(f, known, lasts.get(f), builder_for, main)
                                  for f in folders))
