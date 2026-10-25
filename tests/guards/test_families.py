"""The Family guard: a Family's name is written as a string only in the Ticket module
(`src/model/ticket.py`); every other module imports it, so a new Family is one edit."""

import unittest

from tests.guards.literals import family_names, family_violations
from tests.guards.planted import REPO, planted_tree


class FamilyGuardTest(unittest.TestCase):
    def test_the_ticket_module_defines_every_family(self):
        self.assertEqual(family_names(REPO), {"Needs me", "Waiting", "Ready", "Active",
                                              "Finished", "Done", "Dropped", "Unknown"})

    def test_no_module_but_the_ticket_module_writes_a_family_name(self):
        self.assertEqual(family_violations(REPO), [])

    def test_a_planted_family_name_in_a_view_fails_naming_it(self):
        planted = "def closed(counts):\n    return counts['Done'] + counts['Dropped']\n"
        with planted_tree({"src/views/planted.py": planted}) as root:
            violations = family_violations(root)
        self.assertEqual(len(violations), 2)
        self.assertIn("src.views.planted line 2", violations[0])
        self.assertIn("'Done'", violations[0])
        self.assertIn("'Dropped'", violations[1])

    def test_a_status_word_that_is_no_family_passes(self):
        planted = "STATES = ('running', 'finished', 'landed')\n"
        with planted_tree({"src/model/planted.py": planted}) as root:
            self.assertEqual(family_violations(root), [])

    def test_unknown_is_a_family_name_like_any_other_even_in_the_sessions_tab(self):
        planted = "NOT_GIVEN = 'Unknown'\n"
        for module in ("src/model/planted.py", "src/model/sessions_tab.py"):
            with planted_tree({module: planted}) as root:
                violations = family_violations(root)
            self.assertEqual(len(violations), 1, module)
            self.assertIn("'Unknown'", violations[0])
