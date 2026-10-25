"""The layout guard: the app lays out on the grid only, never with `.place(` or `.pack(`."""

import unittest

from tests.guards.literals import layout_violations
from tests.guards.planted import REPO, planted_tree


class LayoutGuardTest(unittest.TestCase):
    def test_the_app_never_places_or_packs(self):
        self.assertEqual(layout_violations(REPO), [])

    def test_a_planted_pack_call_fails_naming_it(self):
        planted = "def build(frame, label):\n    label.grid(row=0)\n    frame.pack(fill='x')\n"
        with planted_tree({"src/views/planted.py": planted}) as root:
            violations = layout_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.views.planted", violations[0])
        self.assertIn(".pack(", violations[0])
        self.assertIn("line 3", violations[0])

    def test_a_planted_place_call_fails_naming_it(self):
        planted = "def build(badge):\n    badge.place(x=4, y=2)\n"
        with planted_tree({"src/views/planted.py": planted}) as root:
            violations = layout_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn(".place(", violations[0])
