import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import src.model.ticket as ticket_module
from src.model.ticket import parse_ticket
from tests import FIXTURES

SHAPES = FIXTURES / "ticket-shapes"


class PlainHeaderTest(unittest.TestCase):
    def test_plain_status_under_title(self):
        ticket = parse_ticket(SHAPES / "04-plain-status.md")
        self.assertEqual(ticket.number, "04")
        self.assertEqual(ticket.title, "Plain status under the title")
        self.assertEqual(ticket.status, "open")
        self.assertEqual(ticket.family, "Needs me")
        self.assertEqual(ticket.type, "grilling")
        self.assertEqual(ticket.area, "3, the shell")
        self.assertTrue(ticket.parsed)

    def test_bold_status_mid_body(self):
        ticket = parse_ticket(SHAPES / "05-bold-status-mid-body.md")
        self.assertEqual(ticket.status, "ready-for-agent")
        self.assertEqual(ticket.family, "Ready")
        self.assertEqual(ticket.blockers, ("01",))
        self.assertEqual(ticket.type, "")
        self.assertTrue(ticket.parsed)

    def test_status_with_trailing_prose_keeps_first_word(self):
        ticket = parse_ticket(SHAPES / "06-status-trailing-prose.md")
        self.assertEqual(ticket.status, "wontfix")
        self.assertEqual(ticket.family, "Dropped")

    def test_the_header_ends_at_a_level_two_heading_as_the_detail_pane_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "09-sub.md"
            path.write_text("# Sub\n\n### Note\n\nStatus: open\n\n## What\n\nStatus: landed\n",
                            encoding="utf-8")
            self.assertEqual(parse_ticket(path).status, "open")


class FlaggedTicketTest(unittest.TestCase):
    def test_missing_status_is_flagged_unknown(self):
        ticket = parse_ticket(SHAPES / "07-missing-status.md")
        self.assertEqual(ticket.status, "")
        self.assertEqual(ticket.family, "Unknown")
        self.assertFalse(ticket.parsed)
        self.assertEqual(ticket.number, "07")
        self.assertEqual(ticket.blockers, ("02",))

    def test_not_utf8_still_returns_a_flagged_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "08-latin-1.md"
            path.write_bytes(b"# 08: Caf\xe9\r\n\r\nStatus: open\r\n")
            ticket = parse_ticket(path)
        self.assertEqual(ticket.number, "08")
        self.assertEqual(ticket.status, "")
        self.assertEqual(ticket.family, "Unknown")
        self.assertFalse(ticket.parsed)

    def test_missing_file_still_returns_a_flagged_ticket(self):
        ticket = parse_ticket(SHAPES / "99-not-there.md")
        self.assertEqual(ticket.number, "99")
        self.assertEqual(ticket.family, "Unknown")
        self.assertFalse(ticket.parsed)


class FixtureEffortsTest(unittest.TestCase):
    def test_every_fixture_ticket_has_a_status(self):
        paths = sorted(FIXTURES.glob("*/issues/*.md"))
        self.assertEqual(len(paths), 63)
        for path in paths:
            with self.subTest(path.name):
                ticket = parse_ticket(path)
                self.assertTrue(ticket.parsed)
                self.assertNotEqual(ticket.status, "")
                self.assertNotEqual(ticket.family, "Unknown")

    def test_crlf_fixture_reads_like_lf(self):
        ticket = parse_ticket(FIXTURES / "retro-2026-10-19/issues/07-building-a-ticket-on-its-own-page.md")
        self.assertEqual(ticket.title, "Building a ticket, on its own page")
        self.assertEqual(ticket.status, "resolved")
        self.assertEqual(ticket.blockers, ("03", "05"))

    def test_two_parses_of_one_file_are_equal(self):
        path = SHAPES / "04-plain-status.md"
        self.assertEqual(parse_ticket(path), parse_ticket(path))


class FamilyTableTest(unittest.TestCase):
    def test_unlisted_status_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20-parked.md"
            path.write_text("# 20: Parked\n\nStatus: parked\n", encoding="utf-8")
            self.assertEqual(parse_ticket(path).family, "Unknown")
            with mock.patch.dict(ticket_module.STATUS_FAMILY, {"parked": "Waiting"}):
                self.assertEqual(parse_ticket(path).family, "Waiting")

    def test_table_maps_every_documented_status(self):
        self.assertEqual(ticket_module.STATUS_FAMILY, {
            "open": "Needs me", "needs-triage": "Needs me", "ready-for-human": "Needs me",
            "needs-info": "Waiting",
            "ready-for-agent": "Ready",
            "claimed": "Active", "running": "Active",
            "resolved": "Done", "landed": "Done",
            "wontfix": "Dropped",
        })


class NoGuiTest(unittest.TestCase):
    def test_module_imports_nothing_from_the_gui(self):
        code = ("import sys, src.model.ticket; "
                "sys.exit(any(m.split('.')[0] in ('tkinter', 'customtkinter') for m in sys.modules))")
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run([sys.executable, "-c", code], cwd=root)
        self.assertEqual(result.returncode, 0)


class BlockedByTest(unittest.TestCase):
    def blockers(self, name):
        return parse_ticket(SHAPES / name).blockers

    def test_plain_list(self):
        self.assertEqual(self.blockers("04-plain-status.md"), ("07", "08", "09"))

    def test_none(self):
        self.assertEqual(self.blockers("10-blocked-none.md"), ())

    def test_none_can_start_immediately(self):
        self.assertEqual(self.blockers("11-blocked-none-can-start.md"), ())

    def test_numbers_with_reasons(self):
        self.assertEqual(self.blockers("12-blocked-reasons.md"), ("03", "05"))

    def test_reason_then_prose(self):
        self.assertEqual(self.blockers("13-blocked-reason-so.md"), ("08",))

    def test_none_then_sentence(self):
        self.assertEqual(self.blockers("14-blocked-none-dot.md"), ())

    def test_missing_line(self):
        self.assertEqual(self.blockers("15-missing-blocked-by.md"), ())


if __name__ == "__main__":
    unittest.main()
