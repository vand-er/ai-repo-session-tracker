"""Cutting a cell's text to its width (src/views/text_fit.py): what a too-narrow cell
shows, and that an Activity keeps its age when cut. Pure functions: no window."""

import unittest

from src.model.builders import ActivityText
from src.views.text_fit import cut, cut_activity


class CutTest(unittest.TestCase):
    def test_text_that_fits_is_left_alone(self):
        self.assertEqual(cut("resolved", 8), "resolved")

    def test_longer_text_ends_in_an_ellipsis_at_the_width(self):
        self.assertEqual(cut("What the project rules keep", 12), "What the pr…")


class CutActivityTest(unittest.TestCase):
    def test_an_activity_that_fits_shows_whole(self):
        self.assertEqual(cut_activity(ActivityText("Editing shell.gd", "4s"), 30),
                         "Editing shell.gd · 4s")

    def test_a_cut_activity_keeps_its_age(self):
        self.assertEqual(cut_activity(ActivityText("Running tests", "14s"), 16),
                         "Running t… · 14s")

    def test_an_activity_with_no_age_is_cut_like_any_text(self):
        self.assertEqual(cut_activity(ActivityText("Reading 11-gamemanager.md"), 10),
                         "Reading 1…")

    def test_no_activity_shows_nothing(self):
        self.assertEqual(cut_activity(None, 10), "")


if __name__ == "__main__":
    unittest.main()
