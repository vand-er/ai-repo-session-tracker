"""Errors at the work boundary, driven through BoardController with the stand-in window: a
scan that raises an unexpected error shows "unreadable" with its reason, the poll keeps
going, the tab recovers by itself, and start-up never aborts on one bad folder."""

import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import src.controller
from src.controller import BoardController
from src.workspace import load_workspace
from tests.fakes import FakeClock, FakeWindow, write_workspace

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retro-2026-10-19"


class BrokenScan:
    """Stands in for the Effort scan: raises while `broken` names the folder it is given,
    else scans as usual."""

    def __init__(self):
        self.broken = set()
        self.real = src.controller.scan

    def __call__(self, folder, *args, **kwargs):
        if folder in self.broken:
            raise RuntimeError("the parser tripped")
        return self.real(folder, *args, **kwargs)


class ScanErrorTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()   # as a tab's folder is (8.3 names, /var on macOS)
        self.folder = self.root / "retro"
        shutil.copytree(FIXTURE, self.folder)
        self.ws_file = write_workspace(self.root / "ws.json", self.root / "projects")
        self.scan = BrokenScan()
        patcher = mock.patch("src.controller.scan", self.scan)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.window = FakeWindow()

    def controller(self):
        return BoardController(load_workspace(self.ws_file), self.ws_file, self.window)

    def test_a_scan_that_raises_shows_unreadable_and_the_tab_recovers_on_a_later_poll(self):
        controller = self.controller()
        controller.start()
        controller.new_tab(self.folder)
        view = controller.front_tab().view
        self.scan.broken.add(self.folder)
        view.told.clear()
        self.window.tick()
        self.assertEqual(view.told, [("show_unreadable",
                                      (self.folder, "RuntimeError: the parser tripped"))])
        self.window.tick()   # the poll keeps going: still broken, still unreadable
        self.assertEqual(view.told[-1][0], "show_unreadable")
        self.scan.broken.clear()
        view.told.clear()
        self.window.tick()   # the cause is fixed: the Board is back by itself
        self.assertIn("show_snapshot", [name for name, _args in view.told])
        self.assertIsNotNone(controller.front_tab().snapshot)

    def test_an_unexpected_error_is_written_to_the_error_log_beside_the_workspace_file(self):
        controller = BoardController(load_workspace(self.ws_file), self.ws_file, self.window,
                                     clock=FakeClock(datetime(2026, 10, 24, 9, 30, 5)))
        controller.start()
        controller.new_tab(self.folder)
        log = self.root / "error.log"
        self.assertFalse(log.exists())   # nothing has gone wrong yet
        self.scan.broken.add(self.folder)
        self.window.tick()
        text = log.read_text(encoding="utf-8")
        self.assertIn("2026-10-24 09:30:05", text)
        self.assertIn(str(self.folder), text)
        self.assertIn("Traceback (most recent call last):", text)
        self.assertIn("RuntimeError: the parser tripped", text)
        self.window.tick()
        self.assertEqual(log.read_text(encoding="utf-8").count("RuntimeError: the parser"), 2)

    def test_an_error_in_the_sessions_scan_is_logged_and_the_poll_keeps_going(self):
        controller = self.controller()
        controller.start()
        controller.open_sessions()   # first drawn here and now
        with mock.patch("src.sessions_controller.scan_sessions",
                        side_effect=RuntimeError("a transcript tripped")):
            self.window.tick()
        text = (self.root / "error.log").read_text(encoding="utf-8")
        self.assertIn("RuntimeError: a transcript tripped", text)
        self.assertIn("Sessions", text)
        self.assertIsNotNone(self.window.timer)

    def test_an_error_in_the_sessions_tabs_first_draw_is_logged_and_does_not_escape(self):
        controller = self.controller()
        controller.start()
        with mock.patch("src.sessions_controller.scan_sessions",
                        side_effect=RuntimeError("a transcript tripped")):
            controller.open_sessions()   # first drawn here and now: must not raise
        text = (self.root / "error.log").read_text(encoding="utf-8")
        self.assertIn("RuntimeError: a transcript tripped", text)
        self.assertIn("Sessions", text)
        self.window.tick()   # the poll draws the Sessions tab once the cause is gone
        self.assertIsNotNone(controller.sessions.drawn_by)

    def test_a_saved_tab_whose_first_scan_raises_does_not_abort_start_up(self):
        other = self.root / "other"
        shutil.copytree(FIXTURE, other)
        write_workspace(self.ws_file, self.root / "projects",
                        tabs=[str(self.folder), str(other)], active=0)
        self.scan.broken.add(self.folder)
        controller = self.controller()
        controller.start()
        self.assertEqual(self.window.tabs, (["retro", "other"], 0))
        broken_view = controller.tabs[0].view
        self.assertEqual(broken_view.told[-1],
                         ("show_unreadable", (self.folder, "RuntimeError: the parser tripped")))
        self.assertIsNotNone(self.window.timer)   # the poll was scheduled
        controller.front(1)
        self.assertIsNotNone(controller.front_tab().snapshot)


if __name__ == "__main__":
    unittest.main()
