"""The layer guard. Every app module is found by walking the package; no hand list."""

import unittest

from tests.guards.layers import (controller_violations, controllers, model_violations,
                                 platform_violations, start_toolkit_check, toolkit_violations)
from tests.guards.planted import REPO, planted_tree
from tests.guards.tree import Tree, fresh_check, fresh_started


class ModelLayerTest(unittest.TestCase):
    def test_model_imports_only_model_and_standard_library(self):
        self.assertEqual(model_violations(REPO), [])

    def test_a_planted_model_module_importing_the_app_fails_naming_it(self):
        with planted_tree({"src/model/planted.py": "from src.workspace import ENV_VAR\n"}) as root:
            violations = model_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.model.planted", violations[0])
        self.assertIn("src.workspace", violations[0])

    def test_a_model_module_may_import_the_platform_module(self):
        with planted_tree({"src/model/planted.py": "from src.system import WINDOWS\n"}) as root:
            self.assertEqual(model_violations(root), [])


class PlatformLayerTest(unittest.TestCase):
    def test_the_platform_module_imports_only_the_standard_library(self):
        self.assertEqual(platform_violations(REPO), [])

    def test_a_platform_module_importing_the_app_fails_naming_it(self):
        planted = "import json\nfrom src.model import ticket\n"
        with planted_tree({"src/system.py": planted}) as root:
            violations = platform_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.system", violations[0])
        self.assertIn("src.model", violations[0])


class ControllerLayerTest(unittest.TestCase):
    def test_the_board_and_sessions_controllers_are_the_controllers(self):
        self.assertEqual(controllers(REPO), ["src.controller", "src.sessions_controller"])

    def test_controllers_never_import_views(self):
        self.assertEqual(controller_violations(REPO), [])

    def test_a_planted_controller_importing_a_view_fails_naming_it(self):
        planted = "def build():\n    from src.views.window import MainWindow\n"
        with planted_tree({"src/review_controller.py": planted}) as root:
            violations = controller_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.review_controller", violations[0])
        self.assertIn("src.views.window", violations[0])


PLANTED_TOOLKIT = {"src/exporter.py": "import tkinter.filedialog\n\n\ndef ask():\n    return None\n"}
fresh_check("toolkit rule, real tree", lambda: start_toolkit_check(REPO))
fresh_check("toolkit rule, planted tree",
            lambda: start_toolkit_check(Tree(REPO, PLANTED_TOOLKIT)))


class ToolkitLayerTest(unittest.TestCase):
    """Checked in a fresh interpreter, so no other test's imports can hide a leak. The real
    tree and the planted one are checked side by side with the other guards' fresh
    interpreters (`fresh_check`), since an interpreter's start is most of the cost and the
    hook must stay fast."""

    @classmethod
    def setUpClass(cls):
        cls.real = toolkit_violations(REPO, fresh_started("toolkit rule, real tree"))
        with planted_tree(PLANTED_TOOLKIT) as root:
            cls.planted = toolkit_violations(root, fresh_started("toolkit rule, planted tree"))

    def test_no_module_outside_the_views_imports_a_gui_toolkit(self):
        self.assertEqual(self.real, [])

    def test_a_planted_new_module_importing_a_toolkit_fails_naming_it(self):
        violations = self.planted
        self.assertEqual(len(violations), 1)
        self.assertIn("src.exporter", violations[0])
        self.assertIn("tkinter", violations[0])


if __name__ == "__main__":
    unittest.main()
