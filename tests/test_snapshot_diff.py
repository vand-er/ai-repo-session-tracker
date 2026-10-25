"""The diff step of polling: the last Snapshot and a fresh one in, the rows to redraw and
the rows to flash out. Snapshots come from scanning a temp copy of a fixture Effort, so a
change is made the way the owner makes it: by editing a Ticket file."""

import shutil
import tempfile
import unittest
from pathlib import Path

from src.model.effort import scan
from src.model.snapshot_diff import diff_snapshots
from tests import FIXTURES

EFFORT = "field-guide-rebuild"


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.root = self.temp / EFFORT
        shutil.copytree(FIXTURES / EFFORT, self.root)
        self.issues = self.root / "issues"
        self.old = scan(self.root)

    def edit(self, name, old, new):
        path = self.issues / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return path

    def test_an_unchanged_snapshot_redraws_and_flashes_nothing(self):
        changes = diff_snapshots(self.old, scan(self.root), EFFORT)
        self.assertEqual(changes.redraw, ())
        self.assertEqual(changes.flash, ())
        self.assertFalse(changes.reshape)
        self.assertFalse(changes.header)
        self.assertFalse(changes)

    def test_one_status_change_redraws_and_flashes_exactly_that_row(self):
        # 22 is open; claiming it leaves every Ticket it blocks still blocked.
        path = self.edit("22-settings-file.md", "Status: open", "Status: claimed")
        changes = diff_snapshots(self.old, scan(self.root), EFFORT)
        self.assertEqual(changes.redraw, (path,))
        self.assertEqual(changes.flash, (path,))
        self.assertFalse(changes.reshape)

    def test_a_status_change_that_moves_family_redraws_the_header(self):
        self.edit("22-settings-file.md", "Status: open", "Status: claimed")
        self.assertTrue(diff_snapshots(self.old, scan(self.root), EFFORT).header)

    def test_an_edit_that_keeps_the_status_redraws_the_row_without_a_flash(self):
        path = self.edit("22-settings-file.md", "Status: open", "Status: open\nArea: sim")
        changes = diff_snapshots(self.old, scan(self.root), EFFORT)
        self.assertEqual(changes.redraw, (path,))
        self.assertEqual(changes.flash, ())

    def test_a_new_ticket_file_reshapes_the_table(self):
        shutil.copy(self.issues / "22-settings-file.md", self.issues / "43-new.md")
        changes = diff_snapshots(self.old, scan(self.root), EFFORT)
        self.assertTrue(changes.reshape)

    def test_a_deleted_ticket_file_reshapes_the_table(self):
        (self.issues / "42-map-page-reload.md").unlink()
        self.assertTrue(diff_snapshots(self.old, scan(self.root), EFFORT).reshape)

    def test_no_last_snapshot_reshapes_everything(self):
        changes = diff_snapshots(None, self.old, EFFORT)
        self.assertTrue(changes.reshape)
        self.assertTrue(changes.header)


if __name__ == "__main__":
    unittest.main()
