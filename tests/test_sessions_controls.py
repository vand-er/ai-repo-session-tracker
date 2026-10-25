"""The controller's Sessions tab: View → Sessions opens one tab, the window comes from the
Workspace file on each scan, and the fronted Board's Session column is marked.
Driven through BoardController with a stand-in window, so no GUI is built."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from src.controller import BoardController
from src.workspace import load_workspace
from tests.fakes import FakeSessions, FakeWindow

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retro-2026-10-19"
TICKET = next((FIXTURE / "issues").glob("02-*.md"))


def write_transcript(projects, name, minutes_ago, prompt):
    path = projects / f"G--{name}" / f"{name}.jsonl"
    path.parent.mkdir(parents=True)
    lines = [{"type": "user", "timestamp": "2026-10-21T09:00:00Z", "cwd": f"G:\\{name}",
              "message": {"role": "user", "content": prompt}},
             {"type": "custom-title", "customTitle": f"{name} title"}]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    stamp = time.time() - minutes_ago * 60
    os.utime(path, (stamp, stamp))


class SessionsControlsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        projects = root / "projects"
        write_transcript(projects, "fresh", 0.2, f"/implement {TICKET}")
        write_transcript(projects, "older", 10, "hello")
        self.ws_file = root / "ws.json"
        self.write_settings(claude_projects_dir=str(projects), sessions_window_minutes=30)
        self.window = FakeWindow()
        self.controller = BoardController(load_workspace(self.ws_file), self.ws_file, self.window)
        self.controller.start()
        self.controller.new_tab(FIXTURE)

    def write_settings(self, **settings):
        data = json.loads(self.ws_file.read_text(encoding="utf-8")) if self.ws_file.exists() else {}
        data.update(settings)
        self.ws_file.write_text(json.dumps(data), encoding="utf-8")

    def titles(self):
        return [row[0] for row in self.controller.sessions.view.rows]

    def test_the_fronted_board_marks_the_ticket_a_session_names(self):
        session_for = self.controller.front_tab().view.session_for
        self.assertEqual(session_for(TICKET), "fresh title")
        self.assertIsNone(session_for(FIXTURE / "issues" / "01-x.md"))

    def test_opening_sessions_twice_fronts_the_one_tab(self):
        self.controller.open_sessions()
        self.controller.front(0)
        self.controller.open_sessions()
        views = [b for b in self.window.boards if isinstance(b, FakeSessions)]
        self.assertEqual(len(views), 1)
        self.assertEqual(self.window.tabs, (["retro-2026-10-19", "Sessions"], 1))
        self.assertIs(self.window.fronted, views[0])
        self.assertIsNone(self.controller.front_tab())

    def test_a_one_minute_window_in_the_file_drops_older_sessions_on_the_next_scan(self):
        self.controller.open_sessions()
        self.assertEqual(self.titles(), ["fresh title", "older title"])
        self.write_settings(sessions_window_minutes=1)
        self.controller.poll_sessions()
        self.assertEqual(self.titles(), ["fresh title"])
        self.assertIn("last 1 min", self.controller.sessions.view.caption)

    def test_the_poll_redraws_the_fronted_sessions_tab(self):
        self.controller.open_sessions()
        self.write_settings(sessions_window_minutes=1)
        board = self.controller.tabs[0]
        scans = board.scans
        self.window.tick()
        self.assertEqual(self.titles(), ["fresh title"])
        self.assertEqual(board.scans, scans)   # the Board behind is not scanned

    def test_the_sessions_tab_is_not_saved_and_the_owners_window_edit_is_kept(self):
        self.controller.open_sessions()
        self.write_settings(sessions_window_minutes=5)
        self.controller.front(0)   # saves before any sessions scan has read the edit
        saved = json.loads(self.ws_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["tabs"], [str(FIXTURE)])
        self.assertEqual(saved["sessions_window_minutes"], 5)

    def test_a_poll_does_not_read_the_workspace_file_while_it_is_unchanged(self):
        """Story 9: the poll reads no file on the UI thread it need not."""
        self.window.tick()   # reads the file as the last save left it
        with mock.patch("src.sessions_controller.load_workspace",
                        wraps=load_workspace) as read:
            self.window.tick()
            self.window.tick()
        self.assertEqual(read.call_count, 0)

    def test_close_tab_on_the_sessions_tab_closes_only_it(self):
        self.controller.open_sessions()
        self.controller.close_tab()
        self.assertIsNone(self.controller.sessions.view)
        self.assertEqual(self.window.tabs, (["retro-2026-10-19"], 0))
        self.assertIsNotNone(self.controller.front_tab())


if __name__ == "__main__":
    unittest.main()
