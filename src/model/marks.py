"""A Ticket's mark: the Family the Board shows it in, derived on every scan from every
record of how far along it is, and never stored (ADR 0001). Pure: imports no GUI.

The candidates are the Ticket's Status line (its Family and word) and each other record's
`(Family, word)`: the Effort's Progress file (`src/model/progress.py`), its Builder's
finished flag (`finished` here) and main's commit subjects (`src/model/main_branch.py`).
The furthest along wins, in the order Todo/Ready, Active, Finished, Landed/Done, except
that a Dropped Status line always wins. On a tie the Status line wins, so its own word
stays on the badge."""

from collections import namedtuple

from src.model.ticket import ACTIVE, DONE, DROPPED, FINISHED  # Finished: only a mark reaches it

# How far along each Family is. A Family not named here (Needs me, Waiting, Ready,
# Dropped, Unknown) has not started: 0.
_REACH = {ACTIVE: 1, FINISHED: 2, DONE: 3}

Mark = namedtuple("Mark", "family word")   # the Family shown, and the word on the badge


def reach(family):
    return _REACH.get(family, 0)


def stopped(family):
    """Whether a Ticket whose mark is `family` has stopped being built: Finished, Landed
    (Done) or Dropped. Its row shows no Activity, whatever its Builder's files say."""
    return family == DROPPED or reach(family) >= reach(FINISHED)


def finished(builder):
    """The candidate a Ticket's Builder (`src/model/builders.py`) gives: Finished once
    its metadata says it has handed back, else None."""
    return (FINISHED, "finished") if builder is not None and builder.finished else None


def mark_of(status_family, status_word, candidates=()):
    """The mark of a Ticket whose Status line gives `status_family` and `status_word`,
    given the other records' `(Family, word)` candidates (None entries are skipped)."""
    best = Mark(status_family, status_word)
    if status_family == DROPPED:
        return best
    for candidate in candidates:
        if candidate is not None and reach(candidate[0]) > reach(best.family):
            best = Mark(*candidate)
    return best
