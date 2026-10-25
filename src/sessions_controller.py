"""The controller's Sessions half: scans the recent Claude Code Sessions with the settings
the Workspace file holds now, draws the Sessions tab, and tells a Board which of its
Tickets a Session is on. Imports no GUI toolkit.

    sessions = SessionsTab(workspace, workspace_file)
    sessions.view = window.add_sessions_view(COLUMNS)   # while the tab is open
    sessions.draw()             # scan, then redraw the Sessions tab
    board.show_sessions(sessions.titles())               # scan, then mark a Board
    sessions.sync_settings()    # before saving the Workspace

Off the UI thread, a scan splits in two: `reader()` takes the settings on the UI thread
and gives `read`, which reads the transcripts on the runner's thread and changes
nothing; `take(scan)` then keeps its result, on the UI thread:

    runner.submit(sessions.reader(), lambda scan: sessions.draw(sessions.take(scan)))

Each scan also finds the Builders (`src/model/builders.py`): `scan.builder_for(ticket)`
feeds a Board scan's marks, `scan.activity(snapshot)` gives each row's Activity, and
`scan.stalled(snapshot)` the rows among them whose Builder is Stalled.

The Sessions view is a `SessionsViewProtocol` (`src/view_protocols.py`): this controller
calls only its show(rows, caption, selected row index or None)."""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Optional

from src.clock import SystemClock
from src.model.builders import (header_builders, match_builders, scan_builders,
                                subagents_by_session)
from src.model.marks import stopped
from src.model.sessions import list_transcripts, scan_sessions
from src.model.sessions_tab import (PROJECTS_KEY, WINDOW_KEY, builder_row, match_sessions,
                                    session_row, sessions_settings)
from src.view_protocols import SessionsViewProtocol
from src.workspace import load_workspace


@dataclass(frozen=True)
class SessionScan:
    """One scan of the Sessions: what was found, when, where, and over what window, and
    the Builders among them (`src/model/builders.py`)."""
    sessions: list
    now: datetime
    projects_dir: Path
    window: timedelta
    builders: tuple = ()
    builder_for: object = None   # Ticket -> its Builder or None, from match_builders

    def activity(self, snapshot):
        """`Ticket path -> Activity text` ("Editing shell.gd · 4s") for every Ticket of
        `snapshot` whose Builder is working it now. A finished Builder shows none."""
        return {path: builder.activity_text(self.now) for path, builder in self._working(snapshot)}

    def stalled(self, snapshot):
        """The Ticket paths of `snapshot` whose Activity is shown and whose Builder is
        Stalled at this scan's `now` (08)."""
        return frozenset(path for path, builder in self._working(snapshot)
                         if builder.stalled(self.now))

    def builder_on(self, tracked):
        """The Builder working `tracked` (a TrackedTicket) now, with an Activity to show,
        or None. None too once the Ticket has stopped being built (its mark Finished,
        Landed or Dropped, `marks.stopped`), so old Activity never sits on a finished
        row, whether its Builder is a subagent or a Session that names the Ticket."""
        if not self.builder_for or stopped(tracked.mark):
            return None
        builder = self.builder_for(tracked.ticket)
        return builder if builder is not None and builder.activity_text(self.now) else None

    def last_message(self, tracked):
        """The last message of the Builder working `tracked` (a TrackedTicket) now, or
        None when none is (or it has finished, or the Ticket has stopped being built, or
        it has said nothing in its transcript's tail)."""
        if not self.builder_for or stopped(tracked.mark):
            return None
        builder = self.builder_for(tracked.ticket)
        return None if builder is None or builder.finished else builder.last_message

    def _working(self, snapshot):
        """`(Ticket path, Builder)` for each Ticket of `snapshot` with an Activity shown."""
        if snapshot is None:
            return
        for tracked in snapshot.tickets():
            builder = self.builder_on(tracked)
            if builder is not None:
                yield tracked.ticket.path, builder

    def header(self, snapshot):
        """`{Effort path: ((transcript, text), ...)}` for every Effort of `snapshot` with
        Builders working no Ticket of it (see `header_builders`)."""
        if snapshot is None:
            return {}
        shown = {}
        for effort in snapshot.efforts:
            found = self.header_for(effort)
            if found:
                shown[effort.path] = tuple(found)
        return shown

    def header_for(self, effort):
        """`[(transcript, text)]` for each Builder `effort`'s header shows: one working in
        it on no Ticket of it, not finished. The text is its description and its Activity:
        "Fix the code review's findings · Running tests · 4s"."""
        found = []
        for b in header_builders(self.builders, effort):
            activity = b.activity_text(self.now)
            found.append((b.transcript, f"{b.description} · {activity}" if activity
                          else b.description))
        return found

    def caption(self):
        """The line over the Sessions tab. An orchestrator kept for its working subagents
        though quiet for longer than the window is counted apart, not as recent."""
        minutes = int(self.window.total_seconds() // 60)
        n = sum(1 for s in self.sessions if self.now - s.modified <= self.window)
        kept = len(self.sessions) - n
        waiting = f", and {kept} waiting on {'its' if kept == 1 else 'their'} subagents"
        return (f"{n} session{'' if n == 1 else 's'} with a message in the last {minutes} min"
                f"{waiting if kept else ''}"
                f"   ·   {self.projects_dir}   ·   scanned {self.now:%H:%M:%S}")

    @cached_property   # a scan never changes
    def _listed(self):
        """`[(transcript, cells)]`, one per row of the Sessions tab: each Session, newest
        first, and under an orchestrator each of its recent subagent Builders."""
        under = subagents_by_session(self.builders, self.now, self.window)
        listed = []
        for s in self.sessions:
            listed.append((s.path, session_row(s, self.now)))
            listed += [(b.transcript, builder_row(b, s.project, self.now))
                       for b in under.get(s.path, ())]
        return listed

    def rows(self):
        return [cells for _, cells in self._listed]

    def index_of(self, transcript):
        """The row of the Session or subagent Builder whose transcript is `transcript`, or
        None when it is not listed."""
        return next((i for i, (path, _) in enumerate(self._listed) if path == transcript), None)

    def titles(self):
        """`path -> title of the newest Session on it, or None`, for a Board's Session column."""
        match = match_sessions(self.sessions)

        def title_for(path):
            session = match(path)
            return session.title if session else None
        return title_for


class SessionsTab:
    def __init__(self, workspace, workspace_file, clock=None):
        """`clock.now()` gives the time a scan is made at (src/clock.py)."""
        self.workspace = workspace
        self.workspace_file = Path(workspace_file)
        self.clock = clock or SystemClock()
        self.view: Optional[SessionsViewProtocol] = None   # the Sessions tab's view while it is open
        self.drawn_by = None  # the view that has drawn a scan, None until one has
        self.scans = 0
        self.last = None      # the last SessionScan taken
        self.selected = None  # the transcript of the row shown selected, None for none
        self._settings_stamp = None   # the Workspace file's (mtime, size) when last read
        self._on_disk = {}            # its sessions keys as then read

    def scan(self):
        """Scan the Sessions with the window and folder the Workspace file gives now, so
        an owner's edit to the file counts on the next scan."""
        return self.take(self.reader()())

    def reader(self):
        """On the UI thread: take the sessions settings from the Workspace file now, and
        give the file-reading half of a scan, `read() -> SessionScan`, which reads only
        transcripts and changes nothing, so it is safe off the UI thread. Hand its result
        to `take`. A transcript unchanged since the last scan taken is not read again.
        (The Workspace file is taken here, not in `read`, so that a save on the UI thread
        never meets the file held open by another thread. It is only statted here, and
        read again only when it has changed: see `sync_settings`.)"""
        projects_dir, window = sessions_settings(self.sync_settings())
        last = self.last
        same = last is not None and last.projects_dir == projects_dir
        previous = last.sessions if same else ()
        previous_builders = last.builders if same else ()
        clock = self.clock

        def read():
            now = clock.now()
            try:
                listing = list_transcripts(projects_dir)
                sessions = scan_sessions(projects_dir, now, window, previous, listing)
                builders = tuple(scan_builders(projects_dir, now, window, sessions,
                                               previous_builders, listing))
                # An orchestrator waiting on its subagents may be quiet for longer than
                # the window: it is listed while one of them is.
                quiet = set(subagents_by_session(builders, now, window)) - {s.path for s in sessions}
                if quiet:
                    sessions = scan_sessions(projects_dir, now, window, [*previous, *sessions],
                                             listing, keep=quiet)
            except OSError:
                sessions, builders = [], ()
            return SessionScan(sessions, now, projects_dir, window, builders,
                               match_builders(builders))
        return read

    def take(self, scan):
        """The UI-thread half of `scan`: keep the scan. Returns it."""
        self.scans += 1
        self.last = scan
        return scan

    def draw(self, scan=None):
        """Redraw the open Sessions tab from `scan`, or from a scan made now."""
        scan = scan or self.scan()
        selected = scan.index_of(self.selected) if self.selected is not None else None
        self.view.show(scan.rows(), scan.caption(), selected)
        self.drawn_by = self.view

    def titles(self):
        """Scan, then give the Session column's lookup (see SessionScan.titles)."""
        return self.scan().titles()

    def sync_settings(self):
        """Copy the sessions keys from the Workspace file into the Workspace in memory, so
        the owner's edit is used now and kept by the next save. Returns the Workspace.

        The file is read again only when it has changed since it was last read (its
        modification time or size moved: an owner's edit, or a save), so a poll with
        nothing changed costs one stat on the UI thread, not a read."""
        try:
            info = os.stat(self.workspace_file)
            stamp = (info.st_mtime_ns, info.st_size)
        except OSError:
            stamp = None
        if stamp is None or stamp != self._settings_stamp:
            on_disk = load_workspace(self.workspace_file).settings
            self._settings_stamp = stamp
            self._on_disk = {k: on_disk[k] for k in (WINDOW_KEY, PROJECTS_KEY) if k in on_disk}
        for key in (WINDOW_KEY, PROJECTS_KEY):
            if key in self._on_disk:
                self.workspace.settings[key] = self._on_disk[key]
            else:
                self.workspace.settings.pop(key, None)
        return self.workspace
