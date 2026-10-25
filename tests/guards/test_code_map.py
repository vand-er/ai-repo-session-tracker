"""The map-freshness guard: every module of the app is named in the code map.

The code map, `docs/architecture.md`, is written by hand. A module counts as named when
its dotted name appears in backticks there (`src.model.ticket`); a longer name such as
`src.model.ticket.parse_ticket` does not name `src.model.ticket`, nor does `src.model`
name its modules. Modules are found by walking the app package (`app_modules`), so a new
module fails this guard until a line for it is written into the map.
"""

import re
import unittest

from tests.guards.planted import REPO, planted_tree
from tests.guards.tree import app_modules, tree

MAP = "docs/architecture.md"


def map_gaps(root):
    """One line per app module under `root` that the code map doesn't name."""
    if not tree(root).is_file(MAP):
        return [f"{MAP} is missing: the code map names every app module"]
    named = set(re.findall(r"`([^`\n]+)`", tree(root).text(MAP)))
    return [f"{name} is not named in {MAP}: add a line giving its layer and what it owns"
            for name in app_modules(root) if name not in named]


class CodeMapTest(unittest.TestCase):

    def test_the_real_tree_has_every_module_in_the_map(self):
        self.assertEqual(map_gaps(REPO), [])

    def test_a_planted_new_module_missing_from_the_map_fails_naming_it(self):
        with planted_tree({"src/model/exporter.py": "def export():\n    pass\n"}) as root:
            gaps = map_gaps(root)
        self.assertEqual(len(gaps), 1, gaps)
        self.assertIn("src.model.exporter", gaps[0])

    def test_a_missing_map_fails_naming_it(self):
        with planted_tree({MAP: None}) as root:
            gaps = map_gaps(root)
        self.assertEqual(len(gaps), 1, gaps)
        self.assertIn(MAP, gaps[0])


if __name__ == "__main__":
    unittest.main()
