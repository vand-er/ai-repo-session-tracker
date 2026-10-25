"""The diff step of polling: compare the last Snapshot with a fresh one and say what the
shown Effort's Board must redraw. Imports no GUI toolkit."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RowChanges:
    redraw: tuple = ()     # paths of rows whose content changed
    flash: tuple = ()      # paths of rows whose Status or mark changed (a subset of redraw)
    reshape: bool = False  # rows came or went: redraw the whole table
    header: bool = False   # the Effort list or the shown Effort's header changed

    def __bool__(self):
        return bool(self.redraw or self.reshape or self.header)


def diff_snapshots(old, new, effort_name):
    """What changed between Snapshots `old` and `new` for the Effort named `effort_name`.
    Rows are matched by Ticket path. `old` of None (never drawn) reshapes everything."""
    before, after = _effort(old, effort_name), _effort(new, effort_name)
    rows_before = {t.ticket.path: t for t in before.tickets} if before else {}
    rows_after = {t.ticket.path: t for t in after.tickets} if after else {}
    redraw = tuple(p for p, t in rows_after.items() if p in rows_before and rows_before[p] != t)
    flash = tuple(p for p in redraw if _shown(rows_before[p]) != _shown(rows_after[p]))
    reshape = before is None or after is None or list(rows_before) != list(rows_after)
    return RowChanges(redraw=redraw, flash=flash, reshape=reshape,
                      header=_heads(old) != _heads(new))


def _shown(row):
    """What a flash calls out: the Status line, and the mark the badge shows (which a
    Progress file line can move with no Status line changing)."""
    return row.ticket.status, row.mark, row.mark_word


def _heads(snapshot):
    """Everything the Effort list and header card draw: each Effort minus its rows."""
    if snapshot is None:
        return None
    return [(e.path, e.name, e.kind, e.title, e.status, e.counts, e.stale_spec, len(e.tickets))
            for e in snapshot.efforts]


def _effort(snapshot, name):
    if snapshot is None:
        return None
    return next((e for e in snapshot.efforts if e.name == name), None)
