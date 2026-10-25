"""Landed from main's commit subjects (fast-live-board 06): a Ticket whose number heads a
commit subject on the repo's main branch (`07 — ...`) shows Landed. Driven through `scan`
of a Source folder that is a throwaway git repo each test makes in a temp folder."""

import contextlib
import hashlib
import os
import subprocess
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

from src.controller import BoardController
from src.model.effort import scan
from src.runner import SameThreadRunner
from src.workspace import load_workspace
from tests.fakes import FakeWindow, write_workspace

QUIET = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def git(repo, *args):
    """Run git in `repo` with a fixed identity and no hooks; returns its stdout."""
    command = ["git", "-c", "user.name=Test", "-c", "user.email=noreply@example.com",
               "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull,
               "-C", str(repo), *args]
    return subprocess.run(command, check=True, capture_output=True, text=True,
                           encoding="utf-8", stdin=subprocess.DEVNULL, **QUIET).stdout.strip()


EMPTY_TREE = hashlib.sha1(b"tree 0\0").hexdigest()   # git's empty tree, 4b825dc...


def write_object(git_dir, kind, body):
    """Store one loose git object, as git itself does; returns its sha."""
    data = kind + b" " + str(len(body)).encode("ascii") + b"\0" + body
    sha = hashlib.sha1(data).hexdigest()
    path = git_dir / "objects" / sha[:2] / sha[2:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zlib.compress(data))
    return sha


@contextlib.contextmanager
def counting_processes():
    """Within the block, record the command of every process started."""
    started = []

    class Counted(subprocess.Popen):
        def __init__(self, args, *rest, **kwargs):
            started.append(args)
            super().__init__(args, *rest, **kwargs)

    with mock.patch("subprocess.Popen", Counted):
        yield started


def write_ticket(effort, stem, status="ready-for-agent"):
    issues = effort / "issues"
    issues.mkdir(parents=True, exist_ok=True)
    (issues / f"{stem}.md").write_text(
        f"# {stem[:2]}: {stem[3:]}\n\n**Status:** {status}\n\n## What to build\n\nWork.\n",
        encoding="utf-8")


class RepoTestCase(unittest.TestCase):
    """A Source folder that is a git repo on `main`, holding `.scratch/<effort>/`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()
        self.tips = {}
        self.clock = int(time.time()) + 3600   # commits made after the test's Efforts
        git(self.repo, "init", "-q", "-b", "main")
        write_object(self.repo / ".git", b"tree", b"")
        self.commit("Start")

    def commit(self, *subjects, branch="main", when=None):
        """Empty commits with these subjects on `branch` (made from main's tip if new);
        a `branch` that starts `refs/` is that whole ref, such as a remote's branch.
        Written as git's own loose objects and ref file, as `git commit` would, since
        each git process costs a third of a second or more here. Returns their shas."""
        git_dir = self.repo / ".git"
        parent = self.tips.get(branch, self.tips.get("main"))
        shas = []
        for subject in subjects:
            self.clock += 60
            stamp = self.clock if when is None else int(when)
            body = (f"tree {EMPTY_TREE}\n" + (f"parent {parent}\n" if parent else "")
                    + f"author Test <noreply@example.com> {stamp} +0000\n"
                    + f"committer Test <noreply@example.com> {stamp} +0000\n\n"
                    + f"{subject}\n").encode("utf-8")
            parent = write_object(git_dir, b"commit", body)
            shas.append(parent)
        ref = git_dir / (branch if branch.startswith("refs/") else "refs/heads/" + branch)
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(parent + "\n", encoding="ascii")
        self.tips[branch] = parent
        return shas

    def effort(self, name, *stems, status="ready-for-agent"):
        folder = self.repo / ".scratch" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "spec.md").write_text(f"# {name}\n\nStatus: ready-for-agent\n",
                                        encoding="utf-8")
        for stem in stems:
            write_ticket(folder, stem, status)
        return folder

    def marks(self, snapshot, name):
        effort = next(e for e in snapshot.efforts if e.name == name)
        return {t.ticket.number: (t.mark, t.mark_word) for t in effort.tickets}


class UnknownBirthTest(RepoTestCase):
    """P7, owner-ruled: where the system keeps no folder creation time, a commit that heads
    a number only one Effort holds cannot be dated against the Effort, so it does not
    count. A commit named on the Ticket's own Progress line still does."""

    def setUp(self):
        super().setUp()
        # The creation time is the operating system's to give; here it gives none.
        patcher = mock.patch("src.model.main_branch._born", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_unique_number_on_main_does_not_count_without_the_efforts_creation_time(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing")
        self.assertEqual(self.marks(scan(self.repo), "build"), {"07": ("Ready", "ready-for-agent")})

    def test_a_commit_named_on_the_tickets_progress_line_still_counts(self):
        folder = self.effort("build", "07-thing")
        sha, = self.commit("07 — The thing")
        (folder / "progress.md").write_text(f"- 07-thing: waiting, see {sha[:7]}\n",
                                            encoding="utf-8")
        self.assertEqual(self.marks(scan(self.repo), "build"), {"07": ("Done", "landed")})


class MainSubjectTest(RepoTestCase):
    def test_a_subject_on_main_heading_a_tickets_number_makes_it_landed(self):
        self.effort("build", "07-thing", "08-other")
        self.commit("07 — The thing")
        self.assertEqual(self.marks(scan(self.repo), "build"),
                         {"07": ("Done", "landed"), "08": ("Ready", "ready-for-agent")})

    def test_the_same_subject_only_on_another_branch_does_not(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing", branch="flb-07")
        self.assertEqual(self.marks(scan(self.repo), "build"), {"07": ("Ready", "ready-for-agent")})

    def test_a_dropped_status_line_still_wins(self):
        self.effort("build", "07-thing", status="wontfix")
        self.commit("07 — The thing")
        self.assertEqual(self.marks(scan(self.repo), "build"), {"07": ("Dropped", "wontfix")})

    def test_a_status_line_already_done_keeps_its_word(self):
        self.effort("build", "07-thing", status="resolved")
        self.commit("07 — The thing")
        self.assertEqual(self.marks(scan(self.repo), "build"), {"07": ("Done", "resolved")})

    def test_only_the_number_then_a_space_and_a_dash_counts(self):
        self.effort("build", "01-a", "02-b", "03-c", "04-d", "05-e", "06-f")
        self.commit("01 - A hyphen counts", "02 review — A word between does not",
                    "03: A colon does not", "Fix 04 — Not at the head",
                    "05— No space does not", "6 — Another number does not")
        marks = self.marks(scan(self.repo), "build")
        self.assertEqual({n for n, mark in marks.items() if mark == ("Done", "landed")}, {"01"})

    def test_a_repo_with_no_main_branch_changes_nothing(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing")
        git(self.repo, "branch", "-q", "-m", "main", "trunk")
        self.assertEqual(self.marks(scan(self.repo), "build"), {"07": ("Ready", "ready-for-agent")})

    def test_a_main_tip_kept_only_in_packed_refs_still_counts(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing")
        git(self.repo, "pack-refs", "--all")
        self.assertFalse((self.repo / ".git" / "refs" / "heads" / "main").exists())
        self.assertEqual(self.marks(scan(self.repo), "build"), {"07": ("Done", "landed")})

    def test_a_source_in_a_worktree_reads_the_repos_main(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing")
        tree = self.repo.parent / "tree"
        git(self.repo, "worktree", "add", "-q", "-b", "side", str(tree))
        effort = self.effort("build", "07-thing").relative_to(self.repo)
        (tree / effort / "issues").mkdir(parents=True)
        write_ticket(tree / effort, "07-thing")
        self.assertEqual(self.marks(scan(tree), "build"), {"07": ("Done", "landed")})


class BranchChoiceTest(RepoTestCase):
    """Main history is read from the tab's branch setting if set, else the branch the
    remote's `origin/HEAD` names, else `main`, else `master` (open-source-release 06)."""

    def point_origin_head(self, name):
        head = self.repo / ".git" / "refs" / "remotes" / "origin" / "HEAD"
        head.parent.mkdir(parents=True, exist_ok=True)
        head.write_text(f"ref: refs/remotes/origin/{name}\n", encoding="ascii")

    def landed(self, snapshot):
        return {n for n, mark in self.marks(snapshot, "build").items()
                if mark == ("Done", "landed")}

    def test_the_branch_origin_head_names_wins_over_main(self):
        self.effort("build", "07-thing", "08-other")
        self.commit("08 — On trunk", branch="refs/remotes/origin/trunk")
        self.commit("07 — Only on main")
        self.point_origin_head("trunk")
        self.assertEqual(self.landed(scan(self.repo)), {"08"})

    def test_the_tabs_branch_setting_wins_over_everything(self):
        self.effort("build", "06-six", "07-seven", "08-eight", "09-nine")
        self.commit("06 — On release", branch="release")
        self.commit("08 — On trunk", branch="refs/remotes/origin/trunk")
        self.commit("09 — On master", branch="master")
        self.commit("07 — On main")
        self.point_origin_head("trunk")
        self.assertEqual(self.landed(scan(self.repo, branch="release")), {"06"})

    def test_a_branch_setting_naming_no_branch_shows_no_landed(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing")
        self.assertEqual(self.landed(scan(self.repo, branch="gone")), set())

    def test_main_is_reread_only_when_the_chosen_branchs_tip_moves(self):
        self.effort("build", "07-thing", "08-other")
        self.commit("Base", branch="refs/remotes/origin/trunk")
        self.point_origin_head("trunk")
        first = scan(self.repo)
        self.commit("07 — Only on main")
        with counting_processes() as started:
            again = scan(self.repo, first)
        self.assertEqual(started, [])
        self.commit("08 — On trunk", branch="refs/remotes/origin/trunk")
        with counting_processes() as started:
            moved = scan(self.repo, again)
        self.assertEqual(len(started), 1)
        self.assertEqual(self.landed(moved), {"08"})

    def test_master_is_read_when_there_is_no_main(self):
        self.effort("build", "07-thing")
        self.commit("07 — The thing")
        git(self.repo, "branch", "-q", "-m", "main", "master")
        self.assertEqual(self.landed(scan(self.repo)), {"07"})

    def test_a_local_branch_wins_over_origins_branch_of_the_same_name(self):
        # The owner merges onto main and pushes later: local main, ahead of origin's,
        # still shows Landed.
        self.effort("build", "07-thing")
        self.commit("Pushed", branch="refs/remotes/origin/main")
        self.commit("07 — Merged, not pushed yet")
        self.point_origin_head("main")
        self.assertEqual(self.landed(scan(self.repo)), {"07"})


class SeveralEffortsTest(RepoTestCase):
    """Two Efforts in one repo both hold a Ticket 07; only alpha holds 01, only beta 09."""

    def setUp(self):
        super().setUp()
        self.alpha = self.effort("alpha", "01-first", "07-alpha-seven")
        self.beta = self.effort("beta", "07-beta-seven", "09-ninth")
        self.seven = self.commit("07 — Whose seven?", "09 — The ninth", "01 — The first")[0]

    def landed(self, snapshot, name):
        return {n for n, mark in self.marks(snapshot, name).items() if mark == ("Done", "landed")}

    def test_a_number_held_by_one_effort_only_counts_for_it(self):
        snapshot = scan(self.repo)
        self.assertEqual(self.landed(snapshot, "alpha"), {"01"})
        self.assertEqual(self.landed(snapshot, "beta"), {"09"})

    def test_a_shared_number_counts_where_the_progress_file_names_the_commit(self):
        (self.alpha / "progress.md").write_text(
            f"# Progress\n\n- 07-alpha-seven: merged as {self.seven[:7]}, not landed yet\n",
            encoding="utf-8")
        snapshot = scan(self.repo)
        self.assertEqual(self.landed(snapshot, "alpha"), {"01", "07"})
        self.assertEqual(self.landed(snapshot, "beta"), {"09"})

    def test_a_sha_named_only_in_a_note_does_not_count(self):
        # A shape met in a real repo: an Effort's Progress file says where the previous
        # area landed on main, naming that area's last commit, whose number it shares.
        (self.beta / "progress.md").write_text(
            f"# Progress\n\n- Area alpha landed on `main` at `{self.seven[:7]}`.\n"
            "- 09-ninth: running\n", encoding="utf-8")
        snapshot = scan(self.repo)
        self.assertEqual(self.landed(snapshot, "alpha"), {"01"})
        self.assertEqual(self.landed(snapshot, "beta"), {"09"})

    def test_a_number_from_before_the_effort_was_made_does_not_count(self):
        # A shape met in a real repo: main holds `31 — the choice` from a numbering
        # a month older than the Effort whose Ticket 31 is still open.
        gamma = self.effort("gamma", "31-cues", "32-save")
        self.commit("31 — the choice", when=time.time() - 30 * 86400)
        self.commit("32 — the save")
        self.assertEqual(self.landed(scan(self.repo), "gamma"), {"32"})

    def test_an_old_commit_still_counts_where_the_tickets_progress_line_names_it(self):
        (self.alpha / "progress.md").write_text(
            f"- 07-alpha-seven: landed {self.seven[:7]}\n", encoding="utf-8")
        self.commit("01 — Old", when=time.time() - 30 * 86400)
        self.assertIn("07", self.landed(scan(self.repo), "alpha"))

    def test_a_source_that_is_one_effort_still_sees_the_repos_other_efforts(self):
        snapshot = scan(self.beta)
        self.assertEqual(self.landed(snapshot, "beta"), {"09"})


class RereadTest(RepoTestCase):
    def scan_counting_git(self, previous=None):
        """Scan, and count the processes the scan starts."""
        with counting_processes() as started:
            snapshot = scan(self.repo, previous)
        return snapshot, len(started)

    def test_mains_history_is_not_reread_while_its_tip_has_not_moved(self):
        self.effort("build", "07-thing", "08-other")
        self.commit("07 — The thing")
        first, _ = self.scan_counting_git()
        again, started = self.scan_counting_git(first)
        self.assertEqual(started, 0)
        self.assertEqual(self.marks(again, "build")["07"], ("Done", "landed"))

    def test_mains_history_is_reread_when_its_tip_moves(self):
        self.effort("build", "07-thing", "08-other")
        first, _ = self.scan_counting_git()
        self.commit("08 — The other")
        again, started = self.scan_counting_git(first)
        self.assertEqual(started, 1)
        self.assertEqual(self.marks(again, "build")["08"], ("Done", "landed"))


class FirstScanTest(RepoTestCase):
    """Through BoardController, with the stand-in window and a runner that runs each scan
    at once: a tab's first scan runs on the UI thread, so it runs no git; the first poll,
    off the UI thread, reads main."""

    def test_a_tabs_first_scan_runs_no_git_and_its_first_poll_shows_landed(self):
        build = self.effort("build", "07-thing")
        self.commit("07 — The thing")
        projects = self.repo.parent / "projects"
        projects.mkdir()
        ws_file = write_workspace(self.repo.parent / "ws.json", projects)
        window = FakeWindow()
        controller = BoardController(load_workspace(ws_file), ws_file, window,
                                     runner=SameThreadRunner())
        controller.start()
        with counting_processes() as started:
            controller.new_tab(self.repo)
        view = controller.front_tab().view
        self.assertEqual(started, [])
        self.assertEqual(self.shown_mark(view, build), ("Ready", "ready-for-agent"))
        window.tick()
        self.assertEqual(self.shown_mark(view, build), ("Done", "landed"))

    def shown_mark(self, view, effort):
        """The mark of Ticket 07 in the last Snapshot the Board view was told to show."""
        snapshot = [args[0] for name, args in view.told
                    if name in ("show_snapshot", "apply_changes")][-1]
        return self.marks(snapshot, effort.name)["07"]


class CeilingTest(RepoTestCase):
    def test_the_repo_is_not_looked_for_past_gits_ceiling_directories(self):
        build = self.effort("build", "07-thing")
        self.commit("07 — The thing")
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.repo)}):
            snapshot = scan(build)
        self.assertEqual(self.marks(snapshot, "build"), {"07": ("Ready", "ready-for-agent")})


class OutsideGitTest(unittest.TestCase):
    def test_a_folder_outside_git_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "plain"
            write_ticket(source / ".scratch" / "build", "07-thing")
            snapshot = scan(source)
        effort = snapshot.efforts[0]
        self.assertEqual([(t.mark, t.mark_word) for t in effort.tickets],
                         [("Ready", "ready-for-agent")])


if __name__ == "__main__":
    unittest.main()
