"""Stand-ins for the window and its views, so the controller runs with no GUI, plus a
Workspace file that keeps every test away from the owner's real Claude folder.

`FakeWindow` and its views record what the controller told them; the poll timer fires
only when a test calls `FakeWindow.tick`."""

import json
from pathlib import Path

from src.runner import SameThreadRunner


def write_workspace(path, projects_dir, **settings):
    """Write a Workspace file at `path` whose sessions folder is `projects_dir`, so a scan
    never reads the real `~/.claude/projects`. Extra keys go in as given."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.update(settings, claude_projects_dir=str(projects_dir))
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class FakeBoard:
    """Records what it was told to draw in `told`: `(call name, args)`, in order."""

    def __init__(self):
        self.sort = None
        self.detail_pane = None
        self.columns = {}
        self.snapshots = 0
        self.session_for = None
        self.activity = None      # Ticket path -> Activity text, as last shown
        self.stalled = set()      # Ticket paths whose Activity shows Stalled
        self.builders = None      # Effort path -> its header Builders, as last shown
        self.header_line = None   # the Board's header line, as last shown ("" for none)
        self.on_sort = None       # the controller sets these three callbacks
        self.on_activity = None
        self.on_builder = None
        self.told = []

    def show_snapshot(self, snapshot, effort_name, selected):
        self.snapshots += 1
        self.told.append(("show_snapshot", (snapshot, effort_name, selected)))

    def show_unreadable(self, folder, reason):
        self.told.append(("show_unreadable", (folder, reason)))

    def show_effort(self, effort_name, selected):
        self.told.append(("show_effort", (effort_name, selected)))

    def show_detail(self, detail):
        self.told.append(("show_detail", (detail,)))

    def apply_changes(self, snapshot, effort_name, selected, changes):
        self.told.append(("apply_changes", (snapshot, effort_name, selected, changes)))

    def flash(self, paths):
        self.told.append(("flash", (paths,)))

    def show_sessions(self, session_for):
        self.session_for = session_for
        self.told.append(("show_sessions", (session_for,)))

    def show_activity(self, activity, stalled=frozenset()):
        self.activity = dict(activity)
        self.stalled = set(stalled)
        self.told.append(("show_activity", (activity, stalled)))

    def show_builders(self, builders):
        self.builders = dict(builders)
        self.told.append(("show_builders", (builders,)))

    def select_row(self, path):
        self.told.append(("select_row", (path,)))

    def show_header_line(self, text):
        self.header_line = text
        self.told.append(("show_header_line", (text,)))

    def set_sort(self, column, descending):
        self.sort = (column, descending)

    def set_detail_pane(self, shown):
        self.detail_pane = shown

    def set_column(self, key, shown):
        self.columns[key] = shown


class HeldRunner:
    """A runner that holds each submitted scan until the test calls `release()`, which runs
    them all, in order, on the test's thread: a scan "in flight" with no real thread."""

    def __init__(self):
        self.held = []

    def submit(self, work, done, always=None, failed=None):
        self.held.append((work, done, always, failed))

    def release(self):
        held, self.held = self.held, []
        for work, done, always, failed in held:
            SameThreadRunner().submit(work, done, always=always, failed=failed)


class FakeClock:
    """A clock whose time the test sets: `clock.time += timedelta(...)`."""

    def __init__(self, time):
        self.time = time

    def now(self):
        return self.time


class FakeSessions:
    def __init__(self):
        self.rows, self.caption, self.selected = [], "", None

    def show(self, rows, caption, selected=None):
        """`selected`: the index of the row shown selected and in view, or None."""
        self.rows, self.caption, self.selected = rows, caption, selected


class FakeWindow:
    def __init__(self):
        self.boards, self.fronted, self.tabs = [], None, ([], None)
        self.themes = []
        self.timer = None
        self.folder = None   # what ask_folder gives: None as when the owner cancels

    def set_theme(self, palette):
        self.themes.append(palette["name"])

    def ask_folder(self):
        return self.folder

    def close(self): pass
    def show_scans(self, text): pass

    def after(self, ms, fn):
        self.timer = fn
        return fn

    def after_cancel(self, timer):
        self.timer = None

    def tick(self):
        self.timer()

    def set_tabs(self, titles, active):
        self.tabs = (list(titles), active)

    def front_board(self, board):
        self.fronted = board

    def add_board(self, tab):
        self.boards.append(FakeBoard())
        return self.boards[-1]

    def add_sessions_view(self, headings):
        self.boards.append(FakeSessions())
        return self.boards[-1]

    def remove_board(self, board):
        self.boards.remove(board)
