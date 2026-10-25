"""The View toggles (detail pane, Area column) are kept in the Workspace file."""

import tempfile
import unittest
from pathlib import Path

from src.model.view_settings import AREA_COLUMN, DETAIL_PANE, is_on, toggle
from src.workspace import Workspace, load_workspace, save_workspace


class ViewSettingsTest(unittest.TestCase):
    def test_defaults_show_the_pane_and_hide_the_area_column(self):
        ws = Workspace()
        self.assertTrue(is_on(ws, DETAIL_PANE))
        self.assertFalse(is_on(ws, AREA_COLUMN))

    def test_a_toggle_survives_a_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ws.json"
            ws = Workspace()
            self.assertTrue(toggle(ws, AREA_COLUMN))
            self.assertFalse(toggle(ws, DETAIL_PANE))
            save_workspace(ws, path)
            again = load_workspace(path)
            self.assertTrue(is_on(again, AREA_COLUMN))
            self.assertFalse(is_on(again, DETAIL_PANE))

    def test_a_damaged_value_reads_as_the_default(self):
        ws = Workspace(settings={AREA_COLUMN: "yes", DETAIL_PANE: 0})
        self.assertFalse(is_on(ws, AREA_COLUMN))
        self.assertTrue(is_on(ws, DETAIL_PANE))


if __name__ == "__main__":
    unittest.main()
