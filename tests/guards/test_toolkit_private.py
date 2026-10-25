"""The toolkit-private guard: only the adapter module touches customtkinter's internals
(the rule is in `private.py`)."""

import unittest

from tests.guards.planted import REPO, planted_tree
from tests.guards.private import private_violations


class ToolkitPrivateTest(unittest.TestCase):
    def test_only_the_adapter_touches_customtkinter_internals(self):
        self.assertEqual(private_violations(REPO), [])

    def test_a_planted_parent_canvas_read_in_another_view_fails_naming_it(self):
        planted = "def scroll_canvas(frame):\n    return frame._parent_canvas\n"
        with planted_tree({"src/views/planted_view.py": planted}) as root:
            violations = private_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.views.planted_view line 2", violations[0])
        self.assertIn("_parent_canvas", violations[0])

    def test_a_planted_import_from_a_toolkit_internal_package_fails_naming_it(self):
        planted = "from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass\n"
        with planted_tree({"src/views/planted_view.py": planted}) as root:
            violations = private_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.views.planted_view line 1", violations[0])
        self.assertIn("customtkinter.windows.widgets", violations[0])

    def test_a_planted_internal_import_outside_the_views_fails_naming_it(self):
        planted = ("import customtkinter.windows.widgets.scaling\n"
                   "from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass\n")
        with planted_tree({"src/exporter.py": planted}) as root:
            violations = private_violations(root)
        self.assertEqual(len(violations), 2, violations)
        self.assertIn("src.exporter line 1", violations[0])
        self.assertIn("customtkinter.windows.widgets.scaling", violations[0])
        self.assertIn("src.exporter line 2", violations[1])

    def test_a_private_read_outside_the_views_is_no_toolkit_reach(self):
        planted = "import os\n\n\ndef stop():\n    os._exit(0)\n"
        with planted_tree({"src/app_planted.py": planted}) as root:
            self.assertEqual(private_violations(root), [])

    def test_the_views_own_private_state_is_not_flagged(self):
        planted = ("class Pane:\n    def __init__(self):\n        self._rows = []\n\n"
                   "    @classmethod\n    def make(cls):\n        return cls._made\n")
        with planted_tree({"src/views/planted_view.py": planted}) as root:
            self.assertEqual(private_violations(root), [])


if __name__ == "__main__":
    unittest.main()
