"""The tab's branch setting (open-source-release 06): an optional per-tab value in the
Workspace file naming the branch main history is read from. A tab entry is its Source
folder, or `{"folder": ..., "branch": ...}` when the setting is set."""

import json
import tempfile
import unittest
from pathlib import Path

from src.controller import BoardController
from src.runner import SameThreadRunner
from src.workspace import load_workspace, save_workspace
from tests.fakes import FakeWindow, write_workspace
from tests.test_main_landed import RepoTestCase, write_ticket


class WorkspaceBranchTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "ws.json"
        self.one, self.two = Path(tmp.name) / "one", Path(tmp.name) / "two"

    def test_a_workspace_file_with_no_branch_setting_loads_and_saves_unchanged(self):
        before = {"poll_ms": 2000, "tabs": [str(self.one), str(self.two)], "active": 1,
                  "palette": "ember"}
        self.path.write_text(json.dumps(before), encoding="utf-8")
        workspace = load_workspace(self.path)
        self.assertEqual(workspace.folders, [self.one, self.two])
        self.assertIsNone(workspace.branch(self.one))
        save_workspace(workspace, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), before)

    def test_a_tabs_branch_setting_round_trips_through_save_and_load(self):
        data = {"tabs": [str(self.one), {"folder": str(self.two), "branch": "trunk"}],
                "active": 0, "palette": None}
        self.path.write_text(json.dumps(data), encoding="utf-8")
        workspace = load_workspace(self.path)
        self.assertEqual(workspace.folders, [self.one, self.two])
        self.assertEqual(workspace.branch(self.two), "trunk")
        self.assertIsNone(workspace.branch(self.one))
        save_workspace(workspace, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), data)

    def test_a_damaged_tab_entry_is_dropped_and_a_damaged_branch_ignored(self):
        self.path.write_text(json.dumps({"tabs": [
            {"branch": "trunk"}, {"folder": str(self.one), "branch": 7}, 3]}),
            encoding="utf-8")
        workspace = load_workspace(self.path)
        self.assertEqual(workspace.folders, [self.one])
        self.assertIsNone(workspace.branch(self.one))


class TabReadsItsBranchTest(RepoTestCase):
    """Through BoardController with the stand-in window: the tab's first poll reads main
    history from the branch its Workspace entry names."""

    def launch(self, tabs):
        projects = self.repo.parent / "projects"
        projects.mkdir(exist_ok=True)
        ws_file = write_workspace(self.repo.parent / "ws.json", projects, tabs=tabs, active=0)
        self.window = FakeWindow()
        controller = BoardController(load_workspace(ws_file), ws_file, self.window,
                                     runner=SameThreadRunner())
        controller.start()
        self.window.tick()
        return controller.front_tab()

    def shown(self, tab):
        told = [args[0] for name, args in tab.view.told
                if name in ("show_snapshot", "apply_changes")]
        effort = told[-1].efforts[0]
        return {t.ticket.number: (t.mark, t.mark_word) for t in effort.tickets}

    def test_the_tab_reads_landed_from_its_branch_setting(self):
        self.effort("build", "07-seven", "08-eight")
        self.commit("08 — On release", branch="release")
        self.commit("07 — On main")
        tab = self.launch([{"folder": str(self.repo), "branch": "release"}])
        self.assertEqual(self.shown(tab), {"07": ("Ready", "ready-for-agent"),
                                           "08": ("Done", "landed")})

    def test_a_folder_outside_git_shows_its_tickets_without_landed_or_an_error(self):
        plain = self.repo.parent / "plain"
        write_ticket(plain / ".scratch" / "build", "07-thing")
        tab = self.launch([str(plain)])
        self.assertEqual(tab.error, "")
        self.assertNotIn("show_unreadable", [name for name, _ in tab.view.told])
        self.assertEqual(self.shown(tab), {"07": ("Ready", "ready-for-agent")})


if __name__ == "__main__":
    unittest.main()
