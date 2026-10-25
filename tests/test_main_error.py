"""Main history carries its error (open-source-release 07): why main could not be read
(git not found, git failed, timed out, no branch found), empty when the Source folder is
not in a git repo at all, since git is optional. Driven through `scan` of throwaway git
repos made in temp folders, as the main-Landed tests are."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.controller import BoardController
from src.model.effort import scan
from src.runner import SameThreadRunner
from src.workspace import load_workspace
from tests.fakes import FakeWindow, write_workspace
from tests.test_main_landed import RepoTestCase, git, write_ticket


class MainErrorTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.effort("build", "07-thing")
        self.commit("07 — The thing")

    def test_git_missing_gives_git_not_found(self):
        with tempfile.TemporaryDirectory() as empty, \
                mock.patch.dict(os.environ, {"PATH": empty}):
            snapshot = scan(self.repo)
        self.assertEqual(snapshot.main.error, "git not found")

    def test_git_failing_gives_git_failed(self):
        # main's tip names a commit the repo does not hold, so `git log` fails.
        (self.repo / ".git" / "refs" / "heads" / "main").write_text("1" * 40 + "\n",
                                                                     encoding="ascii")
        self.assertEqual(scan(self.repo).main.error, "git failed")

    def test_git_running_past_its_time_limit_gives_timed_out(self):
        # git hits its time limit: on a fast machine a real one can finish within any
        # limit short enough for a test, so the limit's own error stands in for it.
        expired = subprocess.TimeoutExpired("git", 0.001)
        with mock.patch("src.model.main_branch.subprocess.run", side_effect=expired):
            snapshot = scan(self.repo)
        self.assertEqual(snapshot.main.error, "timed out")

    def test_a_repo_with_no_main_or_master_gives_no_branch_found(self):
        git(self.repo, "branch", "-q", "-m", "main", "trunk")
        self.assertEqual(scan(self.repo).main.error, "no branch found")

    def test_a_branch_setting_naming_no_branch_gives_no_branch_found(self):
        self.assertEqual(scan(self.repo, branch="nowhere").main.error, "no branch found")

    def test_a_main_read_fine_gives_no_error(self):
        self.assertEqual(scan(self.repo).main.error, "")

    def git_missing_scan(self):
        with tempfile.TemporaryDirectory() as empty, \
                mock.patch.dict(os.environ, {"PATH": empty}):
            return scan(self.repo)

    def test_a_failed_read_is_tried_again_once_its_retry_time_has_passed(self):
        failed = self.git_missing_scan()   # git fixed from here on; main's tip unmoved
        with mock.patch("src.model.main_branch.RETRY_AFTER", 0):
            snapshot = scan(self.repo, failed)
        self.assertEqual(snapshot.main.error, "")
        self.assertIn("07", snapshot.main.shas)   # main's subjects read: 07 has Landed

    def test_a_failed_read_is_not_tried_again_within_a_minute(self):
        failed = self.git_missing_scan()
        self.assertEqual(scan(self.repo, failed).main.error, "git not found")


class EmptyRepoTest(unittest.TestCase):
    def test_a_repo_with_no_commits_shows_no_error_and_no_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            write_ticket(repo / ".scratch" / "build", "07-thing")
            snapshot = scan(repo)
        self.assertEqual(snapshot.main.error, "")
        self.assertEqual(snapshot.main.shas, {})


class BoardHeaderLineTest(RepoTestCase):
    """Through BoardController with the stand-in window: a main history error reaches the
    Board as one header line, and the Tickets are still shown."""

    def launch(self):
        projects = self.repo.parent / "projects"
        projects.mkdir(exist_ok=True)
        ws_file = write_workspace(self.repo.parent / "ws.json", projects,
                                  tabs=[str(self.repo)], active=0)
        self.window = FakeWindow()
        controller = BoardController(load_workspace(ws_file), ws_file, self.window,
                                     runner=SameThreadRunner())
        controller.start()
        self.window.tick()   # the first poll, which runs git
        return controller.front_tab().view

    def shown_numbers(self, view):
        snapshot = [args[0] for name, args in view.told
                    if name in ("show_snapshot", "apply_changes")][-1]
        return [t.ticket.number for t in snapshot.efforts[0].tickets]

    def test_git_missing_shows_main_not_read_and_still_the_tickets(self):
        self.effort("build", "07-thing", "08-other")
        with tempfile.TemporaryDirectory() as empty, \
                mock.patch.dict(os.environ, {"PATH": empty}):
            view = self.launch()
        self.assertEqual(view.header_line, "main not read: git not found")
        self.assertEqual(self.shown_numbers(view), ["07", "08"])
        self.assertNotIn("show_unreadable", [name for name, _ in view.told])

    def test_a_main_read_fine_shows_no_header_line(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing")
        view = self.launch()
        self.assertFalse(view.header_line)
        self.assertEqual(self.shown_numbers(view), ["07"])

    def test_the_header_line_goes_once_main_reads_again(self):
        self.effort("build", "07-thing")
        git(self.repo, "branch", "-q", "-m", "main", "trunk")
        view = self.launch()
        self.assertEqual(view.header_line, "main not read: no branch found")
        git(self.repo, "branch", "-q", "-m", "trunk", "main")
        self.window.tick()
        self.assertEqual(view.header_line, "")


class OutsideGitErrorTest(unittest.TestCase):
    def test_a_folder_outside_git_gives_no_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "plain"
            write_ticket(source / ".scratch" / "build", "07-thing")
            snapshot = scan(source)
        self.assertIsNone(snapshot.main.repo)
        self.assertEqual(snapshot.main.error, "")


if __name__ == "__main__":
    unittest.main()
