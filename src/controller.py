"""The controller: owns the open tabs, scans each tab's Source folder, keeps the Workspace
file in step, and tells the views what to draw. Imports no GUI toolkit.

    controller = BoardController(workspace, workspace_file, window)
    controller.start()             # reopen the saved tabs, start the poll timer

The window calls back on user actions: File (`new_tab`, `close_tab`, `reopen_last`,
`quit`), the tab strip (`front`), a Board (`select_effort`, `select_file`, `sort_by`),
View (`set_palette`, `toggle_view`, `view_on`, `refresh_now`, `open_sessions`).
`front_tab()` is the fronted Board's Tab, or None while no Board is in front.

One poll timer rescans only the fronted tab every `poll_interval_ms` (Workspace file).
A rescan diffs the new Snapshot with the last and hands the view only what changed; it
re-marks the Board's Session column too, when a mark changed. Its file reading runs on
the runner, off the UI thread, and its result is drawn when the runner hands it back.
The Sessions tab sits last in the tab strip, is not saved to the Workspace, and is
scanned and drawn by `src/sessions_controller.py`.

An unexpected error in a scan, or in drawing it, is caught where the runner hands the
work back: the tab shows it as unreadable, the poll goes on, and the error is written to
`error.log` beside the Workspace file (src/error_log.py). A tab's first scan, and the
Sessions tab's first draw, run under the same guard, so one bad folder or transcript never
stops start-up.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

from src.clock import SystemClock
from src.error_log import ErrorLog
from src.model.detail import read_detail
from src.model.effort import scan
from src.model.sessions_tab import COLUMNS
from src.model.snapshot_diff import diff_snapshots
from src.model.sorting import DEFAULT_SORT, next_sort
from src.model.view_settings import AREA_COLUMN, DETAIL_PANE, is_on, toggle
from src.palette import load_palette
from src.runner import SameThreadRunner
from src.sessions_controller import SessionsTab
from src.view_protocols import MainWindowProtocol
from src.workspace import save_workspace

SESSIONS_TITLE = "Sessions"
ERROR_LOG_NAME = "error.log"   # beside the Workspace file (src/error_log.py)

# Polling (07): the fronted tab is rescanned every `poll_interval_ms` (Workspace file).
POLL_KEY = "poll_interval_ms"
POLL_DEFAULT_MS = 1000
POLL_MIN_MS = 100
SCAN_COUNTER_KEY = "show_scan_counter"


def restore_palette(workspace):
    """The palette to launch in: the saved choice, else graphite when none is saved or the
    saved one is unknown or broken. The Workspace is left naming the palette in use, in
    memory only (start-up never rewrites the Workspace file)."""
    palette = load_palette(workspace.palette)
    workspace.palette = palette["name"]
    return palette


@dataclass
class Shown:
    """What a tab's Board view was last told from the Sessions scan, so that a poll tells
    it only what changed, and a new view is told all of it at once."""
    session_for: object = None   # the Session column's last lookup, `path -> title or None`
    marks: dict = None           # Ticket path -> its Session title, None until marked
    activity: dict = field(default_factory=dict)   # Ticket path -> its Builder's Activity
    stalled: frozenset = frozenset()               # Ticket paths whose Builder is Stalled
    detail: object = None        # the selected file's Detail as read, without the message
    message: str = None          # the selected Ticket's Builder's last message
    builders: dict = field(default_factory=dict)   # Effort path -> its header Builders
    header_line: str = ""        # the Board's header line ("main not read: ..."), "" for none


@dataclass
class Tab:
    """One open Board: its Source folder, its last scan and what is selected in it."""
    folder: Path
    view: object = None          # the window's Board view for this tab
    snapshot: object = None      # the last Snapshot, None until scanned or when unreadable
    error: str = ""              # why the folder could not be read, "" when it could
    effort: str = ""             # name of the Effort shown on the right
    selected: Path = None        # path of the selected Ticket, Map or Spec
    scans: int = 0               # how many times this tab has been scanned
    sort: tuple = DEFAULT_SORT   # (column, descending), kept across rescans and new views
    drawn_by: object = None      # the view that has drawn a whole Snapshot, None until one has
    shown: Shown = field(default_factory=Shown)   # what its view was told beyond the Snapshot
    scanning: bool = False       # a scan of this tab is on the runner and not yet back

    @property
    def title(self):
        return self.folder.name or str(self.folder)


class BoardController:
    """`window` is a `MainWindowProtocol`, its `add_board` gives each tab a
    `BoardViewProtocol` (whose on_sort, on_activity and on_builder this controller sets),
    and its `add_sessions_view` the Sessions tab's `SessionsViewProtocol`: every method this
    controller calls on a view is listed there (`src/view_protocols.py`), and the guard
    `tests/guards/test_protocols.py` holds the real views and the fakes to it.
    `runner` provides submit(work, done, always=None, failed=None): work() runs off the UI
    thread and done(result) runs back on it, after always() (src/runner.py). It defaults
    to SameThreadRunner, which runs the work at once; the app passes a BackgroundRunner.
    `first_runner` is the same, for a tab's first scan and the Sessions tab's first draw,
    which run here and now as there is nothing to show till they land; it defaults to
    SameThreadRunner.
    `clock` provides now() (src/clock.py); it defaults to SystemClock."""

    def __init__(self, workspace, workspace_file, window: MainWindowProtocol, runner=None,
                 clock=None, first_runner=None):
        self.workspace = workspace
        self.workspace_file = Path(workspace_file)
        self.window = window
        self.runner = runner or SameThreadRunner()
        self.first_runner = first_runner or SameThreadRunner()
        self.clock = clock or SystemClock()
        self.error_log = ErrorLog(self.workspace_file.parent / ERROR_LOG_NAME)
        self.tabs = []
        self._poll_id = None          # the pending poll timer
        self.sessions = SessionsTab(workspace, workspace_file, self.clock)
        self.sessions_fronted = False
        self._sessions_scanning = False   # a Sessions-only scan is on the runner

    # ---------- start-up ----------
    def start(self):
        """Reopen the saved tabs, fronting the saved one. (The window is built in the
        saved palette before this.)"""
        for folder in self.workspace.folders:
            self._add_tab(folder)
        self._show_front()
        self._schedule_poll()

    # ---------- File menu ----------
    def new_tab(self, folder=None):
        """Open a tab on `folder`, or on a folder the owner picks; nothing if they cancel."""
        folder = folder or self.window.ask_folder()
        if not folder:
            return
        folder = Path(folder).resolve()
        self.workspace.open_tab(folder)
        self._add_tab(folder)
        self.sessions_fronted = False
        self._changed()

    def close_tab(self, index=None):
        sessions_index = len(self.tabs) if self.sessions.view is not None else None
        if (index is None and self.sessions_fronted) or index == sessions_index:
            self.close_sessions()
            return
        index = self.workspace.active if index is None else index
        if index is None or not 0 <= index < len(self.tabs):
            return
        tab = self.tabs.pop(index)
        self.window.remove_board(tab.view)
        self.workspace.close_tab(index)
        self._changed()

    def reopen_last(self):
        index = self.workspace.reopen_last()
        if index is not None:
            self._add_tab(self.workspace.folders[index])
            self.sessions_fronted = False
            self._changed()

    def quit(self):
        if self._poll_id is not None:
            self.window.after_cancel(self._poll_id)
            self._poll_id = None
        self.save()
        self.window.close()

    # ---------- tabs ----------
    def front(self, index):
        """Bring tab `index` to the front and rescan it. The Sessions tab, when open, is
        the one after the last Board."""
        if self.sessions.view is not None and index == len(self.tabs):
            if not self.sessions_fronted:
                self.sessions_fronted = True
                self._show_front()
                self._schedule_poll()
            return
        if 0 <= index < len(self.tabs) and (index != self.workspace.active or self.sessions_fronted):
            self.sessions_fronted = False
            self.workspace.active = index
            self._changed()
            self._schedule_poll()  # next poll a full interval after this fronting scan

    def rescan(self, index):
        """Scan tab `index`'s Source folder and redraw what changed on its Board since the
        last scan: nothing when nothing changed, else only the changed rows, flashing those
        whose Status changed. A folder that has gone missing keeps its tab, with an
        unreadable message in place of the Board.

        The scan runs on the runner and its result is drawn when the runner hands it
        back, so the window keeps answering meanwhile. Only a tab's first scan runs here
        and now, as the Board has nothing to show until it lands. A tab whose scan is
        still in flight is not scanned again: the next poll waits for it."""
        tab = self.tabs[index]
        if tab.drawn_by is not tab.view and tab.snapshot is not None:
            self._draw_whole(tab, tab.snapshot)   # a new view shows the last scan at once
        if tab.scanning:
            return
        tab.scans += 1
        self._show_scans()
        folder, previous, read_sessions = tab.folder, tab.snapshot, self.sessions.reader()
        branch = self.workspace.branch(folder)
        first = tab.scans == 1   # runs here, on the UI thread, so it runs no git

        def work():
            # The Sessions first: a Builder's finished flag counts towards the marks.
            session_scan = read_sessions()
            return (self._read_folder(folder, previous, session_scan.builder_for,
                                      git=not first, branch=branch), session_scan)
        def failed(err):
            self._scan_failed(tab, err)
        if first:   # under the same guard, so one bad folder never stops start-up
            self.first_runner.submit(work, lambda result: self._take_scan(tab, result),
                                     failed=failed)
            return
        tab.scanning = True

        def back():   # even when the scan raised: the next poll scans again
            tab.scanning = False
        self.runner.submit(work, lambda result: self._scan_landed(tab, result), always=back,
                           failed=failed)

    def _scan_failed(self, tab, err):
        """An unexpected error in `tab`'s scan, or in drawing it, caught where the work is
        handed back: the tab shows it as unreadable, and the next poll scans again."""
        self.error_log.write(self.clock.now(), tab.folder, err)
        if not any(t is tab for t in self.tabs):    # closed while its scan ran
            return
        tab.snapshot, tab.error, tab.drawn_by = None, f"{type(err).__name__}: {err}", None
        tab.view.show_unreadable(tab.folder, tab.error)

    @staticmethod
    def _read_folder(folder, previous, builder_for=None, git=True, branch=None):
        """`(snapshot, "")`, or `(None, why)` when the folder cannot be read. Reads files
        (and with `git`, main's commit subjects when main's tip moved, main being the
        tab's `branch` setting when set), so it is safe off the UI thread."""
        try:
            if not folder.is_dir():
                raise FileNotFoundError("the folder is missing")
            return scan(folder, previous, builder_for, git, branch), ""
        except OSError as err:
            return None, getattr(err, "strerror", None) or str(err)

    def _scan_landed(self, tab, result):
        if any(t is tab for t in self.tabs):    # not closed while its scan ran
            self._take_scan(tab, result)

    def _take_scan(self, tab, result):
        """Draw one scan's result on `tab`'s Board, on the UI thread."""
        (snapshot, error), session_scan = result
        self.sessions.take(session_scan)
        if snapshot is None:
            tab.snapshot, tab.error = None, error
            tab.drawn_by = None
            tab.view.show_unreadable(tab.folder, tab.error)
            return
        old, tab.snapshot, tab.error = tab.snapshot, snapshot, ""
        names = [e.name for e in snapshot.efforts]
        if tab.effort not in names:
            tab.effort = names[0] if names else ""
        changes = diff_snapshots(old, snapshot, tab.effort)
        if tab.drawn_by is not tab.view:
            # This view has never drawn a Snapshot (new tab, folder back).
            self._draw_whole(tab, snapshot)
            if old is not None:
                tab.view.flash(changes.flash)
        elif changes:
            tab.view.apply_changes(snapshot, tab.effort, tab.selected, changes)
        # The Session column (10) is checked on every scan, since sessions change without
        # the Effort's files changing, but re-marked only when a Ticket's mark changed.
        # Each row's Activity likewise.
        self._mark_sessions(tab, session_scan.titles())
        self._show_activity(tab, session_scan)
        self._show_header(tab, session_scan)
        self._show_header_line(tab, snapshot)

    def _show_header_line(self, tab, snapshot):
        """Tell the view its header line when it changes: "main not read: <reason>" while
        main history carries an error (src/model/main_branch.py), else none."""
        error = snapshot.main.error if snapshot.main is not None else ""
        line = f"main not read: {error}" if error else ""
        if line != tab.shown.header_line:
            tab.shown.header_line = line
            tab.view.show_header_line(line)

    def _draw_whole(self, tab, snapshot):
        tab.view.show_snapshot(snapshot, tab.effort, tab.selected)
        shown = tab.shown
        tab.drawn_by, shown.marks = tab.view, None
        if shown.session_for is not None:
            self._mark_sessions(tab, shown.session_for)
        if shown.activity:
            tab.view.show_activity(shown.activity, stalled=shown.stalled)
        if shown.builders:
            tab.view.show_builders(shown.builders)
        if shown.header_line:
            tab.view.show_header_line(shown.header_line)

    def _show_header(self, tab, session_scan):
        """Tell the view each Effort's header Builders (09), when any has changed: one that
        finishes or stops drops out, and so off its header."""
        header = session_scan.header(tab.snapshot)
        if header != tab.shown.builders:
            tab.shown.builders = header
            tab.view.show_builders(header)

    def _show_activity(self, tab, session_scan):
        """Tell the view each row's Activity and which of them are Stalled, when any has
        changed: a Ticket no longer being built drops out of both, and so off its row."""
        activity = session_scan.activity(tab.snapshot)
        stalled = session_scan.stalled(tab.snapshot)
        shown = tab.shown
        if activity != shown.activity or stalled != shown.stalled:
            shown.activity, shown.stalled = activity, stalled
            tab.view.show_activity(activity, stalled=stalled)
        self._show_last_message(tab, session_scan)

    def _mark_sessions(self, tab, session_for):
        marks = {t.ticket.path: session_for(t.ticket.path) for t in tab.snapshot.tickets()}
        tab.shown.session_for = session_for
        if marks != tab.shown.marks:
            tab.shown.marks = marks
            tab.view.show_sessions(session_for)

    # ---------- polling ----------
    def poll_interval(self):
        """Milliseconds between scans of the fronted tab, from the Workspace file."""
        return max(self.workspace.setting(POLL_KEY, POLL_DEFAULT_MS), POLL_MIN_MS)

    def _schedule_poll(self):
        """One timer for the whole app: it rescans only the fronted tab, so a tab behind
        it schedules nothing."""
        if self._poll_id is not None:
            self.window.after_cancel(self._poll_id)
        self._poll_id = self.window.after(self.poll_interval(), self._poll)

    def _poll(self):
        """One tick: rescan the fronted Board (which re-marks its Session column), or
        redraw the Sessions tab when that is in front."""
        self._poll_id = None
        try:
            if self.sessions_fronted:
                self.poll_sessions()
            elif self.front_tab() is not None:
                self.rescan(self.workspace.active)
        finally:
            self._schedule_poll()

    def _show_scans(self):
        """The builder's per-tab scan counter, in the window title, when the Workspace
        setting `show_scan_counter` is on."""
        if self.workspace.setting(SCAN_COUNTER_KEY, False):
            self.window.show_scans("  ".join(f"{t.title}: {t.scans} scans" for t in self.tabs))

    def front_tab(self):
        """The fronted Tab, or None when no Board is in front (no tab open, or the
        Sessions tab fronted)."""
        active = self.workspace.active
        return None if active is None or self.sessions_fronted else self.tabs[active]

    # ---------- Sessions tab ----------
    def open_sessions(self):
        """View → Sessions: open the one Sessions tab, or front it if it is open."""
        if self.sessions.view is None:
            self.sessions.view = self.window.add_sessions_view(COLUMNS)
        self.sessions_fronted = True
        self._show_front()

    def open_activity(self, tab, path):
        """A click on the Activity of the Ticket row at `path`: open its Builder's Session
        (see open_session). Nothing when the row shows no Activity."""
        scan = self.sessions.last
        if scan is None or not scan.builder_for or tab.snapshot is None:
            return
        tracked = tab.snapshot.find(path)
        builder = scan.builder_on(tracked) if tracked is not None else None
        if builder is not None:
            self.open_session(builder.transcript)

    def open_session(self, transcript):
        """Open the Sessions tab, or front it, with the Session or subagent Builder whose
        transcript is `transcript` selected and in view: a click on a row's Activity or on
        a header Builder. Drawn at once from the last scan, which listed it; the poll then
        rescans as usual."""
        self.sessions.selected = transcript
        if self.sessions.view is None:
            self.sessions.view = self.window.add_sessions_view(COLUMNS)
        self.sessions_fronted = True
        if self.sessions.last is not None:
            self.sessions.draw(self.sessions.last)
        self._show_front()
        self._schedule_poll()

    def close_sessions(self):
        if self.sessions.view is None:
            return
        self.window.remove_board(self.sessions.view)
        self.sessions.view, self.sessions_fronted = None, False
        self._show_front()

    def poll_sessions(self):
        """Rescan the Sessions and redraw the Sessions tab, or the fronted Board's Session
        column. Nothing when neither is in front. The poll calls it for the Sessions tab.
        The scan runs on the runner, as a Board's does; a scan in flight is not doubled.
        The Sessions are scanned only here and in a Board's rescan: when the Sessions tab
        or a Board's Session column will show them."""
        def failed(err):   # logged; the Sessions shown stay as they were till the next poll
            self.error_log.write(self.clock.now(), SESSIONS_TITLE, err)
        if self.sessions_fronted and self.sessions.drawn_by is not self.sessions.view:
            # Nothing drawn yet: scan here and now, under the same guard as a poll's.
            self.first_runner.submit(self.sessions.reader(),
                                     lambda scan: self.sessions.draw(self.sessions.take(scan)),
                                     failed=failed)
            return
        if self._sessions_scanning:
            return
        if self.sessions_fronted:
            def landed(scan):
                if self.sessions.view is not None:
                    self.sessions.draw(scan)
        else:
            tab = self.front_tab()
            if tab is None or tab.snapshot is None:
                return

            def landed(scan):
                if any(t is tab for t in self.tabs) and tab.snapshot is not None:
                    self._mark_sessions(tab, scan.titles())
                    self._show_activity(tab, scan)
                    self._show_header(tab, scan)
        self._sessions_scanning = True

        def back():   # even when the scan raised
            self._sessions_scanning = False
        self.runner.submit(self.sessions.reader(), lambda scan: landed(self.sessions.take(scan)),
                           always=back, failed=failed)

    # ---------- within a Board ----------
    def select_effort(self, tab, name):
        tab.effort = name
        tab.selected = None
        tab.view.show_effort(name, tab.selected)

    def select_file(self, tab, path):
        """A Ticket row, or the Effort's Map or Spec, was selected in `tab`. Its file is
        read now, never during a scan, and handed to the Board's detail pane."""
        tab.selected = Path(path)
        efforts = tab.snapshot.efforts if tab.snapshot else ()
        effort = next((e for e in efforts if e.name == tab.effort), None)
        tab.shown.detail = None
        if effort is not None:
            tab.shown.detail = read_detail(effort, tab.selected)
            self._show_detail(tab, self._last_message(tab, self.sessions.last))

    def _show_detail(self, tab, message):
        """Show the selected file's Detail as last read, with its Builder's `message`."""
        tab.shown.message = message
        tab.view.show_detail(replace(tab.shown.detail, last_message=message))

    def _last_message(self, tab, session_scan):
        """The last message of the Builder working `tab`'s selected Ticket, or None."""
        tracked = tab.snapshot.find(tab.selected) if tab.snapshot else None
        if tracked is None or session_scan is None:
            return None
        return session_scan.last_message(tracked)

    def _show_last_message(self, tab, session_scan):
        """Show the selected Ticket's detail again when its Builder's last message changed:
        the Detail as last read, so the poll reads no Ticket file on the UI thread."""
        if tab.selected is None or tab.shown.detail is None:
            return
        message = self._last_message(tab, session_scan)
        if message != tab.shown.message:
            self._show_detail(tab, message)

    # ---------- View menu ----------
    def set_palette(self, name):
        """Save the chosen palette and restyle the window in it, live: the window recolours
        every view in place, so nothing is rebuilt, rescanned or read again. An unknown or
        broken palette gives graphite, as at launch."""
        palette = load_palette(name)
        self.workspace.palette = palette["name"]
        self.save()
        self.window.set_theme(palette)

    def refresh_now(self):
        """View → Refresh now: rescan the fronted tab (or the Sessions tab) at once."""
        if self.sessions_fronted:
            self.poll_sessions()
        elif self.workspace.active is not None:
            self.rescan(self.workspace.active)

    def view_on(self, key):
        """Whether a View toggle (DETAIL_PANE, AREA_COLUMN) is on."""
        return is_on(self.workspace, key)

    def toggle_view(self, key):
        """Flip a View toggle, save it, and show it on every Board."""
        toggle(self.workspace, key)
        self.save()
        for tab in self.tabs:
            self._apply_view(tab)

    # ---------- sorting ----------
    def sort_by(self, tab, column):
        """A click on `column`'s header: sort by it, or reverse it when already sorted."""
        tab.sort = next_sort(tab.sort, column)
        tab.view.set_sort(*tab.sort)

    # ---------- plumbing ----------
    def save(self):
        """Write the Workspace file, keeping the sessions settings as the file has them now,
        so an owner's edit made while the app runs is not overwritten."""
        self.sessions.sync_settings()
        save_workspace(self.workspace, self.workspace_file)

    def _add_tab(self, folder):
        tab = Tab(folder=Path(folder))
        self._new_view(tab)
        self.tabs.append(tab)

    def _new_view(self, tab):
        """Build `tab`'s Board view and give it the tab's sort and the View toggles."""
        tab.view = self.window.add_board(tab)
        tab.view.on_sort = lambda column: self.sort_by(tab, column)
        tab.view.on_activity = lambda path: self.open_activity(tab, path)
        tab.view.on_builder = self.open_session
        self._apply_view(tab)

    def _apply_view(self, tab):
        tab.view.set_sort(*tab.sort)
        tab.view.set_detail_pane(self.view_on(DETAIL_PANE))
        tab.view.set_column("area", self.view_on(AREA_COLUMN))

    def _changed(self):
        self.save()
        self._show_front()

    def _show_front(self):
        """Redraw the tab strip and front the active tab, rescanning it: a tab behind
        the front is not scanned until it is fronted."""
        active = self.workspace.active
        titles = [t.title for t in self.tabs]
        if self.sessions.view is not None:
            titles.append(SESSIONS_TITLE)
        self.window.set_tabs(titles, len(self.tabs) if self.sessions_fronted else active)
        if self.sessions_fronted:
            self.poll_sessions()
            self.window.front_board(self.sessions.view)
            return
        if active is None:
            self.window.front_board(None)
            return
        self.rescan(active)
        self.window.front_board(self.tabs[active].view)
