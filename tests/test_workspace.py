"""The Workspace: which tabs are open, their Source folders and the chosen palette,
loaded from and saved to a Workspace file. Tests use a temp file, never the real one."""

import tempfile
import unittest
from pathlib import Path

from src.workspace import Workspace, load_workspace, save_workspace


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "sub" / "workspace.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_gives_no_tabs_and_no_saved_palette(self):
        ws = load_workspace(self.path)
        self.assertEqual(ws.folders, [])
        self.assertIsNone(ws.active)
        self.assertIsNone(ws.palette)

    def test_saved_tabs_and_palette_come_back_on_load(self):
        a, b = self.dir / "repo-a", self.dir / "effort-b"
        save_workspace(Workspace(tabs=[a, b], active=1, palette="dusk"), self.path)
        ws = load_workspace(self.path)
        self.assertEqual(ws.folders, [a, b])
        self.assertEqual(ws.active, 1)
        self.assertEqual(ws.palette, "dusk")

    def test_a_damaged_file_loads_as_an_empty_workspace(self):
        self.path.parent.mkdir(parents=True)
        for text in ("{not json", "[1, 2]", '{"tabs": "x", "active": "y", "palette": 5}', "\xff"):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="latin-1")
                ws = load_workspace(self.path)
                self.assertEqual((ws.folders, ws.active, ws.palette), ([], None, None))

    def test_a_fronted_index_past_the_tabs_fronts_the_last_tab(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"tabs": ["C:/a", "C:/b"], "active": 7}', encoding="utf-8")
        self.assertEqual(load_workspace(self.path).active, 1)

    def test_settings_other_tickets_add_survive_a_save(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"tabs": [], "poll_ms": 2500, "show_area": true}', encoding="utf-8")
        ws = load_workspace(self.path)
        self.assertEqual(ws.setting("poll_ms", 1000), 2500)
        self.assertEqual(ws.setting("sessions_window_minutes", 30), 30)
        ws.settings["show_detail"] = False
        save_workspace(ws, self.path)
        again = load_workspace(self.path)
        self.assertEqual(again.setting("poll_ms", 1000), 2500)
        self.assertIs(again.setting("show_area", False), True)
        self.assertIs(again.setting("show_detail", True), False)

    def test_opening_a_tab_adds_its_folder_and_fronts_it(self):
        ws = Workspace()
        self.assertEqual(ws.open_tab(self.dir / "a"), 0)
        self.assertEqual(ws.open_tab(self.dir / "b"), 1)
        self.assertEqual(ws.folders, [self.dir / "a", self.dir / "b"])
        self.assertEqual(ws.active, 1)

    def test_closing_a_tab_fronts_its_neighbour(self):
        a, b, c = (self.dir / n for n in "abc")
        ws = Workspace(tabs=[a, b, c], active=2)
        ws.close_tab(2)
        self.assertEqual((ws.folders, ws.active), ([a, b], 1))
        ws.close_tab(0)
        self.assertEqual((ws.folders, ws.active), ([b], 0))
        ws.close_tab(0)
        self.assertEqual((ws.folders, ws.active), ([], None))

    def test_closing_a_tab_before_the_fronted_one_keeps_the_same_tab_in_front(self):
        a, b, c = (self.dir / n for n in "abc")
        ws = Workspace(tabs=[a, b, c], active=2)
        ws.close_tab(0)
        self.assertEqual(ws.folders[ws.active], c)

    def test_reopen_last_brings_back_only_the_most_recently_closed_folder(self):
        a, b = self.dir / "a", self.dir / "b"
        ws = Workspace(tabs=[a, b], active=0)
        ws.close_tab(0)
        ws.close_tab(0)
        self.assertEqual(ws.reopen_last(), 0)
        self.assertEqual((ws.folders, ws.active), ([b], 0))
        self.assertIsNone(ws.reopen_last())
        self.assertEqual(ws.folders, [b])

    def test_a_setting_of_the_wrong_type_reads_as_its_default(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"poll_ms": "fast"}', encoding="utf-8")
        self.assertEqual(load_workspace(self.path).setting("poll_ms", 1000), 1000)


if __name__ == "__main__":
    unittest.main()
