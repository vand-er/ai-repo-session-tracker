"""The poll, driven through BoardController with the stand-in window and a runner that runs
each scan at once on the same thread: what a poll tells the Board view, and nothing when
nothing changed."""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from src.controller import BoardController
from src.runner import SameThreadRunner
from src.workspace import load_workspace
from tests.fakes import FakeWindow, write_workspace

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retro-2026-10-19"


def write_transcript(projects, name, prompt, minutes_ago=0.2):
    path = projects / f"G--{name}" / f"{name}.jsonl"
    path.parent.mkdir(parents=True)
    lines = [{"type": "user", "timestamp": "2026-10-21T09:00:00Z", "cwd": f"G:\\{name}",
              "message": {"role": "user", "content": prompt}},
             {"type": "custom-title", "customTitle": f"{name} title"}]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    stamp = time.time() - minutes_ago * 60
    os.utime(path, (stamp, stamp))
    return path


class PollTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()   # as a tab's folder is (8.3 names, /var on macOS)
        self.folder = root / "retro"
        shutil.copytree(FIXTURE, self.folder)
        self.ticket = next((self.folder / "issues").glob("02-*.md"))
        projects = self.projects = root / "projects"
        write_transcript(projects, "fresh", f"/implement {self.ticket}")
        self.window = FakeWindow()
        self.runner = self.make_runner()
        ws_file = write_workspace(root / "ws.json", projects)
        self.controller = BoardController(load_workspace(ws_file), ws_file, self.window,
                                          runner=self.runner)
        self.controller.start()
        self.controller.new_tab(self.folder)
        self.tab = self.controller.front_tab()
        self.view = self.tab.view

    def make_runner(self):
        return SameThreadRunner()

    def told(self):
        return [name for name, _args in self.view.told]

    def test_the_first_scan_draws_the_board_and_marks_its_sessions(self):
        self.assertEqual(self.told(), ["show_snapshot", "show_sessions"])
        self.assertEqual(self.view.session_for(self.ticket), "fresh title")

    def test_a_poll_with_nothing_changed_tells_the_view_nothing(self):
        self.view.told.clear()
        self.window.tick()
        self.window.tick()
        self.assertEqual(self.told(), [])

    def set_status(self, status):
        text = self.ticket.read_text(encoding="utf-8")
        old = next(line for line in text.splitlines() if line.startswith("Status:"))
        self.ticket.write_text(text.replace(old, f"Status: {status}"), encoding="utf-8")
        later = time.time() + 5   # a new modification time, however coarse the clock
        os.utime(self.ticket, (later, later))

    def test_a_poll_redraws_and_flashes_a_ticket_whose_status_changed(self):
        self.view.told.clear()
        self.set_status("claimed")
        self.window.tick()
        self.assertEqual(self.told(), ["apply_changes"])
        snapshot, effort, _selected, changes = self.view.told[0][1]
        self.assertEqual(effort, "retro")
        self.assertEqual(list(changes.flash), [self.ticket])
        row = next(t for t in snapshot.efforts[0].tickets if t.ticket.path == self.ticket)
        self.assertEqual(row.ticket.status, "claimed")


class PollInFlightTest(PollTest):
    """The same Board with a runner that holds each scan until released: the scan runs
    off the poll, and its result reaches the view only when it is handed back."""

    def setUp(self):
        super().setUp()
        self.runner.release()     # the start-up scans, if any were handed over

    def make_runner(self):
        from tests.fakes import HeldRunner
        return HeldRunner()

    def test_a_polls_result_reaches_the_view_only_when_handed_back(self):
        self.view.told.clear()
        self.set_status("claimed")
        self.window.tick()
        self.assertEqual(self.told(), [])
        self.runner.release()
        self.assertEqual(self.told(), ["apply_changes"])

    def test_a_poll_while_a_scan_is_in_flight_starts_no_second_scan(self):
        scans = self.tab.scans
        self.window.tick()
        self.window.tick()
        self.assertEqual(len(self.runner.held), 1)
        self.runner.release()
        self.window.tick()
        self.assertEqual(len(self.runner.held), 1)
        self.assertEqual(self.tab.scans, scans + 2)

    def test_a_theme_switch_during_a_scan_keeps_the_view_and_the_scan_lands_on_it(self):
        self.view.told.clear()
        self.set_status("claimed")
        self.window.tick()
        self.controller.set_palette("paper")
        self.assertIs(self.tab.view, self.view)
        self.assertEqual(self.told(), [])
        self.runner.release()
        self.assertEqual(self.told(), ["apply_changes"])
        self.assertEqual(self.view.session_for(self.ticket), "fresh title")

    def test_the_sessions_tabs_poll_redraws_it_when_its_scan_is_handed_back(self):
        self.controller.open_sessions()
        sessions = self.controller.sessions.view
        self.assertEqual([row[0] for row in sessions.rows], ["fresh title"])
        write_transcript(self.projects, "newer", "hello")
        self.window.tick()
        self.assertEqual([row[0] for row in sessions.rows], ["fresh title"])
        self.runner.release()
        self.assertEqual(sorted(row[0] for row in sessions.rows), ["fresh title", "newer title"])

    def test_a_poll_with_nothing_changed_tells_the_view_nothing(self):
        self.view.told.clear()
        self.window.tick()
        self.runner.release()
        self.window.tick()
        self.runner.release()
        self.assertEqual(self.told(), [])

    def test_a_poll_redraws_and_flashes_a_ticket_whose_status_changed(self):
        self.view.told.clear()
        self.set_status("claimed")
        self.window.tick()
        self.runner.release()
        self.assertEqual(self.told(), ["apply_changes"])
        self.assertEqual(list(self.view.told[0][1][3].flash), [self.ticket])


class ProgressPollTest(unittest.TestCase):
    """A Builder's progress, written to the Effort's Progress file, reaching the Board on
    the next poll (fast-live-board 05)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()   # as a tab's folder is (8.3 names, /var on macOS)
        self.folder = root / "marks"
        shutil.copytree(FIXTURE.parent / "progress-marks", self.folder)
        self.progress = self.folder / "progress.md"
        self.ticket = self.folder / "issues" / "03-running.md"
        self.window = FakeWindow()
        ws_file = write_workspace(root / "ws.json", root / "projects")
        self.controller = BoardController(load_workspace(ws_file), ws_file, self.window,
                                          runner=SameThreadRunner())
        self.controller.start()
        self.controller.new_tab(self.folder)
        self.view = self.controller.front_tab().view

    def write_state(self, state):
        text = self.progress.read_text(encoding="utf-8")
        old = next(line for line in text.splitlines() if line.startswith("- 03-running:"))
        self.progress.write_text(text.replace(old, f"- 03-running: {state}"), encoding="utf-8")
        later = time.time() + 5 + len(state)   # a new modification time each write
        os.utime(self.progress, (later, later))

    def poll(self):
        """What the next poll told the view: the changes, and the Ticket's row."""
        self.view.told.clear()
        self.window.tick()
        told = [(name, args) for name, args in self.view.told if name == "apply_changes"]
        self.assertEqual(len(told), 1, [name for name, _ in self.view.told])
        snapshot, _effort, _selected, changes = told[0][1]
        row = next(t for t in snapshot.efforts[0].tickets if t.ticket.path == self.ticket)
        return changes, row

    def test_running_then_finished_then_landed_reach_the_board_each_flashing_the_row(self):
        for state, mark in (("finished .worktrees/03", ("Finished", "finished")),
                            ("landed 3333333", ("Done", "landed"))):
            with self.subTest(state=state):
                self.write_state(state)
                changes, row = self.poll()
                self.assertEqual((row.mark, row.mark_word), mark)
                self.assertEqual(list(changes.flash), [self.ticket])
                self.assertTrue(changes.header)   # the counts moved

    def test_an_unchanged_progress_file_tells_the_view_nothing(self):
        self.view.told.clear()
        self.window.tick()
        self.window.tick()
        self.assertEqual([name for name, _ in self.view.told], [])


if __name__ == "__main__":
    unittest.main()
