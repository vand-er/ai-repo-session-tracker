"""The Ticket check tool (tools/ticket_check.py), driven through its command line on
fixture Efforts. Close mode is checked by reading the files it wrote."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import FIXTURES

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ticket_check.py"


def run(*args):
    result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], cwd=REPO,
                            capture_output=True)
    return result.returncode, result.stdout.decode("utf-8"), result.stderr.decode("utf-8")


class TempEffort(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ticket-check-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def effort(self, tickets, progress=None, name="effort"):
        """An Effort folder holding `tickets` ({file name: text}) and a Progress file."""
        folder = self.tmp / name
        (folder / "issues").mkdir(parents=True)
        for file_name, text in tickets.items():
            (folder / "issues" / file_name).write_bytes(text.encode("utf-8"))
        if progress is not None:
            (folder / "progress.md").write_bytes(progress.encode("utf-8"))
        return folder


class ReportTest(TempEffort):
    def test_ticket_shapes_list_every_ticket_and_pass(self):
        folder = self.tmp / "shapes"
        shutil.copytree(FIXTURES / "ticket-shapes", folder / "issues")
        code, out, err = run(folder)
        self.assertEqual(code, 0, out + err)
        numbers = [line.split()[0] for line in out.splitlines() if line[:2].isdigit()]
        self.assertEqual(numbers, ["04", "05", "06", "07", "10", "11", "12", "13", "14", "15"])


class DriftTest(TempEffort):
    def test_landed_line_on_an_unresolved_ticket_fails_naming_it(self):
        code, out, err = run(FIXTURES / "ticket-check-drift")
        self.assertEqual(code, 1, out + err)
        problems = [line for line in out.splitlines() if line.startswith("FAIL")]
        self.assertEqual(len(problems), 1, out)
        self.assertIn("02", problems[0])
        self.assertIn("landed 2222222", problems[0])
        self.assertIn("ready-for-agent", problems[0])

    def test_progress_marks_lists_every_ticket_and_its_planted_drift(self):
        code, out, _ = run(FIXTURES / "progress-marks")
        numbers = [line.split()[0] for line in out.splitlines() if line[:2].isdigit()]
        self.assertEqual(numbers, [f"{n:02}" for n in range(1, 11)])
        self.assertIn("01  ready-for-agent  progress: landed 1111111", out)
        failed = sorted(line.split()[1] for line in out.splitlines() if line.startswith("FAIL"))
        self.assertEqual(failed, ["01", "04", "07"])   # landed lines the Status never caught up with
        self.assertEqual(code, 1)


class BlockedByTest(TempEffort):
    def test_a_range_fails_naming_the_ticket_and_the_value(self):
        code, out, err = run(FIXTURES / "ticket-check-range")
        self.assertEqual(code, 1, out + err)
        problems = [line for line in out.splitlines() if line.startswith("FAIL")]
        self.assertEqual(len(problems), 1, out)
        self.assertIn("13", problems[0])
        self.assertIn("01–12", problems[0])

    def test_none_reasons_and_a_waits_on_line_pass(self):
        folder = self.effort({
            "01-none.md": "# 01: None\n\n**Blocked by:** None\n\n**Status:** ready-for-agent\n",
            "03-a.md": "# 03: A\n\nBlocked by: none\nStatus: open\n",
            "05-b.md": "# 05: B\n\nBlocked by: none\nStatus: open\n",
            "07-reasons.md": ("# 07: Reasons\n\n**Blocked by:** 03 (why), 05 (why)\n\n"
                              "**Waits on:** open-source-release 04, 06\n\n"
                              "**Status:** ready-for-agent\n"),
        })
        code, out, err = run(folder)
        self.assertEqual(code, 0, out + err)
        self.assertIn("07  ready-for-agent  progress: -  blocked by: 03, 05", out)
        self.assertIn("waits on: open-source-release 04, 06", out)

    def test_numbers_then_a_range_fail(self):
        folder = self.effort({"09-x.md": "# 09: X\n\nBlocked by: 01, 02-05\nStatus: open\n"})
        code, out, _ = run(folder)
        self.assertEqual(code, 1, out)
        self.assertIn("01, 02-05", out)

    def test_prose_instead_of_numbers_fails(self):
        folder = self.effort({"09-x.md": "# 09: X\n\nBlocked by: the shell ticket\nStatus: open\n"})
        code, out, _ = run(folder)
        self.assertEqual(code, 1, out)
        self.assertIn("the shell ticket", out)


class CloseTest(TempEffort):
    def test_close_on_a_crlf_copy_of_the_drift_fixture(self):
        folder = self.tmp / "drift"
        shutil.copytree(FIXTURES / "ticket-check-drift", folder)
        ticket = folder / "issues" / "02-never-closed.md"
        progress = folder / "progress.md"
        for path in (ticket, progress):   # CRLF on disk, whatever git checked out
            text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
            path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

        code, out, err = run(folder, "--close", "02", "abc1234",
                             "2026-10-24: landed as abc1234 → main")
        self.assertEqual(code, 0, out + err)

        raw = ticket.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))   # every line still ends CRLF
        self.assertEqual(raw.decode("utf-8").split("\r\n"), [
            "# 02: Landed, but its Status line was never updated",
            "",
            "**Blocked by:** 01 (landed and closed)",
            "",
            "**Status:** resolved",
            "",
            "- [x] Not ticked",
            "",
            "## Comments",
            "",
            "- 2026-10-24: landed as abc1234 → main",
            "",
        ])
        raw = progress.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn(b"- 01-closed: landed 1111111\r\n- 02-never-closed: landed abc1234\r\n", raw)
        self.assertNotIn(b"2222222", raw)
        self.assertEqual(run(folder)[0], 0)

    def test_close_appends_under_existing_comments_and_adds_a_missing_progress_line(self):
        folder = self.effort({
            "05-x.md": ("# 05: X\n\n**What to build:** prose.\n\n**Blocked by:** None\n\n"
                        "**Status:** ready-for-agent\n\n- [ ] One\n- [X] Two\n  - [ ] Nested\n\n"
                        "## Comments\n\n- an earlier comment\n\n## Later\n\nText.\n"),
            "06-y.md": "# 06: Y\n\nStatus: open\n",
        }, progress="# Progress\n\n## Tickets\n\n- 06-y: waiting\n\n## Notes\n\n- 05: a note\n")
        code, out, err = run(folder, "--close", "05", "def5678", "Closed.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((folder / "issues" / "05-x.md").read_text(encoding="utf-8"), (
            "# 05: X\n\n**What to build:** prose.\n\n**Blocked by:** None\n\n"
            "**Status:** resolved\n\n- [x] One\n- [X] Two\n  - [x] Nested\n\n"
            "## Comments\n\n- an earlier comment\n- Closed.\n\n## Later\n\nText.\n"))
        self.assertEqual((folder / "progress.md").read_text(encoding="utf-8"), (
            "# Progress\n\n## Tickets\n\n- 06-y: waiting\n- 05-x: landed def5678\n\n"
            "## Notes\n\n- 05: a note\n"))

    def test_close_on_a_missing_ticket_fails_and_writes_nothing(self):
        folder = self.effort({"06-y.md": "# 06: Y\n\nStatus: open\n"}, progress="- 06-y: waiting\n")
        code, out, err = run(folder, "--close", "09", "def5678", "Closed.")
        self.assertNotEqual(code, 0)
        self.assertIn("09", out + err)
        self.assertEqual((folder / "progress.md").read_text(encoding="utf-8"), "- 06-y: waiting\n")


if __name__ == "__main__":
    unittest.main()
