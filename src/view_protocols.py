"""The view seams: what the controllers expect of the views, as `typing.Protocol` classes.

The controllers (`src/controller.py`, `src/sessions_controller.py`) and the composition
root talk to the views only through these three. Each holds every method and settable
callback they use on that view today, so a controller's expectations are code, not prose:

- `MainWindowProtocol`: the main window (`src/views/window.py` `MainWindow`; in tests
  `tests/fakes.py` `FakeWindow`). It owns the tab strip and stacks the views.
- `BoardViewProtocol`: one tab's Board (`src/views/board_view.py` `BoardView`;
  `FakeBoard`), returned by `MainWindowProtocol.add_board`.
- `SessionsViewProtocol`: the Sessions tab (`src/views/sessions_view.py` `SessionsView`;
  `FakeSessions`), returned by `MainWindowProtocol.add_sessions_view`.

They live here, beside the controllers and outside the views, so that naming a view's
type never imports a view (or a GUI toolkit). This module imports only `typing`.

The guard `tests/guards/test_protocols.py` checks that the real views and the fakes
satisfy them: every member by name, and for each method its arity (the calls written
here must bind). A parameter before `/` is passed by position, so only its place counts;
one after it the controller passes by keyword, so its name counts too. A view or fake
that gains a method the controllers now call needs it added here first.
"""

from typing import Callable, Optional, Protocol


class SessionsViewProtocol(Protocol):
    """The Sessions tab's view."""

    def show(self, rows, caption, selected=None, /):
        """Draw `rows` (each a list of cell texts) under `caption`. `selected`: the index of
        the row shown selected and scrolled into view, or None."""


class BoardViewProtocol(Protocol):
    """One tab's Board: the Effort sidebar, the Ticket table and the detail pane."""

    on_sort: Optional[Callable]       # set to on_sort(column): a column header was clicked
    on_activity: Optional[Callable]   # on_activity(ticket path): a row's Activity was clicked
    on_builder: Optional[Callable]    # on_builder(transcript): a header Builder was clicked

    def show_snapshot(self, snapshot, effort_name, selected, /):
        """Draw a whole Snapshot, showing the Effort `effort_name`, `selected` (a path or
        None) selected."""

    def show_unreadable(self, folder, reason, /):
        """Show why the Source `folder` could not be read, in place of the Board."""

    def show_effort(self, effort_name, selected, /):
        """Show another Effort of the Snapshot already drawn."""

    def apply_changes(self, snapshot, effort_name, selected, changes, /):
        """Redraw only what `changes` (a `RowChanges`) names, from `snapshot`."""

    def flash(self, paths, /):
        """Flash the rows at `paths` (their Status changed)."""

    def show_sessions(self, session_for, /):
        """Mark the Session column: `session_for(path)` is a title or None."""

    def show_activity(self, activity, /, stalled=frozenset()):
        """Each row's Activity, `{ticket path: text}`; `stalled` the paths shown Stalled."""

    def show_builders(self, builders, /):
        """The Efforts' header Builders, `{effort path: ((transcript, text), ...)}`."""

    def show_header_line(self, text, /):
        """Show `text` as the Board's header line ("" for none)."""

    def show_detail(self, detail, /):
        """Show a file's `Detail` in the detail pane."""

    def select_row(self, path, /):
        """Click the Ticket row at `path`, as the owner would (`--select`)."""

    def set_sort(self, column, descending, /):
        """Sort the table by `column`."""

    def set_detail_pane(self, shown, /):
        """Show or hide the detail pane."""

    def set_column(self, key, shown, /):
        """Show or hide the optional column `key` (today "area")."""


class MainWindowProtocol(Protocol):
    """The main window: the tab strip, the stacked views and the toolkit's timer."""

    def set_theme(self, palette, /):
        """Restyle every view in place in `palette`."""

    def set_tabs(self, titles, active, /):
        """Draw the tab strip: `titles` in order, the one at index `active` (or None) in front."""

    def add_board(self, tab, /) -> BoardViewProtocol:
        """Build and stack a Board view for `tab` (a controller `Tab`)."""

    def add_sessions_view(self, headings, /) -> SessionsViewProtocol:
        """Build and stack the Sessions tab's view with column `headings`."""

    def remove_board(self, view, /):
        """Drop a Board or Sessions view."""

    def front_board(self, view, /):
        """Bring a Board or Sessions view to the front; None shows the empty hint."""

    def ask_folder(self, /) -> Optional[str]:
        """Ask the owner for a Source folder: its path, or None if they cancel."""

    def close(self, /):
        """Close the window."""

    def show_scans(self, text, /):
        """Show the per-tab scan counter after the title ("" for none)."""

    def after(self, ms, fn, /):
        """Call `fn` once on the UI thread after `ms` milliseconds; gives a timer id."""

    def after_cancel(self, timer, /):
        """Cancel the timer `timer`."""
