import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.model.effort import scan, scan_effort
from tests import FIXTURES

GUIDE = FIXTURES / "field-guide-rebuild"
RETRO = FIXTURES / "retro-2026-10-19"


class FieldGuideRebuildTest(unittest.TestCase):
    """Expected values hand-counted from the 42 files' Status and Blocked by lines.

    resolved: 01-20, 23, 30, 32, 34, 37, 40, 41, 42 (28); claimed: 21 (1);
    open: 22, 24-29, 31, 33, 35, 36, 38, 39 (13)."""

    @classmethod
    def setUpClass(cls):
        cls.effort = scan_effort(GUIDE)

    def test_is_a_wayfinder_effort_with_the_maps_header(self):
        self.assertEqual(self.effort.name, "field-guide-rebuild")
        self.assertEqual(self.effort.kind, "wayfinder")
        self.assertEqual(self.effort.title, "The field guide rebuild: the map")
        self.assertEqual(self.effort.status, "")
        self.assertEqual(len(self.effort.tickets), 42)

    def test_counts_per_family_match_a_hand_count(self):
        self.assertEqual(self.effort.counts, {
            "Needs me": 13, "Waiting": 0, "Ready": 0, "Active": 1, "Finished": 0,
            "Done": 28, "Dropped": 0, "Unknown": 0,
        })

    def numbers(self, flag):
        return {t.ticket.number for t in self.effort.tickets if getattr(t, flag)}

    def test_the_one_claimed_ticket_is_active_and_not_on_the_frontier(self):
        active = [t for t in self.effort.tickets if t.ticket.family == "Active"]
        self.assertEqual([t.ticket.number for t in active], ["21"])
        self.assertFalse(active[0].blocked)
        self.assertFalse(active[0].frontier)

    def test_frontier_is_the_open_tickets_whose_blockers_are_all_resolved(self):
        # 22 (16-20), 28 (16-19, 23), 31 (10-13, 30), 38 (10-13, 37), 39 (10-13).
        self.assertEqual(self.numbers("frontier"), {"22", "28", "31", "38", "39"})

    def test_blocked_are_the_tickets_waiting_on_an_open_or_claimed_one(self):
        # 24-27 and 33 wait on 21 (claimed); 29 on 28; 35 on 24; 36 on 35.
        self.assertEqual(self.numbers("blocked"),
                         {"24", "25", "26", "27", "29", "33", "35", "36"})

    def test_no_spec_warning_on_a_map(self):
        self.assertFalse(self.effort.stale_spec)


class RetroTest(unittest.TestCase):
    def test_every_ticket_done_raises_the_spec_warning(self):
        effort = scan_effort(RETRO)
        self.assertEqual(effort.kind, "build")
        self.assertEqual(effort.title,
                         "The retro's fixes: the builders' pages and tools, true and short")
        self.assertEqual(effort.status, "ready-for-agent")
        self.assertEqual(len(effort.tickets), 7)
        self.assertEqual(effort.counts["Done"], 7)
        self.assertTrue(effort.stale_spec)
        self.assertEqual({t.ticket.number for t in effort.tickets if t.frontier or t.blocked}, set())


def write_effort(root, header, tickets):
    """A small Effort on disk: `header` is map.md's or spec.md's name and text,
    `tickets` maps file name to text."""
    (root / "issues").mkdir(parents=True)
    (root / header[0]).write_text(header[1], encoding="utf-8")
    for name, text in tickets.items():
        (root / "issues" / name).write_text(text, encoding="utf-8")
    return root


class BlockerEdgeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "edges"

    def test_ticket_with_no_blocked_by_line_is_not_blocked(self):
        effort = scan_effort(write_effort(self.root, ("spec.md", "# S\n\nStatus: open\n"), {
            "01-free.md": "# 01: Free\n\nStatus: ready-for-agent\n",
        }))
        (only,) = effort.tickets
        self.assertFalse(only.blocked)
        self.assertTrue(only.frontier)
        self.assertFalse(effort.stale_spec)

    def test_blocker_with_no_ticket_file_keeps_the_ticket_blocked(self):
        effort = scan_effort(write_effort(self.root, ("map.md", "# M\n"), {
            "01-done.md": "# 01: Done\n\nStatus: resolved\n",
            "02-waits.md": "# 02: Waits\n\nStatus: open\nBlocked by: 01, 07\n",
        }))
        waits = effort.tickets[1]
        self.assertTrue(waits.blocked)
        self.assertFalse(waits.frontier)
        self.assertEqual(waits.missing_blockers, ("07",))

    def test_dropped_blocker_counts_as_resolved(self):
        effort = scan_effort(write_effort(self.root, ("map.md", "# M\n"), {
            "01-dropped.md": "# 01: Dropped\n\nStatus: wontfix\n",
            "02-waits.md": "# 02: Waits\n\nStatus: needs-info\nBlocked by: 01\n",
        }))
        self.assertFalse(effort.tickets[1].blocked)
        self.assertTrue(effort.tickets[1].frontier)


class ScanTest(unittest.TestCase):
    def test_repo_root_returns_every_effort_in_name_order(self):
        # The fixtures folder copied under a repo root's `.scratch/`: ticket-shapes has
        # no map.md, spec.md or issues/, so it is not an Effort.
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / ".scratch"
            shutil.copytree(FIXTURES, scratch)
            snapshot = scan(tmp)
            self.assertEqual([e.name for e in snapshot.efforts],
                             ["field-guide-rebuild", "progress-marks", "retro-2026-10-19",
                              "ticket-check-drift", "ticket-check-range"])
            self.assertEqual(snapshot.efforts[0].counts, scan_effort(GUIDE).counts)

    def test_one_effort_folder_returns_just_it(self):
        snapshot = scan(RETRO)
        self.assertEqual(len(snapshot.efforts), 1)
        self.assertEqual(snapshot.efforts[0], scan_effort(RETRO))

    def test_two_scans_of_the_same_folder_compare_equal(self):
        self.assertEqual(scan(GUIDE), scan(GUIDE))
        self.assertEqual(scan_effort(RETRO), scan_effort(RETRO))


class NoGuiTest(unittest.TestCase):
    def test_module_imports_nothing_from_the_gui(self):
        code = ("import sys, src.model.effort; "
                "sys.exit(any(m.split('.')[0] in ('tkinter', 'customtkinter') for m in sys.modules))")
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run([sys.executable, "-c", code], cwd=root)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
