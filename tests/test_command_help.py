"""The `wayfinder-board` command: `--help` answers before any app code loads, so it works on a
system where the app itself can't start yet. Checked in a fresh interpreter so other tests
cannot hide a leak."""

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

HELP_THEN_LIST_MODULES = (
    "import sys\n"
    "from src.__main__ import main\n"
    "try:\n"
    "    main(['--help'])\n"
    "except SystemExit as stop:\n"
    "    code = stop.code\n"
    "else:\n"
    "    code = 'returned'\n"
    "loaded = sorted(m for m in sys.modules if m.split('.')[0] in "
    "('tkinter', '_tkinter', 'customtkinter') or m == 'src.app' or m.startswith('src.views'))\n"
    "print('EXIT', code)\n"
    "print('LOADED', ','.join(loaded))\n"
)


class HelpTest(unittest.TestCase):
    def test_help_prints_usage_and_loads_no_gui_module(self):
        result = subprocess.run([sys.executable, "-c", HELP_THEN_LIST_MODULES], cwd=REPO,
                                capture_output=True, text=True, check=True)
        self.assertIn("usage: wayfinder-board", result.stdout)
        self.assertIn("EXIT 0", result.stdout)
        self.assertEqual(result.stdout.splitlines()[-1].strip(), "LOADED")


if __name__ == "__main__":
    unittest.main()
