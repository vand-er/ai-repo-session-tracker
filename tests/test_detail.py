"""The detail pane's data: which kind a selected file is, the command Copy command puts on
the clipboard, and the body shown, read from disk only when asked."""

import tempfile
import unittest
from pathlib import Path

from src.model.detail import (BUILD_TICKET, MAP, SPEC, WAYFINDER_TICKET, copy_command,
                              fit_message, read_detail)
from src.model.effort import scan_effort
from tests import FIXTURES

GUIDE = FIXTURES / "field-guide-rebuild"
RETRO = FIXTURES / "retro-2026-10-19"


class CopyCommandTest(unittest.TestCase):
    def test_each_kind_gets_its_skill_and_the_absolute_path(self):
        path = Path(r"C:\work\.scratch\x\issues\03-thing.md")
        self.assertEqual(copy_command(MAP, path), r"/wayfinder C:\work\.scratch\x\issues\03-thing.md")
        self.assertEqual(copy_command(WAYFINDER_TICKET, path),
                         r"/wayfinder C:\work\.scratch\x\issues\03-thing.md")
        self.assertEqual(copy_command(SPEC, path), r"/to-tickets C:\work\.scratch\x\issues\03-thing.md")
        self.assertEqual(copy_command(BUILD_TICKET, path),
                         r"/implement C:\work\.scratch\x\issues\03-thing.md")


class MapDetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detail = read_detail(scan_effort(GUIDE), GUIDE / "map.md")

    def test_the_map_copies_wayfinder_with_its_absolute_path(self):
        self.assertEqual(self.detail.kind, MAP)
        self.assertEqual(self.detail.path, (GUIDE / "map.md").resolve())
        self.assertEqual(self.detail.command, f"/wayfinder {(GUIDE / 'map.md').resolve()}")

    def test_shows_destination_and_decisions_so_far_and_nothing_else(self):
        body = self.detail.body
        self.assertTrue(body.startswith("## Destination"))
        self.assertIn("\n## Decisions so far", body)
        # The Map's own lines on each side of the two sections.
        self.assertNotIn("## Notes", body)
        self.assertNotIn("## Not yet specified", body)
        self.assertNotIn("## Out of scope", body)
        self.assertNotIn("# The field guide rebuild", body)


class TicketAndSpecDetailTest(unittest.TestCase):
    def test_a_resolved_wayfinder_ticket_shows_its_question_and_answer(self):
        path = GUIDE / "issues" / "01-style-guide-clashes.md"
        detail = read_detail(scan_effort(GUIDE), path)
        self.assertEqual(detail.kind, WAYFINDER_TICKET)
        self.assertEqual(detail.command, f"/wayfinder {path.resolve()}")
        self.assertTrue(detail.body.startswith("## Question\n\nWhere do the style guide's"))
        self.assertIn("\n## Answer\n", detail.body)
        self.assertIn("The grill has already settled the style guide's direct clashes", detail.body)

    def test_an_open_wayfinder_ticket_shows_its_question(self):
        path = next((GUIDE / "issues").glob("22-*.md"))
        detail = read_detail(scan_effort(GUIDE), path)
        self.assertIn("## Question", detail.body)
        self.assertNotIn("## Answer", detail.body)

    def test_a_build_ticket_copies_implement(self):
        path = next((RETRO / "issues").glob("01-*.md"))
        detail = read_detail(scan_effort(RETRO), path)
        self.assertEqual(detail.kind, BUILD_TICKET)
        self.assertEqual(detail.command, f"/implement {path.resolve()}")
        self.assertTrue(detail.body.startswith("## What to build"))

    def test_the_spec_copies_to_tickets_and_shows_its_body(self):
        path = RETRO / "spec.md"
        detail = read_detail(scan_effort(RETRO), path)
        self.assertEqual(detail.kind, SPEC)
        self.assertEqual(detail.command, f"/to-tickets {path.resolve()}")
        self.assertTrue(detail.body.startswith("## "))

    def test_the_body_is_read_from_disk_when_asked_not_at_scan_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "effort"
            (folder / "issues").mkdir(parents=True)
            (folder / "map.md").write_text("# M\n\n## Destination\n\nThere.\n", encoding="utf-8")
            ticket = folder / "issues" / "01-q.md"
            ticket.write_text("# 01: Q\n\nStatus: open\n\n## Question\n\nFirst?\n", encoding="utf-8")
            effort = scan_effort(folder)
            ticket.write_text("# 01: Q\n\nStatus: resolved\n\n## Question\n\nFirst?\n\n"
                              "## Answer\n\nYes.\n", encoding="utf-8")
            self.assertEqual(read_detail(effort, ticket).body,
                             "## Question\n\nFirst?\n\n## Answer\n\nYes.")

    def test_a_file_with_no_sections_shows_all_its_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "effort"
            (folder / "issues").mkdir(parents=True)
            (folder / "spec.md").write_bytes(b"# S\r\n\r\nStatus: open\r\n\r\nJust prose.\r\n")
            detail = read_detail(scan_effort(folder), folder / "spec.md")
            self.assertEqual(detail.body, "# S\n\nStatus: open\n\nJust prose.")

    def test_an_unreadable_file_says_so_instead_of_failing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "effort"
            (folder / "issues").mkdir(parents=True)
            (folder / "spec.md").write_text("# S\n\nStatus: open\n", encoding="utf-8")
            ticket = folder / "issues" / "01-bad.md"
            ticket.write_bytes(b"# 01: Caf\xe9\n\n## What to build\n")
            effort = scan_effort(folder)
            self.assertTrue(read_detail(effort, ticket).body.startswith("Could not read this file"))
            gone = folder / "issues" / "02-gone.md"
            self.assertTrue(read_detail(effort, gone).body.startswith("Could not read this file"))


class FitMessageTest(unittest.TestCase):
    """A Builder's last message, cut to what the detail pane shows without scrolling (08)."""

    def test_a_short_message_is_kept_whole_on_one_line(self):
        self.assertEqual(fit_message("Running the suite now.", columns=40, lines=3),
                         "Running the suite now.")

    def test_a_message_is_wrapped_at_words_to_the_columns(self):
        self.assertEqual(fit_message("one two three four five six", columns=10, lines=3),
                         "one two\nthree four\nfive six")

    def test_line_breaks_and_runs_of_spaces_become_single_spaces(self):
        self.assertEqual(fit_message("Fixed it.\n\n  Next:   tests.", columns=40, lines=3),
                         "Fixed it. Next: tests.")

    def test_a_long_message_is_cut_to_the_lines_and_ends_with_an_ellipsis(self):
        self.assertEqual(fit_message("one two three four five six seven", columns=10, lines=2),
                         "one two\nthree…")

    def test_a_cut_last_line_with_no_room_for_the_ellipsis_loses_a_word(self):
        self.assertEqual(fit_message("alpha beta gamma delta", columns=10, lines=1), "alpha…")


if __name__ == "__main__":
    unittest.main()
