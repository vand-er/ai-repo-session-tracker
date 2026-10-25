"""Where a scripted window goes (src/views/placement.py): the work area of a monitor the
owner is not looking at. `away_work_area` is pure: monitors in, a rect out."""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from src.views.placement import away_work_area, owner_note, owner_point
from src.workspace import load_workspace

# (monitor rect, work-area rect, is primary), rects (left, top, right, bottom)
LEFT = ((0, 0, 1920, 1080), (0, 0, 1920, 1040), True)
RIGHT = ((1920, 0, 3840, 1080), (1920, 0, 3840, 1040), False)
THIRD = ((3840, 0, 5760, 1080), (3840, 0, 5760, 1040), False)


class AwayWorkAreaTest(unittest.TestCase):
    def test_the_owner_on_the_left_monitor_sends_it_to_the_right(self):
        self.assertEqual(away_work_area([LEFT, RIGHT], (900, 500)), RIGHT[1])

    def test_the_owner_on_the_right_monitor_sends_it_to_the_left(self):
        self.assertEqual(away_work_area([LEFT, RIGHT], (2500, 500)), LEFT[1])

    def test_with_three_monitors_it_takes_the_first_the_owner_is_not_on(self):
        self.assertEqual(away_work_area([LEFT, RIGHT, THIRD], (900, 500)), RIGHT[1])
        self.assertEqual(away_work_area([LEFT, RIGHT, THIRD], (4000, 500)), LEFT[1])

    def test_one_monitor_is_the_only_place_to_go(self):
        self.assertEqual(away_work_area([LEFT], (900, 500)), LEFT[1])

    def test_with_no_owner_point_it_goes_away_from_the_primary(self):
        self.assertEqual(away_work_area([RIGHT, LEFT], None), RIGHT[1])

    def test_a_point_on_no_monitor_counts_as_the_primary(self):
        self.assertEqual(away_work_area([LEFT, RIGHT], (-50, -50)), RIGHT[1])

    def test_no_monitors_gives_none(self):
        self.assertIsNone(away_work_area([], (0, 0)))


@unittest.skipUnless(sys.platform.startswith("win"), "the placement guard is Windows only")
class OwnerNoteTest(unittest.TestCase):
    """The owner's note (the Workspace's optional `owner_window_note` path) names where the
    owner's window is; with no path set the guard reads no note and raises nothing."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_a_set_note_path_gives_the_centre_of_the_window_it_notes(self):
        note = self.folder / "window.json"
        note.write_text(json.dumps({"x": 100, "y": 200, "width": 800, "height": 600}), encoding="utf-8")
        self.assertEqual(owner_point(note), (500, 500))

    def test_the_note_path_is_an_optional_workspace_setting_unset_by_default(self):
        plain = self.folder / "plain.json"
        plain.write_text(json.dumps({"tabs": [], "palette": "graphite"}), encoding="utf-8")
        named = self.folder / "named.json"
        named.write_text(json.dumps({"tabs": [], "owner_window_note": "C:/notes/window.json"}),
                         encoding="utf-8")
        self.assertIsNone(owner_note(load_workspace(plain)))
        self.assertEqual(owner_note(load_workspace(named)), Path("C:/notes/window.json"))

    def test_with_no_note_path_it_reads_no_note_and_raises_nothing(self):
        point = owner_point(None)    # the window in front now, or None
        self.assertTrue(point is None or len(point) == 2)

    def test_a_missing_or_damaged_note_raises_nothing(self):
        bad = self.folder / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        for note in (self.folder / "missing.json", bad):
            with contextlib.redirect_stderr(io.StringIO()):
                point = owner_point(note)
            self.assertTrue(point is None or len(point) == 2)

    def test_a_missing_or_damaged_note_says_so_on_stderr(self):
        bad = self.folder / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        for note in (self.folder / "missing.json", bad):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                owner_point(note)
            lines = err.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("can't read the owner's window note", lines[0])
            self.assertIn(str(note), lines[0])


if __name__ == "__main__":
    unittest.main()
