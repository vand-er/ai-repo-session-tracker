"""A Ticket's mark: the furthest along of its Status line's Family and its line in the
Effort's Progress file (fast-live-board 05). Driven through `scan_effort` on fixture
folders; expected values come from the fixture's own lines, written down by hand."""

import shutil
import tempfile
import unittest
from pathlib import Path

from src.model.effort import scan_effort
from tests import FIXTURES

MARKS = FIXTURES / "progress-marks"


def by_number(effort):
    return {t.ticket.number: t for t in effort.tickets}


class ProgressMarksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.effort = scan_effort(MARKS)
        cls.rows = by_number(cls.effort)

    def mark(self, number):
        row = self.rows[number]
        return row.mark, row.mark_word

    def test_a_stale_status_line_under_a_landed_line_is_landed(self):
        self.assertEqual(self.mark("01"), ("Done", "landed"))

    def test_a_finished_line_gives_finished(self):
        self.assertEqual(self.mark("02"), ("Finished", "finished"))

    def test_a_running_line_gives_active(self):
        self.assertEqual(self.mark("03"), ("Active", "running"))

    def test_a_dropped_status_line_under_a_landed_line_stays_dropped(self):
        self.assertEqual(self.mark("04"), ("Dropped", "wontfix"))

    def test_a_status_line_further_along_than_the_progress_line_wins(self):
        self.assertEqual(self.mark("05"), ("Done", "resolved"))

    def test_a_finished_line_is_further_along_than_a_claimed_status(self):
        self.assertEqual(self.mark("10"), ("Finished", "finished"))

    def test_a_line_naming_only_the_number_still_counts(self):
        self.assertEqual(self.mark("07"), ("Done", "landed"))

    def test_a_note_naming_a_number_and_a_waiting_line_change_nothing(self):
        self.assertEqual(self.mark("08"), ("Ready", "ready-for-agent"))
        self.assertEqual(self.mark("06"), ("Ready", "ready-for-agent"))

    def test_finished_is_counted_apart_and_the_done_count_counts_landed(self):
        self.assertEqual(self.effort.counts, {
            "Needs me": 0, "Waiting": 0, "Ready": 3, "Active": 1, "Finished": 2,
            "Done": 3, "Dropped": 1, "Unknown": 0,
        })

    def test_the_status_line_itself_is_left_as_written(self):
        self.assertEqual(self.rows["01"].ticket.status, "ready-for-agent")
        self.assertEqual(self.rows["01"].ticket.family, "Ready")

    def test_a_ticket_waiting_on_a_finished_one_stays_blocked(self):
        self.assertTrue(self.rows["06"].blocked)
        self.assertFalse(self.rows["06"].frontier)

    def test_a_ticket_waiting_on_a_landed_one_is_on_the_frontier(self):
        self.assertFalse(self.rows["09"].blocked)
        self.assertTrue(self.rows["09"].frontier)

    def test_neither_finished_nor_landed_is_on_the_frontier(self):
        self.assertFalse(self.rows["02"].frontier)
        self.assertFalse(self.rows["01"].frontier)


class ProgressFileChangesTest(unittest.TestCase):
    """A copy of the fixture, edited the way an orchestrator would."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "marks"
        shutil.copytree(MARKS, self.folder)
        self.progress = self.folder / "progress.md"

    def status_marks(self, effort):
        return {n: (t.mark, t.mark_word) for n, t in by_number(effort).items()}

    def test_the_blocked_ticket_is_unblocked_when_its_blocker_lands(self):
        text = self.progress.read_text(encoding="utf-8")
        self.progress.write_text(text.replace("- 02-finished: finished .worktrees/02",
                                              "- 02-finished: landed 2222222"), encoding="utf-8")
        rows = by_number(scan_effort(self.folder))
        self.assertEqual((rows["02"].mark, rows["02"].mark_word), ("Done", "landed"))
        self.assertFalse(rows["06"].blocked)
        self.assertTrue(rows["06"].frontier)

    def without_progress(self):
        """Each Ticket's mark from its Status line alone, written down by hand."""
        return {"01": ("Ready", "ready-for-agent"), "02": ("Ready", "ready-for-agent"),
                "03": ("Ready", "ready-for-agent"), "04": ("Dropped", "wontfix"),
                "05": ("Done", "resolved"), "06": ("Ready", "ready-for-agent"),
                "07": ("Ready", "ready-for-agent"), "08": ("Ready", "ready-for-agent"),
                "09": ("Ready", "ready-for-agent"), "10": ("Active", "claimed")}

    def test_a_missing_progress_file_changes_nothing(self):
        self.progress.unlink()
        effort = scan_effort(self.folder)
        self.assertEqual(self.status_marks(effort), self.without_progress())
        self.assertTrue(by_number(effort)["09"].blocked)   # 01 is only Ready now

    def test_a_progress_file_that_is_not_text_changes_nothing(self):
        self.progress.write_bytes(b"- 01-stale-landed: landed \xff\xfe\x00 1111111\n")
        self.assertEqual(self.status_marks(scan_effort(self.folder)), self.without_progress())

    def test_a_progress_file_of_malformed_lines_changes_nothing(self):
        self.progress.write_text("01-stale-landed landed\n-01: landed\n- 02 finished\n"
                                 "- 03-running: 1234567 running\n- : landed\n",
                                 encoding="utf-8")
        self.assertEqual(self.status_marks(scan_effort(self.folder)), self.without_progress())

    def test_a_progress_folder_in_place_of_the_file_changes_nothing(self):
        self.progress.unlink()
        self.progress.mkdir()
        self.assertEqual(self.status_marks(scan_effort(self.folder)), self.without_progress())


# A shape met in a real repo, rewritten with invented names: every Status line still
# says ready-for-agent; the Progress file says each Ticket landed, out of order, among
# task-graph lines, run notes and notes for later builders that also start `- NN`.
SHELL_AREA = {   # file stem -> Blocked by
    "01-flags-become-plain-code": "None (can start immediately)",
    "02-flag-machinery-goes": "01 (The flags become plain code)",
    "03-every-asset-path-resolves": "None (can start immediately)",
    "04-move-shell-and-debug": "02 (The flag machinery goes), 03 (Every `assets/` path resolves)",
    "05-move-entries-and-search": "02 (The flag machinery goes), 03 (Every path resolves)",
    "06-move-map-menus-sounds": "02 (The flag machinery goes), 03 (Every path resolves)",
    "07-tests-mirror-folders": "04, 05, 06 (the three moves)",
    "08-renames": "07 (The tests mirror the folders)",
    "09-trip-state-records": "08 (The renames)",
    "10-controller-owns-the-trip": "09 (TripState, TripLog and the map as records)",
    "11-controller-steps-searches": "10 (The controller owns the trip)",
    "12-open-screen-and-rebuild": "11 (The controller steps every search)",
    "13-the-overlays": "12 (`open_screen` and free-and-rebuild)",
    "14-diagnostics-beside-every-shot": "08 (The renames)",
    "15-shot-log-and-sampler": "14 (`Diagnostics.report()` beside every shot)",
}
SHELL_AREA_PROGRESS = """# Progress: rebuild-03-shell

- Integration branch: `integration/rebuild-03-shell`, cut from `main` at `07fa9ea`.
- Builders: SDK subagents, each in `.claude/worktrees/<NN-slug>`.

## Task graph

- 01, 03: no blockers
- 02 ← 01
- 04, 05, 06 ← 02, 03
- 09 ← 08; 14 ← 08 (09 and 14 run beside each other)

## Tickets

- 01-flags-become-plain-code: landed 0c6f168
- 02-flag-machinery-goes: landed df9c26c
- 03-every-asset-path-resolves: landed 8114834
- 04-move-shell-and-debug: landed cac6561
- 05-move-entries-and-search: landed 7dac4f2
- 06-move-map-menus-sounds: landed 7822556
- 07-tests-mirror-folders: landed 756c1f2
- 08-renames: landed 79dc670
- 09-trip-state-records: landed 57b705a
- 10-controller-owns-the-trip: landed 0a22f26
- 11-controller-steps-searches: landed f53b639
- 12-open-screen-and-rebuild: landed 96468f0
- 13-the-overlays: landed 9466f7a
- ALL TICKETS LANDED at 9466f7a. `/code-review` running on `07fa9ea...integration/rebuild-03-shell`
  (Standards and Spec agents) done.
- 16-review-fixes: landed ca606d3.
- DONE 2026-10-21: `main` fast-forwarded to ca606d3 in the live tree (every ticket closed).
- 14-diagnostics-beside-every-shot: landed 6566daf
- 15-shot-log-and-sampler: landed fe5df93 (no before of its own; 01-04 diffed clean against
  reports/14-after.txt at its base 6566daf)

## Notes for later builders

- 04, 05, 06, 07: read `reports/03.md`, `## For ticket 04`.
- 07: `reports/05.md`, `## For ticket 07` (the search files that left `search/`).
- 12: `reports/15.md`: the shot log reads `last swap <x> s` from Diagnostics' Shell section.
"""


class ShellAreaShapeTest(unittest.TestCase):
    def test_every_ticket_shows_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "rebuild-03-shell"
            (folder / "issues").mkdir(parents=True)
            (folder / "spec.md").write_text("# Area 3: the shell\n\nStatus: ready-for-agent\n",
                                            encoding="utf-8")
            (folder / "progress.md").write_text(SHELL_AREA_PROGRESS, encoding="utf-8")
            for stem, blocked_by in SHELL_AREA.items():
                (folder / "issues" / f"{stem}.md").write_text(
                    f"# {stem[:2]}: {stem[3:]}\n\n**Blocked by:** {blocked_by}\n"
                    "**Status:** ready-for-agent\n\n## What to build\n\nWork.\n",
                    encoding="utf-8")
            effort = scan_effort(folder)
        self.assertEqual(len(effort.tickets), 15)
        self.assertEqual(effort.counts["Done"], 15)
        self.assertEqual({t.mark_word for t in effort.tickets}, {"landed"})
        self.assertEqual([t for t in effort.tickets if t.blocked or t.frontier], [])
        self.assertEqual({t.ticket.status for t in effort.tickets}, {"ready-for-agent"})
        self.assertTrue(effort.stale_spec)   # every Ticket Done, the Spec still not


class BuilderFinishedTest(unittest.TestCase):
    """A Builder's metadata gaining its finished flag (07) is one more record of how far
    along a Ticket is, folded in under the same furthest-along rule."""

    def scan(self, finished=True, numbers=("03", "04", "05", "08")):
        from src.model.builders import Builder
        builder = Builder(transcript=Path("agent-x.jsonl"), session=Path("orch.jsonl"),
                          description="Build ticket", number=None, efforts=(), mentions=(),
                          finished=finished)
        return by_number(scan_effort(MARKS, builder_for=lambda t: builder
                                     if t.number in numbers else None))

    def mark(self, rows, number):
        return rows[number].mark, rows[number].mark_word

    def test_a_finished_builder_on_a_ready_ticket_gives_finished(self):
        self.assertEqual(self.mark(self.scan(), "08"), ("Finished", "finished"))

    def test_a_finished_builder_is_further_along_than_a_running_line(self):
        self.assertEqual(self.mark(self.scan(), "03"), ("Finished", "finished"))

    def test_a_status_line_further_along_and_a_dropped_one_still_win(self):
        rows = self.scan()
        self.assertEqual(self.mark(rows, "05"), ("Done", "resolved"))
        self.assertEqual(self.mark(rows, "04"), ("Dropped", "wontfix"))

    def test_a_builder_still_working_changes_no_mark(self):
        rows = self.scan(finished=False)
        self.assertEqual(self.mark(rows, "08"), ("Ready", "ready-for-agent"))
        self.assertEqual(self.mark(rows, "03"), ("Active", "running"))


if __name__ == "__main__":
    unittest.main()
