"""A normal start (no `--shot`) loads none of the Windows-only dev tools: the window
placement guard and the screenshot tool load only when `--shot` runs. Checked in a fresh
interpreter, through `main`, with a stand-in for the built app so no window opens."""

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEV_TOOLS = ("src.views.placement", "src.views.screenshot")

_START = """
import sys
import src.app

class Window:
    def after(self, *_a): pass
    def mainloop(self): pass

class Controller:
    def front_tab(self): return None

src.app.build_app = lambda workspace_file=None: (Window(), Controller())
from src.__main__ import main
main(ARGV)
print(",".join(m for m in DEV_TOOLS if m in sys.modules))
"""


def loaded_dev_tools(argv):
    """Run `main(argv)` in a fresh interpreter; the dev tools it left loaded, comma-joined."""
    code = _START.replace("ARGV", repr(argv)).replace("DEV_TOOLS", repr(DEV_TOOLS))
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True,
                            text=True, check=True)
    return result.stdout.strip()


class StartUpTest(unittest.TestCase):
    def test_a_normal_start_loads_no_windows_only_dev_tool(self):
        self.assertEqual(loaded_dev_tools(["--workspace", "unused.json"]), "")


if __name__ == "__main__":
    unittest.main()
