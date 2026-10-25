"""The Ticket table's row order: (rows, column, descending) -> ordered rows, plus which
sort a header click asks for. Pure: no GUI imports.

Column keys are the Ticket table's (`num`, `title`, `type`, `status`, `blocked_by`,
`flag`, `area`, `updated`, `session`). Ties keep the order the rows came in, so a
Status sort lists each status's Tickets in file order."""

from src.model.effort import FAMILIES

DEFAULT_SORT = ("num", False)   # Ticket number ascending: file order


def _status(tracked):
    """By the mark's Family in display order (Needs me first, Unknown last), then the
    word on the badge."""
    return FAMILIES.index(tracked.mark), tracked.mark_word.lower()


def _text(attr):
    """Case-blind, with blank cells after every filled one."""
    def key(tracked):
        value = getattr(tracked.ticket, attr) or ""
        return value == "", value.lower()
    return key


def _flag(tracked):
    return 0 if tracked.frontier else (2 if not tracked.blocked else 1)


_KEYS = {
    "num": lambda tracked: tracked.ticket.path.name,
    "status": _status,
    "updated": lambda tracked: tracked.ticket.mtime,
    "title": _text("title"),
    "type": _text("type"),
    "area": _text("area"),
    "blocked_by": lambda tracked: (not tracked.ticket.blockers, tracked.ticket.blockers),
    "flag": _flag,
}


def _session(session_for):
    """Tickets with a recent session first, by that session's title (case-blind)."""
    def key(tracked):
        title = session_for(tracked.ticket.path)
        return title is None, (title or "").lower()
    return key


def sort_rows(rows, column, descending, session_for=None):
    """`rows` (TrackedTickets) sorted by `column`; `descending` reverses it. `num` is file
    order. `session_for(path)` gives the title of the session on a Ticket, or None; the
    `session` column sorts by it. A column with no sort rule keeps the rows as given."""
    if column == "session":
        key = _session(session_for) if session_for else None
    else:
        key = _KEYS.get(column)
    if key is None:
        return list(rows)
    return sorted(rows, key=key, reverse=descending)


def next_sort(current, column):
    """The sort after a click on `column`'s header: a new column sorts ascending, a second
    click on the sorted column reverses it."""
    sorted_column, descending = current
    return (column, not descending) if column == sorted_column else (column, False)
