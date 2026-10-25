"""Builders seen from the Sessions side (the sessions seam): the Sessions tab lists each
subagent Builder as its own row under its orchestrator, and an Effort's header lists the
Builders working no Ticket of it. Scanned from the builders fixture with a stand-in clock."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from src.model.effort import Effort
from src.sessions_controller import SessionsTab
from src.workspace import load_workspace
from tests.fakes import FakeClock, write_workspace
from tests.test_builders import NOW, ORCH, PROJECTS, SHOP, SUBAGENTS, fresh_fixture, set_mtime, ticket


def scan_now(now=NOW):
    tmp = tempfile.TemporaryDirectory()
    try:
        ws_file = write_workspace(Path(tmp.name) / "ws.json", PROJECTS)
        return SessionsTab(load_workspace(ws_file), ws_file, FakeClock(now)).scan()
    finally:
        tmp.cleanup()


def shop(*numbers):
    """The shop Effort with Tickets of these numbers (only paths and numbers are read)."""
    from src.model.effort import TrackedTicket
    tickets = tuple(TrackedTicket(ticket(n, f"t{n}"), False, False, (), "Ready", "ready-for-agent")
                    for n in numbers)
    return Effort(path=SHOP, name="shop", kind="build", title="Shop", status="", tickets=tickets,
                  counts={}, stale_spec=False)


class SubagentRowsTest(unittest.TestCase):
    def setUp(self):
        fresh_fixture()
        self.addCleanup(fresh_fixture)

    def titles(self, scan):
        return [row[0] for row in scan.rows()]

    def test_each_subagent_builder_is_a_row_under_its_orchestrator(self):
        titles = self.titles(scan_now())
        at = titles.index("Build the shop")
        under = titles[at + 1:at + 9]
        self.assertEqual(sorted(under), sorted(
            f"└ {d}" for d in ("Build ticket 11 cart", "Build ticket 12 checkout",
                               "Build ticket 13 gamemanager", "Build ticket 14 inventory",
                               "Build ticket 15 save game", "Map the shop codebase",
                               "Fix the first review's findings", "Fix the code review's findings")))
        self.assertNotIn("└ Build ticket 18 old work", titles)
        self.assertIn("Checkout page", titles)

    def test_a_subagent_row_is_keyed_by_its_own_transcript(self):
        scan = scan_now()
        row = scan.rows()[scan.index_of(SUBAGENTS / "agent-a11.jsonl")]
        self.assertEqual(row[0], "└ Build ticket 11 cart")
        self.assertEqual(scan.rows()[scan.index_of(ORCH)][0], "Build the shop")
        self.assertIsNone(scan.index_of(SUBAGENTS / "agent-a18.jsonl"))

    def test_an_orchestrator_quiet_longer_than_the_window_is_listed_while_a_subagent_works(self):
        set_mtime(ORCH, NOW - timedelta(hours=2))
        titles = self.titles(scan_now())
        self.assertIn("Build the shop", titles)
        self.assertEqual(titles[titles.index("Build the shop") + 1][:2], "└ ")

    def test_the_caption_counts_a_kept_orchestrator_apart_from_the_recent_sessions(self):
        def counted(scan):
            return int(scan.caption().split(" ", 1)[0])
        recent = scan_now()
        set_mtime(ORCH, NOW - timedelta(hours=2))
        kept = scan_now()
        self.assertEqual(counted(kept), counted(recent) - 1)
        self.assertIn("with a message in the last 30 min, and 1 waiting on its subagents",
                      kept.caption())
        self.assertNotIn("waiting", recent.caption())


class HeaderBuildersTest(unittest.TestCase):
    """An Effort's header lists its Builders whose description names no Ticket of it."""

    def setUp(self):
        fresh_fixture()

    def header(self, effort):
        return dict(scan_now().header_for(effort))

    def test_a_builder_naming_no_ticket_is_listed_and_a_finished_one_is_not(self):
        header = self.header(shop("11", "12", "13", "14", "15"))
        self.assertEqual(header[SUBAGENTS / "agent-a20.jsonl"],
                         "Fix the code review's findings · Editing cart.gd · 8s")
        self.assertIn(SUBAGENTS / "agent-a16.jsonl", header)
        self.assertNotIn(SUBAGENTS / "agent-a19.jsonl", header)

    def test_builders_on_tickets_of_the_effort_are_rows_not_header_builders(self):
        header = self.header(shop("11", "12", "13", "14", "15"))
        self.assertNotIn(SUBAGENTS / "agent-a11.jsonl", header)
        self.assertNotIn(SUBAGENTS / "agent-a12.jsonl", header)

    def test_a_builder_numbering_a_ticket_the_effort_lacks_is_a_header_builder(self):
        header = self.header(shop("12", "13", "14", "15"))
        self.assertEqual(header[SUBAGENTS / "agent-a11.jsonl"],
                         "Build ticket 11 cart · Editing shell.gd · 4s")

    def test_another_effort_has_no_header_builders(self):
        other = shop("11")
        other = Effort(**{**other.__dict__, "path": Path("G:\\other\\.scratch\\shop")})
        self.assertEqual(self.header(other), {})


if __name__ == "__main__":
    unittest.main()
