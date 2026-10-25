import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.workspace import ENV_VAR, default_workspace_path, workspace_path
from tests import FIXTURES


class PlaceholderTest(unittest.TestCase):
    def test_placeholder(self):
        self.assertTrue(True)


class FixtureTest(unittest.TestCase):
    def test_map_effort_has_42_tickets(self):
        effort = FIXTURES / "field-guide-rebuild"
        self.assertTrue((effort / "map.md").is_file())
        self.assertEqual(len(list((effort / "issues").glob("*.md"))), 42)

    def test_spec_effort_has_7_tickets(self):
        effort = FIXTURES / "retro-2026-10-19"
        self.assertTrue((effort / "spec.md").is_file())
        self.assertEqual(len(list((effort / "issues").glob("*.md"))), 7)


class WorkspacePathTest(unittest.TestCase):
    def setUp(self):
        default = default_workspace_path()
        self.default = default
        self.before = default.stat().st_mtime_ns if default.exists() else None

    def tearDown(self):
        after = self.default.stat().st_mtime_ns if self.default.exists() else None
        self.assertEqual(after, self.before, "tests touched the default Workspace file")

    def test_test_run_points_away_from_default(self):
        self.assertNotEqual(workspace_path(), self.default)

    def test_env_var_points_at_temp_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "workspace.json"
            with mock.patch.dict(os.environ, {ENV_VAR: str(target)}):
                path = workspace_path()
                self.assertEqual(path, target)
                path.write_text("{}", encoding="utf-8")
            self.assertEqual(target.read_text(encoding="utf-8"), "{}")

    def test_explicit_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ws.json"
            self.assertEqual(workspace_path(target), target)

    def test_default_is_under_user_profile(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(ENV_VAR, None)
            self.assertEqual(workspace_path(), self.default)
        self.assertTrue(self.default.is_relative_to(Path.home()))

    def test_model_imports_no_gui(self):
        # In a fresh interpreter: test discovery imports every test module first, and the
        # view tests (test_shapes, test_placement) load the toolkit.
        import subprocess
        import sys
        code = ("import sys, src.workspace\n"
                "print(any(m in sys.modules for m in ('tkinter', 'customtkinter')))\n")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parent.parent, check=True)
        self.assertEqual(result.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
