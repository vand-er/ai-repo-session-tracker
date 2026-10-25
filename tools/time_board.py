"""Time the Board against the 20 ms bar: drive the real window through every interaction
and report the median time from input to painted frame.

    python tools/time_board.py ~/code/my-repo --label before --out docs/evidence/fast-live-board/before-timing.md
    python tools/time_board.py SOURCE --shots docs/evidence/fast-live-board --label after
    python tools/time_board.py SOURCE --quick            # 3 runs each, for a builder's check
    python tools/time_board.py SOURCE --only sort,poll_changed --no-generated

Which run to start:
    Use --quick for a Builder's check of the whole table after a change: 3 runs per row and
    3 launches instead of 9 and 5, so faster but less exact. Not for before/after evidence.
    Use --only ROW[,ROW] to re-time just the rows a change touched, or the rows a run marked
    unreliable or failed, instead of timing the whole table again. The row names are listed
    at the end. Add --no-generated to skip the 400-Ticket folder too.
    An agent starts the run in the background once and waits for its notification: there
    is no need to poll it. The run queues behind any other run on this machine (a lock file
    in the temp folder; it prints "waiting for run <pid>" and gives up after 30 minutes),
    and its last line is `exit=<code>`, the process's exit code, non-zero on error.
    A row timed while the machine's CPU load is above 40% is still written, marked
    unreliable: re-time it with --only when the machine is quieter.
    The CPU load is machine-wide, less only the CPU time of the process taking the
    reading. So a window's rows leave out that window's own work, but the startup row
    and the run's average in the table's heading include the harness's own work: the
    windows and launches it starts.

It times two Source folders: the one given, and a generated one whose biggest Effort has
400 Tickets (made in a temp folder, removed after). Each runs in a fresh process with its
own window, opened on two tabs of that folder.

What "input" means here: the call a click makes (the controller's or Board view's public
method the click handler calls), or a real `<MouseWheel>` event for scrolling. What
"painted" means: after the toolkit's idle and update work (`update_idletasks`, then
`update`). The poll timer is set to a day, so it never fires inside a timing; the poll is
timed by calling Refresh now, which runs the same rescan. "Poll, one row changed" rewrites
one Ticket's Status line first, so the given folder's poll is timed on a temp copy of its
`.md` files (it is never written to).

The poll's scan runs on a background runner (ticket 03), so a poll's rows count UI-thread
time only: Refresh now handing the scan over, plus drawing its result when the runner
hands it back (the controller's `done`, then the paint after it). The time the scan
itself takes, off the UI thread, is reported in its own rows, which carry no bar. Every
other row starts with no scan out (settling waits for any to land), and a tab switch's
row times the switch, not the scan it hands over.

Startup is timed from launching a fresh `python` to the first painted window, on a
Workspace holding one tab on that folder.

It never reads or writes the owner's Workspace file: every window gets its own temp
Workspace file, and the env var points at a temp one too. It reads Claude Code's sessions
folder (`--claude-projects`, default the app's own default), as the app does.

Every window it opens (the timing windows, each startup launch, each `--shot`) opens on
the monitor that does not hold the owner's window, at the bottom of the z-order, and is
never activated or focused (src/views/placement.py). No interaction needs focus: the
clicks are the calls a click makes, and the wheel event is sent to a widget directly.
A covered window still paints, and PrintWindow still draws it for the stills.

While one interaction runs (seconds, on the 400-Ticket Effort today) the window cannot
answer Windows, which may title it "Not Responding". That is the slowness being timed,
not a hang: the next settle answers it.
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.model.marks import stopped  # noqa: E402  (needs the path above; imports no GUI)
from src.system import WINDOWS  # noqa: E402
from src.workspace import ENV_VAR  # noqa: E402

BAR_MS = 20.0
DAY_MS = 24 * 60 * 60 * 1000
FLASH_WAIT_S = 2.3     # longer than the table's flash, so an unflash never lands in a timing
GENERATED_TICKETS = 400

ROWS = (
    ("effort_switch", "Switch Effort (to the biggest)"),
    ("effort_reclick", "Re-click the Effort shown"),
    ("row_select", "Select a row"),
    ("sort", "Sort by a column"),
    ("toggle_area", "Toggle the Area column"),
    ("toggle_detail", "Toggle the detail pane"),
    ("theme", "Switch theme"),
    ("tab_board", "Switch tab: Board to Board"),
    ("tab_to_sessions", "Switch tab: Board to Sessions"),
    ("tab_from_sessions", "Switch tab: Sessions to Board"),
    ("scroll", "Scroll one wheel step"),
    ("poll_idle", "Poll, nothing changed"),
    ("poll_changed", "Poll, one row changed"),
    ("poll_activity", "Poll, a Builder's Activity changed"),
    ("click_activity", "Click a row's Activity (Sessions tab open behind)"),
    ("click_header_builder", "Click a header Builder (Sessions tab open behind)"),
    ("click_activity_opening", "Click a row's Activity, opening the Sessions tab (no bar: "
                               "builds the tab, as View → Sessions does)"),
    ("startup", "Startup to first painted window"),
    ("poll_idle_scan", "Poll, nothing changed: the scan, off the UI thread (no bar)"),
    ("poll_changed_scan", "Poll, one row changed: the scan, off the UI thread (no bar)"),
    ("poll_changed_controller", "Poll, one row changed: the controller's UI-thread share, "
                                "without the views' drawing"),
)
NO_BAR = {"poll_idle_scan", "poll_changed_scan", "click_activity_opening"}
SORT_KEYS = ("title", "type", "status", "blocked_by", "flag", "updated", "session", "num")
STATUS_LINE = re.compile(r"^(\s*(?:\*\*)?Status:(?:\*\*)?\s*)(\S+)(.*)$", re.IGNORECASE | re.MULTILINE)


# ---------------------------------------------------------------- the queue
LOCK_FILE = Path(tempfile.gettempdir()) / "wayfinder-board-timing.lock"
LOCK_TIMEOUT_S = 30 * 60
LOCK_POLL_S = 5.0
LOCK_EMPTY_GRACE_S = 10.0   # a lock naming no pid this long is a run that died making it


class LockTimeout(RuntimeError):
    """Another run held the lock for longer than the harness waits."""


def pid_alive(pid):
    """Whether a process with this pid is running. (On Windows `os.kill(pid, 0)` would kill
    it, so it asks the process's exit code instead.)"""
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.GetLastError() == 5             # access denied: it exists
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259                      # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _holder(path):
    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _create(path, pid):
    """Create the lock file holding `pid`, whole from the moment it exists: the pid is
    written to a file of this run's own, then linked to the lock's name, which fails if
    the lock exists. False when it does."""
    own = path.with_name(f"{path.name}.{pid}.tmp")
    own.write_text(str(pid), encoding="utf-8")
    try:
        os.link(own, path)
        return True
    except FileExistsError:
        return False
    except OSError:   # no hard links on this disk: create, then write (the grace covers it)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as lock:
            lock.write(str(pid))
        return True
    finally:
        own.unlink(missing_ok=True)


def acquire_lock(path=LOCK_FILE, pid=None, clock=time.monotonic, sleep=time.sleep, out=print,
                 timeout_s=LOCK_TIMEOUT_S, poll_s=LOCK_POLL_S):
    """Take the machine-wide timing lock: a file holding the running harness's pid. While
    another live run holds it, say "waiting for run <pid>" and wait, raising LockTimeout
    after `timeout_s`. A lock whose pid is dead is taken over, and so is one that names
    no pid for LOCK_EMPTY_GRACE_S (a run that died between making it and writing it);
    until then it is held."""
    path, pid = Path(path), os.getpid() if pid is None else pid
    began, said, empty_since = clock(), None, None
    while not _create(path, pid):
        holder = _holder(path)
        if holder is None:
            empty_since = clock() if empty_since is None else empty_since
            stale = clock() - empty_since >= LOCK_EMPTY_GRACE_S
        else:
            empty_since, stale = None, not pid_alive(holder)
        if stale:
            path.unlink(missing_ok=True)
            empty_since = None
            continue
        if holder is not None and holder != said:
            out(f"waiting for run {holder}")
            said = holder
        if clock() - began >= timeout_s:
            raise LockTimeout(f"run {holder or '(pid not written)'} still holds {path} after "
                              f"{timeout_s / 60:.0f} minutes")
        sleep(poll_s if holder is not None else min(poll_s, 1.0))
    return path


def release_lock(path=LOCK_FILE, pid=None):
    """Drop the lock, if this run still holds it."""
    pid = os.getpid() if pid is None else pid
    if _holder(path) == pid:
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- load and rows
UNRELIABLE_LOAD = 40.0   # percent: other work on the machine above this skews a row


def _system_times():
    import ctypes
    idle, kernel, user = (ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong())
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel),
                                                 ctypes.byref(user)):
        raise OSError("GetSystemTimes failed")
    return idle.value, kernel.value + user.value   # kernel time includes idle time


def cpu_meter(system_times=None, own_cpu_s=time.process_time):
    """Start measuring the CPU load of other work on the machine: the machine's busy share
    (Windows' GetSystemTimes, summed over every CPU) less this process's own CPU time.
    The function returned gives the average load since, in percent, or None when it
    cannot be read. Only this process is subtracted: a window process measuring its own
    rows leaves out its own work, but a process it launched still counts."""
    if system_times is None:
        if not sys.platform.startswith("win"):
            return lambda: None
        system_times = _system_times
    try:
        idle0, total0 = system_times()
        own0 = own_cpu_s()
    except (OSError, AttributeError):
        return lambda: None

    def since():
        try:
            idle1, total1 = system_times()
        except OSError:
            return None
        total = total1 - total0
        if total <= 0:
            return None
        own = (own_cpu_s() - own0) * 1e7   # seconds to GetSystemTimes' 100 ns units
        return max(0.0, 100.0 * (total - (idle1 - idle0) - own) / total)
    return since


# Rows taken while timing another row: asking for one times that row too.
DERIVED = {"poll_idle_scan": "poll_idle", "poll_changed_scan": "poll_changed",
           "poll_changed_controller": "poll_changed"}


def parse_only(text):
    """`--only`'s value, "ROW[,ROW]", as the set of row keys to time (with the rows a
    derived row is taken from). An unknown name is a ValueError naming it."""
    if text is None:
        return None
    asked = [name.strip() for name in text.split(",") if name.strip()]
    known = {key for key, _title in ROWS}
    unknown = [name for name in asked if name not in known]
    if unknown or not asked:
        raise ValueError(f"unknown row {', '.join(unknown) or '(none given)'}; the rows are: "
                         + ", ".join(key for key, _title in ROWS))
    return frozenset(asked) | {DERIVED[name] for name in asked if name in DERIVED}


class Recorder:
    """Times the rows asked for (`only`, None: every row), and the CPU load over each:
    `record(key, measure)` keeps `measure()`'s samples (or its error) under `key`, with
    the load it ran under. A row not asked for is never measured."""

    def __init__(self, only=None, load=cpu_meter, out=print):
        self.only, self.load, self.out = only, load, out
        self.results, self.loads = {}, {}

    def wants(self, *keys):
        """Whether any of `keys` is asked for: a setup for those rows is worth doing."""
        return self.only is None or any(key in self.only for key in keys)

    def record(self, key, measure):
        if not self.wants(key):
            return
        self.out(f"  {key} ...", end="", flush=True)
        since = self.load()
        try:
            self.results[key] = measure()
            text = f" {statistics.median(self.results[key]):.1f} ms (n={len(self.results[key])})"
        except Exception as err:   # one broken step must not lose the rest of the table
            self.results[key] = f"error: {type(err).__name__}: {err}"
            text = f" {self.results[key]}"
        self.loads[key] = since()
        if unreliable(self.loads[key]):
            text += f" (unreliable: CPU load {self.loads[key]:.0f}%)"
        self.out(text, flush=True)

    def derive(self, key, samples, of):
        """`samples` taken while timing row `of` (a poll's scan times, say): same load."""
        if not self.wants(key):
            return
        self.results[key] = samples
        self.loads[key] = self.loads.get(of)

    def data(self, info=None):
        return {"results": self.results, "load": self.loads, "info": info or {}}


def unreliable(load):
    return load is not None and load > UNRELIABLE_LOAD


# ---------------------------------------------------------------- fixtures
GEN_STATUSES = ("ready-for-agent", "claimed", "resolved", "needs-triage", "needs-info",
                "landed", "wontfix", "ready-for-human", "resolved", "resolved")
GEN_TYPES = ("AFK", "HITL", "grilling", "research")
GEN_WORDS = ("timing", "canvas", "redraw", "palette", "sidebar", "badge", "scroll", "poll",
             "header", "column", "session", "detail", "frontier", "blocked", "landing")


def generate_source(root, tickets=GENERATED_TICKETS):
    """A repo-root Source folder: `.scratch/generated-400/` (a build Effort of `tickets`
    Tickets, every Family, some Blocked, long and short titles) and `.scratch/generated-small/`
    (5 Tickets), so there is an Effort to switch from."""
    root = Path(root)
    _write_effort(root / ".scratch" / f"generated-{tickets}", tickets,
                  f"A generated Effort of {tickets} Tickets")
    _write_effort(root / ".scratch" / "generated-small", 5, "A small generated Effort")
    return root


def _write_effort(folder, count, title):
    issues = folder / "issues"
    issues.mkdir(parents=True, exist_ok=True)
    (folder / "spec.md").write_text(f"# {title}\n\nStatus: ready-for-agent\n\n## Problem\n\n"
                                    "A fixture for tools/time_board.py.\n", encoding="utf-8")
    for i in range(1, count + 1):
        number = f"{i:02d}"
        words = " ".join(GEN_WORDS[(i * k) % len(GEN_WORDS)] for k in range(1, 2 + i % 9))
        blocked_by = f"{i - 1:02d}, {i - 2:02d}" if 3 <= i <= 99 and i % 4 == 0 else "None"
        text = (f"# {number}: Generated Ticket {i}, {words}\n\n"
                f"Type: {GEN_TYPES[i % len(GEN_TYPES)]}\n"
                f"Status: {GEN_STATUSES[i % len(GEN_STATUSES)]}\n"
                f"Area: {i % 7 + 1}, area {i % 7 + 1}\n"
                f"Blocked by: {blocked_by}\n\n"
                f"## What to build\n\nGenerated Ticket {i} for the timing harness.\n\n"
                + "".join(f"- [ ] Criterion {k}: {words}\n" for k in range(1, 6)))
        (issues / f"{number}-generated-ticket-{number}.md").write_text(text, encoding="utf-8")


def copy_markdown(source, dest):
    """A copy of the `.md` files the Board reads (all of `.scratch/`, or the Effort folder),
    for the poll timing to write to. The given folder is only read."""
    source, dest = Path(source), Path(dest)
    tree = source / ".scratch" if (source / ".scratch").is_dir() else source
    target = dest / ".scratch" if tree != source else dest

    def ignore(folder, names):
        return [n for n in names if not (n.endswith(".md") or (Path(folder) / n).is_dir())
                or n in (".git", ".venv", "node_modules")]
    shutil.copytree(tree, target, ignore=ignore)
    return dest


class FakeBuilders:
    """An orchestrator Session and three subagent Builders, in Claude Code's layout, on the
    first three Tickets of `effort` still being built; `act(i)` appends a new tool call to
    one of them."""

    TOOLS = (("Edit", {"file_path": "G:\\work\\shell.gd"}),
             ("Bash", {"command": "python -m unittest discover"}),
             ("Read", {"file_path": "G:\\work\\notes.md"}))

    def __init__(self, projects, effort):
        self.projects = Path(projects)
        orch = self.projects / "G--harness" / "orch.jsonl"
        self.subagents = orch.with_suffix("") / "subagents"
        self.subagents.mkdir(parents=True, exist_ok=True)
        self._line(orch, "user", {"role": "user",
                                  "content": f"/implement-spec {effort.path / 'spec.md'}"})
        self.transcripts = []
        # Tickets still being built: one whose mark is Finished, Landed or Dropped shows no
        # Activity whatever its Builder does (story 32).
        building = [t for t in effort.tickets if not stopped(t.mark)] or list(effort.tickets)
        for tracked in building[:3]:
            number = tracked.ticket.number
            (self.subagents / f"agent-h{number}.meta.json").write_text(
                json.dumps({"description": f"Build ticket {number} harness"}), encoding="utf-8")
            transcript = self.subagents / f"agent-h{number}.jsonl"
            self._line(transcript, "user", {"role": "user", "content": f"Build {tracked.ticket.path}"})
            self.transcripts.append(transcript)
            self.act(len(self.transcripts) - 1)
        # A Builder on no Ticket (09): the Effort's header shows it. `act` never touches it.
        (self.subagents / "agent-hfix.meta.json").write_text(
            json.dumps({"description": "Fix the code review's findings"}), encoding="utf-8")
        self.loose = self.subagents / "agent-hfix.jsonl"
        self._line(self.loose, "user", {"role": "user", "content": "Fix the code review's findings."})
        self._line(self.loose, "assistant", {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "git diff"}}]})

    def act(self, i):
        name, args = self.TOOLS[i % len(self.TOOLS)]
        self._line(self.transcripts[i % len(self.transcripts)], "assistant", {
            "role": "assistant", "content": [{"type": "tool_use", "name": name, "input": args}]})

    @staticmethod
    def _line(path, kind, message):
        record = {"type": kind, "timestamp": datetime.now().astimezone().isoformat(),
                  "message": message}
        with open(path, "a", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")


def write_builders(projects, effort):
    return FakeBuilders(projects, effort)


def set_projects(workspace_file, projects):
    """Point the Workspace file's sessions folder at `projects` (None: the app's default),
    returning what it was. The app reads it on every Sessions scan."""
    path = Path(workspace_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    was = data.get("claude_projects_dir")
    if projects is None:
        data.pop("claude_projects_dir", None)
    else:
        data["claude_projects_dir"] = str(projects)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return was


def write_workspace(path, tabs, claude_projects=None, owner_note=None, **settings):
    """A window's temp Workspace file. `owner_note` (`--owner-note`) is the owner's window
    note, so the window opens away from the owner (src/views/placement.py); None: no note."""
    data = {"tabs": [str(t) for t in tabs], "active": 0 if tabs else None, "palette": "graphite",
            "poll_interval_ms": DAY_MS, "show_detail_pane": True, "show_area_column": False}
    if claude_projects:
        data["claude_projects_dir"] = str(claude_projects)
    if owner_note:
        data["owner_window_note"] = str(owner_note)
    data.update(settings)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------- in the window (child)
class Timer:
    def __init__(self, window, repeats, budget_s, minimum):
        self.window, self.repeats, self.budget_s, self.minimum = window, repeats, budget_s, minimum

    probe = None   # the UiThreadProbe, once installed: settling waits for its scans too

    def settle(self, seconds=0.05):
        """Let everything pending draw, and any scan out on the runner land, then wait a
        moment, still drawing. So no timing starts with a scan running beside it."""
        end = time.perf_counter() + seconds
        self.window.update_idletasks()
        self.window.update()
        if self.probe is not None:
            self.probe.wait()
        while time.perf_counter() < end:
            time.sleep(0.01)
            self.window.update()

    def once(self, action):
        """Milliseconds from `action()` (the input) to the frame painted after it."""
        self.settle()
        start = time.perf_counter()
        action()
        self.window.update_idletasks()
        self.window.update()
        return (time.perf_counter() - start) * 1000

    def run(self, step, once=None):
        """Time `step(i)` (which does untimed setup and returns the timed action) until
        `repeats` samples, or `budget_s` is spent once `minimum` samples are in. `once`
        times one action (default: `self.once`)."""
        once = once or self.once
        samples, began = [], time.perf_counter()
        while len(samples) < self.repeats and (
                len(samples) < self.minimum or time.perf_counter() - began < self.budget_s):
            samples.append(once(step(len(samples))))
        return samples


class UiThreadProbe:
    """Stands between the controller and its runner and times, on the UI thread, each
    result handed back: the controller's `done`, then the paint after it. `scan_ms` is
    the wall time from handing work over to its result landing."""

    def __init__(self, inner, window):
        self.inner, self.window = inner, window
        self.submitted = self.landed = 0
        self.applied_ms = self.scan_ms = self.drawing_ms = 0.0

    VIEW_CALLS = ("show_snapshot", "show_unreadable", "apply_changes", "flash", "show_sessions",
                  "show_effort", "show_activity")

    def watch_view(self, view):
        """Count the time `view`'s drawing calls take (and the paint after a result) in
        `drawing_ms`, so a poll's UI-thread time can be split into the controller's share
        and the views'."""
        depth = [0]   # a view call made inside another (apply_changes -> flash) counts once
        for name in self.VIEW_CALLS:
            def timed(*args, _call=getattr(view, name), **kwargs):
                start = time.perf_counter()
                depth[0] += 1
                try:
                    return _call(*args, **kwargs)
                finally:
                    depth[0] -= 1
                    if depth[0] == 0:
                        self.drawing_ms += (time.perf_counter() - start) * 1000
            setattr(view, name, timed)

    def submit(self, work, done, always=None, failed=None):
        self.submitted += 1
        handed = time.perf_counter()

        def timed(result):
            start = time.perf_counter()
            self.scan_ms += (start - handed) * 1000
            try:
                done(result)
                painted = time.perf_counter()
                self.window.update_idletasks()
                self.drawing_ms += (time.perf_counter() - painted) * 1000
            finally:
                self.applied_ms += (time.perf_counter() - start) * 1000

        def back():   # runs before `timed`, and also when the scan raised
            self.landed += 1
            if always is not None:
                always()
        self.inner.submit(work, timed, back, failed)   # a failed scan goes on to the controller

    def wait(self, timeout_s=60.0):
        """Pump the window until every scan handed over has landed."""
        end = time.perf_counter() + timeout_s
        while self.landed < self.submitted:
            if time.perf_counter() > end:
                import faulthandler
                faulthandler.dump_traceback(all_threads=True)   # where the scan is stuck
                raise RuntimeError("a scan never came back from the runner")
            time.sleep(0.001)
            self.window.update()

    def ui_once(self, timer, scans, shares=None):
        """A `Timer.once` for an action that hands a scan to the runner: milliseconds of
        UI-thread time, from the action to its own paint plus from the result landing to
        the paint after it. The scan's off-thread wall time is appended to `scans`, and
        the controller's share (the UI-thread time not spent in a view's drawing calls or
        the paint) to `shares`."""
        def once(action):
            timer.settle()
            submitted = self.submitted
            self.applied_ms = self.scan_ms = self.drawing_ms = 0.0
            start = time.perf_counter()
            action()
            painted = time.perf_counter()
            self.window.update_idletasks()
            handing = (time.perf_counter() - start) * 1000
            self.drawing_ms += (time.perf_counter() - painted) * 1000
            if self.submitted == submitted:
                raise RuntimeError("the poll handed no scan to the runner")
            self.wait()
            scans.append(self.scan_ms)
            if shares is not None:
                shares.append(handing + self.applied_ms - self.drawing_ms)
            return handing + self.applied_ms
        return once


def _descendants(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _descendants(child)


def wheel_target(table):
    """The widget a wheel turn over the table's rows lands on: the first shown widget
    drawn inside the table's biggest canvas (the one that scrolls), or that canvas when
    it holds no widgets (a table drawn on one canvas)."""
    import tkinter as tk
    canvases = [w for w in _descendants(table) if isinstance(w, tk.Canvas)]
    if not canvases:
        return table
    canvas = max(canvases, key=lambda c: c.winfo_width() * c.winfo_height())
    inside = [w for w in _descendants(canvas)
              if w is not canvas and not w.winfo_children() and w.winfo_ismapped()]
    return inside[0] if inside else canvas


def run_window(folder, poll_folder, workspace_file, result_file, repeats, budget_s, minimum,
               only=None):
    """Time every row asked for (`only`: a set of row keys, None: all) in one window, and
    write the results, the load over each row and the folder's info to `result_file`."""
    from src.app import build_app
    from src.model.sorting import DEFAULT_SORT
    from src.model.view_settings import AREA_COLUMN, DETAIL_PANE
    from src.palette import palette_names

    from src.views.placement import guard_foreground, keep_behind

    guard_foreground()
    window, controller = build_app(workspace_file)
    keep_behind(window, controller.workspace)
    probe = controller.runner = UiThreadProbe(controller.runner, window)
    timer = Timer(window, repeats, budget_s, minimum)
    timer.probe = probe
    timer.settle(1.0)
    rows, info = Recorder(only), {}
    record, wants = rows.record, rows.wants

    def front():
        return controller.front_tab()

    tab = controller.tabs[0]
    efforts = sorted(tab.snapshot.efforts, key=lambda e: len(e.tickets)) if tab.snapshot else []
    big = efforts[-1] if efforts else None
    other = efforts[0] if len(efforts) > 1 else None
    info["efforts"] = len(efforts)
    info["biggest"] = f"{big.name} ({len(big.tickets)} Tickets)" if big else "none"
    info["tickets"] = sum(len(e.tickets) for e in efforts)
    if big is None:
        raise SystemExit(f"no Effort with Tickets in {folder}")
    controller.select_effort(tab, big.name)
    timer.settle(0.5)

    def effort_switch(_i):
        controller.select_effort(front(), other.name)
        timer.settle()
        return lambda: controller.select_effort(front(), big.name)
    if other is not None:
        record("effort_switch", lambda: timer.run(effort_switch))
    else:
        rows.derive("effort_switch", "n/a: only one Effort", of=None)
    record("effort_reclick", lambda: timer.run(
        lambda _i: lambda: controller.select_effort(front(), big.name)))

    paths = [t.ticket.path for t in big.tickets[:8]]
    record("row_select", lambda: timer.run(
        lambda i: lambda: front().view.select_row(paths[i % len(paths)])))

    def sort_step(i):
        key = SORT_KEYS[i % len(SORT_KEYS)]
        return lambda: controller.sort_by(front(), key)
    record("sort", lambda: timer.run(sort_step))
    while front().sort != DEFAULT_SORT:
        controller.sort_by(front(), DEFAULT_SORT[0])
    timer.settle()

    def toggle(key):
        samples = timer.run(lambda _i: lambda: controller.toggle_view(key))
        if len(samples) % 2:
            controller.toggle_view(key)    # leave it as it started
            timer.settle()
        return samples
    record("toggle_area", lambda: toggle(AREA_COLUMN))
    record("toggle_detail", lambda: toggle(DETAIL_PANE))

    names = palette_names()
    second = "paper" if "paper" in names else next(n for n in names if n != "graphite")

    def theme():
        samples = timer.run(lambda i: lambda: controller.set_palette(second if i % 2 == 0 else "graphite"))
        if controller.workspace.palette != "graphite":
            controller.set_palette("graphite")
            timer.settle()
        return samples
    record("theme", theme)

    def scroll_step(i):
        target = wheel_target(front().view.table)
        delta = -120 if i % 2 == 0 else 120    # down, then back up: every step moves
        return lambda: target.event_generate("<MouseWheel>", delta=delta, x=0, y=0)
    record("scroll", lambda: timer.run(scroll_step))

    if wants("tab_board"):
        # Board to Board: the second tab shows the biggest Effort too.
        controller.front(1)
        controller.select_effort(controller.tabs[1], big.name)
        controller.front(0)
        timer.settle(0.5)
        record("tab_board", lambda: timer.run(
            lambda i: lambda: controller.front(1 if i % 2 == 0 else 0)))
        controller.front(0)

    if wants("tab_to_sessions", "tab_from_sessions"):
        controller.open_sessions()
        controller.front(0)
        timer.settle(0.5)
        sessions_index = len(controller.tabs)

        def to_sessions(_i):
            controller.front(0)
            timer.settle()
            return lambda: controller.front(sessions_index)

        def from_sessions(_i):
            controller.front(sessions_index)
            timer.settle()
            return lambda: controller.front(0)
        record("tab_to_sessions", lambda: timer.run(to_sessions))
        record("tab_from_sessions", lambda: timer.run(from_sessions))
        controller.close_sessions()
        controller.front(0)
        timer.settle(0.5)

    idle_scans = []
    probe.watch_view(front().view)
    record("poll_idle", lambda: timer.run(lambda _i: controller.refresh_now,
                                          probe.ui_once(timer, idle_scans)))
    rows.derive("poll_idle_scan", idle_scans, of="poll_idle")

    activity_keys = ("poll_activity", "click_activity", "click_header_builder",
                     "click_activity_opening")
    if not wants("poll_changed", *activity_keys):
        write_results(result_file, rows, info)
        controller.quit()
        return

    # One row changed: a tab on a folder the harness may write to, the biggest Effort shown.
    controller.new_tab(str(poll_folder))
    poll_tab = front()
    poll_effort = next(e for e in poll_tab.snapshot.efforts if e.name == big.name)
    controller.select_effort(poll_tab, big.name)
    target = poll_effort.tickets[min(2, len(poll_effort.tickets) - 1)].ticket.path
    original = target.read_text(encoding="utf-8")
    first = STATUS_LINE.search(original)
    was = first.group(2) if first else ""
    alternate = "claimed" if was.lower() != "claimed" else "ready-for-agent"

    def changed_step(i):
        status = alternate if i % 2 == 0 else (was or "ready-for-agent")
        text = (STATUS_LINE.sub(lambda m: m.group(1) + status + m.group(3), original, count=1)
                if first else f"Status: {status}\n" + original)
        target.write_text(text, encoding="utf-8")
        timer.settle(FLASH_WAIT_S)
        return controller.refresh_now
    timer.settle(0.5)
    probe.watch_view(poll_tab.view)
    changed_scans, changed_shares = [], []
    try:
        record("poll_changed", lambda: timer.run(
            changed_step, probe.ui_once(timer, changed_scans, changed_shares)))
    finally:
        target.write_text(original, encoding="utf-8")
    rows.derive("poll_changed_scan", changed_scans, of="poll_changed")
    rows.derive("poll_changed_controller", changed_shares, of="poll_changed")
    if wants(*activity_keys):
        time_activity(controller, timer, rows, probe, poll_tab, poll_effort, workspace_file,
                      result_file, info)
    write_results(result_file, rows, info)
    controller.quit()


def write_results(result_file, rows, info):
    Path(result_file).write_text(json.dumps(rows.data(info)), encoding="utf-8")


def time_activity(controller, timer, rows, probe, poll_tab, poll_effort, workspace_file,
                  result_file, info):
    """A Builder's Activity changed: three Builders on the biggest Effort's first Tickets,
    in a sessions folder of the harness's own (the Workspace file points the scan at it);
    then the clicks on Activity."""
    record = rows.record
    builders = write_builders(Path(result_file).parent / f"builders-{Path(result_file).stem}",
                              poll_effort)
    was = set_projects(workspace_file, builders.projects)
    timer.settle(0.5)
    controller.refresh_now()
    timer.settle(0.5)
    info["activity_rows"] = len(poll_tab.shown.activity)

    def activity_step(i):
        builders.act(i)
        timer.settle()
        return controller.refresh_now
    activity_scans = []
    try:
        record("poll_activity", lambda: timer.run(
            activity_step, probe.ui_once(timer, activity_scans)))
        click_builders(controller, timer, record, poll_tab, info)
    finally:
        set_projects(workspace_file, was)


def click_builders(controller, timer, record, tab, info):
    """09: a click on a row's Activity, and on a header Builder, each a real `<Button-1>` on
    the widget drawing it, timed to the painted frame. The Sessions tab is open behind the
    Board (as after its first use); the click fronts it with the Builder's row selected.
    Then once more with the Sessions tab closed, so the click builds it."""
    index = controller.tabs.index(tab)
    table = tab.view.table
    path = next((p for p in tab.shown.activity if p in table._index), None)
    header = tab.view.header_builders
    info["header_builders"] = len(header._hits)
    if path is None:
        def missing():
            raise RuntimeError("no row shows Activity")
        record("click_activity", missing)
        return

    def click_activity():
        y = table._index[path] * table.row_h + table.row_h // 2 - int(table.body.canvasy(0))
        table.body.event_generate("<Button-1>", x=table._body_x["activity"] + 12, y=y)

    def click_header():
        y0, y1, _transcript = header._hits[0]
        header.event_generate("<Button-1>", x=20, y=(y0 + y1) // 2)

    def from_board(click):
        def step(_i):
            controller.front(index)
            table._scroll_top(max(0, table._index[path] - 2) * table.row_h)   # row in view
            table._fill()
            timer.settle()
            return click
        return step

    controller.open_sessions()
    controller.front(index)
    timer.settle(0.5)
    record("click_activity", lambda: timer.run(from_board(click_activity)))
    view = controller.sessions.view
    print(f"  (the click fronted the Sessions tab: {controller.sessions_fronted}; selected row: "
          f"{view.selected if view else None}; header Builders: {len(header._hits)})", flush=True)
    if header._hits:
        record("click_header_builder", lambda: timer.run(from_board(click_header)))

    def opening(i):
        controller.close_sessions()
        return from_board(click_activity)(i)
    record("click_activity_opening", lambda: timer.run(opening))
    controller.close_sessions()
    controller.front(index)
    timer.settle()


def startup_child(workspace_file):
    """Build the window and paint it once, then say so on stdout and quit."""
    from src.app import build_app
    from src.views.placement import guard_foreground, keep_behind
    guard_foreground()
    window, controller = build_app(workspace_file)
    keep_behind(window, controller.workspace)
    window.update_idletasks()
    window.update()
    print("painted", flush=True)
    controller.quit()


# ---------------------------------------------------------------- the parent
def _quiet():
    """Launch a window process asking Windows to show its first window without activating
    it (SW_SHOWNOACTIVATE), on top of what src/views/placement.py does inside it."""
    if not WINDOWS:
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 4    # SW_SHOWNOACTIVATE
    return {"startupinfo": info}


def time_startup(folder, temp, runs, claude_projects, tag, owner_note=None):
    samples = []
    for i in range(runs):
        ws = write_workspace(temp / f"ws-startup-{tag}-{i}.json", [folder], claude_projects,
                             owner_note)
        start = time.perf_counter()
        child = subprocess.Popen([sys.executable, __file__, "--startup-child", "--workspace", str(ws)],
                                 stdout=subprocess.PIPE, text=True, cwd=REPO, **_quiet())
        line = child.stdout.readline()
        elapsed = (time.perf_counter() - start) * 1000
        child.communicate()
        if line.strip() == "painted":
            samples.append(elapsed)
    if not samples:
        raise RuntimeError("the window never painted")
    return samples


def time_folder(label, folder, poll_folder, temp, args, tag):
    print(f"{label}: {folder}", flush=True)
    ws = write_workspace(temp / f"ws-{tag}.json", [folder, folder], args.claude_projects,
                         args.owner_note)
    result = temp / f"result-{tag}.json"
    command = [sys.executable, __file__, "--child", str(folder), "--poll-folder", str(poll_folder),
               "--workspace", str(ws), "--result", str(result), "--repeats", str(args.repeats),
               "--budget", str(args.budget), "--minimum", str(args.minimum)]
    if args.only is not None:
        command += ["--only", ",".join(sorted(args.only))]
    data = {"results": {}, "load": {}, "info": {}}
    if args.only is None or set(args.only) - {"startup"}:
        subprocess.run(command, cwd=REPO, check=False, **_quiet())
        data = (json.loads(result.read_text(encoding="utf-8")) if result.is_file()
                else {"results": {}, "load": {}, "info": {"error": "the timing window crashed"}})
    rows = Recorder(args.only)
    rows.record("startup", lambda: time_startup(folder, temp, args.startup_runs,
                                                args.claude_projects, tag, args.owner_note))
    data["results"].update(rows.results)
    data.setdefault("load", {}).update(rows.loads)
    return data


def _ms(value):
    return f"{value:,.1f} ms" if value < 100 else f"{value:,.0f} ms"


def cell(samples, bar=True):
    if not isinstance(samples, list) or not samples:
        return (samples or "not run"), ""
    median = statistics.median(samples)
    verdict = ("pass" if median <= BAR_MS else "FAIL") if bar else ""
    return f"{_ms(median)} (n={len(samples)})", verdict


def render(label, runs, args, load=None, only=None):
    """The table, in Markdown. `load` is the CPU load of other work over the whole run (a
    `cpu_meter` reading), or None."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                             text=True).stdout.strip()
    except OSError:
        sha = "?"
    lines = [f"# Board timing: {label}", "",
             f"{datetime.now():%Y-%m-%d %H:%M}, commit {sha or '?'}, Python {sys.version.split()[0]}.",
             f"Bar: {BAR_MS:.0f} ms from input to painted frame. Each cell is the median of up to "
             f"{args.repeats} runs (at least {args.minimum}; fewer when a run is slow, "
             f"{args.budget:.0f} s budget per interaction); startup is the median of "
             f"{args.startup_runs} launches. CPU load (other work on the machine, "
             f"machine-wide but for the harness's own process) "
             + (f"averaged {load:.0f}% over the run" if load is not None
                else "could not be read")
             + f"; a row timed above {UNRELIABLE_LOAD:.0f}% load is marked unreliable."
             + (f" Only these rows were timed: {', '.join(k for k, _t in ROWS if k in only)}."
                if only is not None else ""), ""]
    for name, (folder, data) in runs.items():
        info = data.get("info", {})
        lines.append(f"- **{name}**: `{folder}`, {info.get('efforts', '?')} Efforts, "
                     f"{info.get('tickets', '?')} Tickets, biggest {info.get('biggest', '?')}"
                     + (f", {info['activity_rows']} rows showing Activity in the Activity poll"
                        if "activity_rows" in info else "")
                     + (f". {info['error']}" if "error" in info else ""))
    lines.append("")
    heading = "| Interaction |" + "".join(f" {n} | |" for n in runs)
    lines += [heading, "|---|" + "---:|:---:|" * len(runs)]
    for key, title in ROWS:
        if only is not None and key not in only:
            continue
        row = f"| {title} |"
        for _name, (_folder, data) in runs.items():
            text, verdict = cell(data["results"].get(key), key not in NO_BAR)
            load = data.get("load", {}).get(key)
            if unreliable(load) and key in data["results"]:
                text += f", unreliable: CPU load {load:.0f}%"
            row += f" {text} | {verdict} |"
        lines.append(row)
    return "\n".join(lines) + "\n"


def take_shots(source, out_dir, label, temp, claude_projects, generated=None, owner_note=None):
    """`--shot` PNGs of every view: each palette's Board, the Sessions tab, the detail pane
    off, the Area column on, and the generated 400-Ticket Effort. The biggest Effort is
    shown with its first Ticket selected."""
    from src.model.effort import scan
    from src.palette import palette_names
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def biggest(folder):
        effort = max(scan(folder).efforts, key=lambda e: len(e.tickets))
        return effort.name, effort.tickets[0].ticket.path

    effort, first = biggest(source)
    shots = [(f"{label}-board-{p}.png", source, effort, first, {"palette": p}, [])
             for p in palette_names()]
    shots += [(f"{label}-detail-pane-off.png", source, effort, first, {"show_detail_pane": False}, []),
              (f"{label}-area-column-on.png", source, effort, first, {"show_area_column": True}, []),
              (f"{label}-sessions-tab.png", source, effort, first, {}, ["--sessions"])]
    if generated is not None:
        g_effort, g_first = biggest(generated)
        shots.append((f"{label}-board-generated-{GENERATED_TICKETS}.png", generated, g_effort,
                      g_first, {}, []))
    for i, (name, folder, effort_name, select, settings, extra) in enumerate(shots):
        ws = write_workspace(temp / f"ws-shot-{i}.json", [], claude_projects, owner_note,
                             **settings)
        subprocess.run([sys.executable, str(REPO / "wayfinder.py"), "--workspace", str(ws),
                        "--open", str(folder), "--effort", effort_name, "--select", str(select),
                        *extra, "--shot", str(out_dir / name)], cwd=REPO, check=False,
                       **_quiet())


def utf8_output():
    """Print UTF-8 whatever the console: redirected to a file or a pipe, Windows' stdout
    takes the ANSI code page, and a row title's "→" would crash the print of the table."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None, lock_file=LOCK_FILE):
    """The command line. A timing run (not the child processes it starts) ends with one
    `exit=<code>` line and returns that code: 0 when every row asked for was timed."""
    utf8_output()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="rows for --only:\n" + "\n".join(f"  {key:<24} {title}" for key, title in ROWS))
    parser.add_argument("source", nargs="?", help="the Source folder to time (e.g. ~/code/my-repo)")
    parser.add_argument("--label", default="run", help="names the table and the shots (before, after)")
    parser.add_argument("--out", help="also write the table to this file")
    parser.add_argument("--shots", metavar="DIR", help="also save --shot PNGs of every view here")
    parser.add_argument("--repeats", type=int, default=9, help="most runs per interaction (9)")
    parser.add_argument("--minimum", type=int, default=3, help="fewest runs per interaction (3)")
    parser.add_argument("--budget", type=float, default=20.0,
                        help="seconds per interaction before it stops at the minimum (20)")
    parser.add_argument("--startup-runs", type=int, default=5, help="launches timed for startup (5)")
    parser.add_argument("--quick", action="store_true",
                        help="3 runs each, 3 launches: a Builder's check of the whole table")
    parser.add_argument("--only", metavar="ROW[,ROW]",
                        help="time only these rows (names below): re-time what a change touched")
    parser.add_argument("--no-generated", action="store_true", help="skip the 400-Ticket Effort")
    parser.add_argument("--claude-projects", metavar="DIR",
                        help="Claude Code's sessions folder (default: the app's, ~/.claude/projects)")
    parser.add_argument("--owner-note", metavar="FILE",
                        help="a JSON note of the owner's window (x, y, width, height); its "
                             "windows open on another monitor (default: none)")
    # internal: the child processes
    parser.add_argument("--child", help=argparse.SUPPRESS)
    parser.add_argument("--poll-folder", help=argparse.SUPPRESS)
    parser.add_argument("--workspace", help=argparse.SUPPRESS)
    parser.add_argument("--result", help=argparse.SUPPRESS)
    parser.add_argument("--startup-child", action="store_true", help=argparse.SUPPRESS)
    try:
        args = parser.parse_args(argv)
        try:
            args.only = parse_only(args.only)
        except ValueError as err:
            parser.error(f"--only: {err}")
        if not (args.startup_child or args.child or args.source):
            parser.error("give the Source folder to time")
    except SystemExit as stop:
        if not stop.code:   # --help
            raise
        return finish(stop.code)

    if args.startup_child:
        return startup_child(args.workspace)
    if args.child:
        return run_window(Path(args.child), Path(args.poll_folder), args.workspace, args.result,
                          args.repeats, args.budget, args.minimum, args.only)
    if args.quick:
        args.repeats, args.minimum, args.startup_runs = 3, 3, 3
    try:
        code = timing_run(args, lock_file)
    except LockTimeout as err:
        print(f"error: {err}", file=sys.stderr)
        code = 1
    except Exception:   # any failure still ends with the exit line
        traceback.print_exc()
        code = 1
    return finish(code)


def finish(code):
    """The run's last line: `exit=<code>`."""
    sys.stderr.flush()
    print(f"exit={code}", flush=True)
    return code


def failed_rows(runs):
    """The rows (and folders) whose timing raised, or whose window crashed."""
    failed = []
    for name, (_folder, data) in runs.items():
        if "error" in data.get("info", {}):
            failed.append(f"{name}: {data['info']['error']}")
        failed += [f"{name}: {key}" for key, value in data["results"].items()
                   if isinstance(value, str) and value.startswith("error")]
    return failed


def timing_run(args, lock_file):
    """Wait for the lock, time the folders, print (and write) the table. Returns 1 when a
    row failed, else 0."""
    acquire_lock(lock_file)
    try:
        return _time_all(args)
    finally:
        release_lock(lock_file)


def _time_all(args):
    source = Path(args.source).resolve()
    temp = Path(tempfile.mkdtemp(prefix="wayfinder-board-timing-"))
    os.environ[ENV_VAR] = str(temp / "workspace-never-used.json")   # never the owner's file
    try:
        run_load = cpu_meter()
        runs = {}
        copy = copy_markdown(source, temp / "poll-copy" / source.name)
        runs[source.name] = (source, time_folder(source.name, source, copy, temp, args, "given"))
        generated = None
        if not args.no_generated:
            generated = generate_source(temp / f"generated-{GENERATED_TICKETS}")
            runs[f"generated-{GENERATED_TICKETS}"] = (
                "a temp folder", time_folder(f"generated-{GENERATED_TICKETS}", generated, generated,
                                             temp, args, "generated"))
        table = render(args.label, runs, args, run_load(), args.only)
        print()
        print(table)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(table, encoding="utf-8")
            print(f"wrote {Path(args.out).resolve()}")
        if args.shots:
            take_shots(source, args.shots, args.label, temp, args.claude_projects, generated,
                       args.owner_note)
        failed = failed_rows(runs)
        for line in failed:
            print(f"error: {line}", file=sys.stderr)
        return 1 if failed else 0
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
