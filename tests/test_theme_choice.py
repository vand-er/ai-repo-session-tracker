"""The chosen theme: saved to the Workspace file when it changes, restored on launch, and a
bad saved value never stops the app from starting (ticket 11). The window is a stand-in."""

import tempfile
import unittest
from pathlib import Path

from src.controller import BoardController, restore_palette
from src.workspace import load_workspace
from tests.fakes import FakeWindow, write_workspace

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retro-2026-10-19"


class ThemeChoiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = write_workspace(Path(self._tmp.name) / "workspace.json",
                                    Path(self._tmp.name) / "projects")

    def tearDown(self):
        self._tmp.cleanup()

    def launch(self):
        """What the app does at launch: read the file, pick the palette to draw in."""
        workspace = load_workspace(self.path)
        palette = restore_palette(workspace)
        return BoardController(workspace, self.path, FakeWindow()), palette

    def test_with_no_saved_choice_the_app_launches_in_graphite(self):
        controller, palette = self.launch()
        self.assertEqual(palette["name"], "graphite")
        self.assertEqual(controller.workspace.palette, "graphite")

    def test_a_chosen_theme_restyles_the_window_and_survives_a_relaunch(self):
        controller, _ = self.launch()
        controller.set_palette("paper")
        self.assertEqual(controller.window.themes, ["paper"])
        _, palette = self.launch()
        self.assertEqual(palette["name"], "paper")

    def test_a_theme_switch_restyles_the_views_in_place(self):
        """The window recolours what it has drawn: every Board and the Sessions tab keep
        their views, nothing is redrawn from a Snapshot, no file is read again."""
        controller, _ = self.launch()
        controller.start()
        controller.new_tab(FIXTURE)
        tab = controller.front_tab()
        controller.select_file(tab, sorted((FIXTURE / "issues").glob("*.md"))[0])
        controller.open_sessions()
        views = list(controller.window.boards)
        told = list(tab.view.told)
        scans = tab.scans
        controller.set_palette("paper")
        self.assertEqual(controller.window.themes, ["paper"])
        self.assertEqual(controller.window.boards, views)
        self.assertIs(controller.sessions.view, views[-1])
        self.assertEqual(tab.view.told, told)
        self.assertEqual(tab.scans, scans)

    def test_an_unknown_saved_theme_launches_in_graphite_without_rewriting_the_file(self):
        self.path.write_text('{"tabs": [], "palette": "dusk"}', encoding="utf-8")
        controller, palette = self.launch()
        self.assertEqual(palette["name"], "graphite")
        self.assertEqual(controller.workspace.palette, "graphite")
        self.assertIn('"dusk"', self.path.read_text(encoding="utf-8"))

    def test_a_damaged_workspace_file_launches_in_graphite(self):
        self.path.write_text('{"palette": ', encoding="utf-8")
        _, palette = self.launch()
        self.assertEqual(palette["name"], "graphite")

    def test_choosing_an_unknown_theme_saves_graphite(self):
        controller, _ = self.launch()
        controller.set_palette("dusk")
        self.assertEqual(load_workspace(self.path).palette, "graphite")


if __name__ == "__main__":
    unittest.main()
