"""The controller's View controls: header sorting, the pane and Area toggles, Refresh now.
Driven through BoardController with a stand-in window, so no GUI is built."""

import tempfile
import unittest
from pathlib import Path

from src.controller import BoardController
from src.model.view_settings import AREA_COLUMN, DETAIL_PANE
from src.workspace import load_workspace
from tests.fakes import FakeWindow, write_workspace

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retro-2026-10-19"


class ViewControlsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws_file = write_workspace(Path(tmp.name) / "ws.json", Path(tmp.name) / "projects")
        self.controller = self.launch(load_workspace(self.ws_file))
        self.controller.new_tab(FIXTURE)
        self.tab = self.controller.front_tab()

    def launch(self, workspace):
        controller = BoardController(workspace, self.ws_file, FakeWindow())
        controller.start()
        return controller

    def test_a_new_board_gets_the_default_sort_and_toggles(self):
        view = self.tab.view
        self.assertEqual(view.sort, ("num", False))
        self.assertTrue(view.detail_pane)
        self.assertEqual(view.columns, {"area": False})

    def test_header_clicks_sort_then_reverse(self):
        self.tab.view.on_sort("status")
        self.assertEqual(self.tab.view.sort, ("status", False))
        self.tab.view.on_sort("status")
        self.assertEqual(self.tab.view.sort, ("status", True))

    def test_the_sort_survives_a_rescan_and_a_new_view(self):
        self.controller.sort_by(self.tab, "updated")
        self.controller.refresh_now()
        self.controller.set_palette("placeholder")   # restyles every Board view
        self.assertEqual(self.tab.view.sort, ("updated", False))

    def test_refresh_now_scans_the_fronted_tab_once(self):
        before = self.tab.scans
        self.controller.refresh_now()
        self.assertEqual(self.tab.scans, before + 1)

    def test_toggles_reach_the_views_and_survive_a_relaunch(self):
        self.controller.toggle_view(DETAIL_PANE)
        self.controller.toggle_view(AREA_COLUMN)
        self.assertFalse(self.tab.view.detail_pane)
        self.assertTrue(self.tab.view.columns["area"])
        again = self.launch(load_workspace(self.ws_file))
        view = again.front_tab().view
        self.assertFalse(view.detail_pane)
        self.assertTrue(view.columns["area"])
        self.assertTrue(again.view_on(AREA_COLUMN))


if __name__ == "__main__":
    unittest.main()
