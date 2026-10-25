"""`--shot` can't hang and `--menu` opens a menu first (agent-guardrails 13). Driven
through the app's argument handling, `src.__main__.main`, with the stand-in window, a
controller on the fake clock, and a stand-in for the PNG capture."""

import contextlib
import heapq
import io
import itertools
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from src import __main__ as app_main
from src.controller import BoardController
from src.runner import SameThreadRunner
from src.workspace import load_workspace
from tests.fakes import FakeClock, FakeWindow, write_workspace


class FakeBar:
    """The options bar: records the menus it was told to open, and when."""

    def __init__(self, clock):
        self.clock = clock
        self.opened = []

    def open_menu(self, name):
        self.opened.append((name, self.clock.time))

    def open_popups(self):
        return []


class ScriptedWindow(FakeWindow):
    """A stand-in window whose `after` calls run in `mainloop`, in order, on the fake
    clock. When nothing more is due it hangs, as a stuck window does, until it is closed
    (by the controller's quit, or by the watchdog's exit)."""

    HORIZON = timedelta(minutes=5)

    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.options_bar = FakeBar(clock)
        self.closed = threading.Event()
        self._queue, self._order = [], itertools.count()

    def after(self, ms, fn):
        entry = [self.clock.time + timedelta(milliseconds=ms), next(self._order), fn]
        heapq.heappush(self._queue, entry)
        return entry

    def after_cancel(self, entry):
        entry[2] = None

    def update(self): pass
    def update_idletasks(self): pass

    def close(self):
        self.closed.set()

    def mainloop(self):
        end = self.clock.time + self.HORIZON
        while not self.closed.is_set() and self._queue and self._queue[0][0] <= end:
            due, _, fn = heapq.heappop(self._queue)
            self.clock.time = max(self.clock.time, due)
            if fn is not None:
                fn()
        self.clock.time = max(self.clock.time, end)
        self.closed.wait(5)   # hung: only a close (or the watchdog) ends it


class ShotFlagsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "projects").mkdir()
        self.ws_file = write_workspace(root / "ws.json", root / "projects")
        self.png = root / "out.png"
        self.clock = FakeClock(datetime(2026, 10, 24, 12, 0).astimezone())
        self.window = ScriptedWindow(self.clock)
        self.exits = []
        self.shots = []
        for name, value in (("build_app", self.build_app), ("shoot", self.shoot),
                            ("guard_foreground", lambda: None),
                            ("keep_behind", lambda window, *_a, **_k: None),
                            ("CLOCK", self.clock), ("_exit", self.exit)):
            patcher = mock.patch.object(app_main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.saves = False

    def build_app(self, workspace_file=None):
        controller = BoardController(load_workspace(self.ws_file), self.ws_file, self.window,
                                     runner=SameThreadRunner(), clock=self.clock)
        controller.start()
        return self.window, controller

    def shoot(self, window, out_path, done, **_options):
        self.shots.append((str(out_path), self.clock.time))
        if self.saves:
            done()

    def exit(self, code):
        self.exits.append(code)
        self.window.close()

    def run_main(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            app_main.main(list(argv))
        return err.getvalue()

    def test_a_shot_that_never_saves_ends_non_zero_with_the_watchdogs_message(self):
        err = self.run_main("--workspace", str(self.ws_file), "--shot", str(self.png))
        self.assertEqual(len(self.exits), 1)
        self.assertNotEqual(self.exits[0], 0)
        self.assertIn("--shot", err)
        self.assertIn(str(self.png), err)
        self.assertIn(f"{app_main.SHOT_LIMIT_S} s", err)

    def test_a_shot_that_saves_in_time_exits_as_usual(self):
        self.saves = True
        self.run_main("--workspace", str(self.ws_file), "--shot", str(self.png))
        self.assertEqual(len(self.shots), 1)
        self.clock.time += timedelta(minutes=10)   # long after: the watchdog stays quiet
        time.sleep(3 * app_main.WATCH_POLL_S)
        self.assertEqual(self.exits, [])

    def test_menu_opens_that_menu_before_the_shot_is_taken(self):
        self.saves = True
        self.run_main("--workspace", str(self.ws_file), "--menu", "View",
                      "--shot", str(self.png))
        (name, opened_at), = self.window.options_bar.opened
        (_, shot_at), = self.shots
        self.assertEqual(name, "View")
        self.assertLess(opened_at, shot_at)

    def test_an_unknown_menu_is_an_error_naming_the_known_menus(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            app_main.main(["--workspace", str(self.ws_file), "--menu", "Edit",
                           "--shot", str(self.png)])
        self.assertNotEqual(raised.exception.code, 0)
        self.assertEqual(self.shots, [])
        message = err.getvalue().splitlines()[-1]
        self.assertIn("--menu", message)
        self.assertIn("Edit", message)
        for known in ("File", "View", "Actions", "Help"):
            self.assertIn(known, message)


if __name__ == "__main__":
    unittest.main()
