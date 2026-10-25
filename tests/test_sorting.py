"""Sorting the Ticket table: (rows, column, descending) -> ordered rows."""

import unittest
from dataclasses import replace
from pathlib import Path

from src.model.effort import TrackedTicket
from src.model.ticket import Ticket, family_of
from src.model.sorting import DEFAULT_SORT, next_sort, sort_rows


def row(number, status="open", mtime=0.0, title="", type_="", area=""):
    ticket = Ticket(path=Path(f"{number}-t.md"), number=number, title=title or f"T{number}",
                    status=status, family=family_of(status), type=type_, area=area,
                    blockers=(), mtime=mtime, parsed=True)
    return TrackedTicket(ticket=ticket, blocked=False, frontier=False, missing_blockers=(),
                         mark=ticket.family, mark_word=status)


def numbers(rows):
    return [r.ticket.number for r in rows]


class SortByStatusTest(unittest.TestCase):
    def test_groups_by_family_in_family_order(self):
        rows = [row("01", "landed"), row("02", "weird"), row("03", "wontfix"),
                row("04", "claimed"), row("05", "ready-for-agent"), row("06", "needs-info"),
                row("07", "open")]
        self.assertEqual(numbers(sort_rows(rows, "status", False)),
                         ["07", "06", "05", "04", "01", "03", "02"])

    def test_within_a_family_sorts_by_the_raw_word_then_file_order(self):
        rows = [row("01", "ready-for-human"), row("02", "open"), row("03", "needs-triage"),
                row("04", "open"), row("05", "running"), row("06", "claimed")]
        self.assertEqual(numbers(sort_rows(rows, "status", False)),
                         ["03", "02", "04", "01", "06", "05"])

    def test_second_click_reverses_the_order(self):
        rows = [row("01", "landed"), row("02", "open"), row("03", "needs-info")]
        self.assertEqual(numbers(sort_rows(rows, "status", True)), ["01", "03", "02"])

    def test_sorts_by_the_mark_with_finished_between_active_and_done(self):
        # 01 and 03 say ready-for-agent, but the Progress file marks them Landed and Finished.
        rows = [replace(row("01", "ready-for-agent"), mark="Done", mark_word="landed"),
                row("02", "landed"), row("03", "ready-for-agent"), row("04", "claimed")]
        rows[2] = replace(rows[2], mark="Finished", mark_word="finished")
        self.assertEqual(numbers(sort_rows(rows, "status", False)), ["04", "03", "01", "02"])


class SortByNumberAndUpdatedTest(unittest.TestCase):
    def test_number_restores_file_order_after_another_sort(self):
        rows = [row("01", "landed"), row("02", "open"), row("03", "needs-info")]
        by_status = sort_rows(rows, "status", False)
        self.assertEqual(numbers(sort_rows(by_status, "num", False)), ["01", "02", "03"])
        self.assertEqual(numbers(sort_rows(by_status, "num", True)), ["03", "02", "01"])

    def test_updated_descending_puts_the_newest_file_first(self):
        rows = [row("01", mtime=200.0), row("02", mtime=300.0), row("03", mtime=100.0)]
        self.assertEqual(numbers(sort_rows(rows, "updated", True)), ["02", "01", "03"])
        self.assertEqual(numbers(sort_rows(rows, "updated", False)), ["03", "01", "02"])


class SortByTextTest(unittest.TestCase):
    def test_text_columns_ignore_case_and_put_blanks_last(self):
        rows = [row("01", type_=""), row("02", type_="spike"), row("03", type_="Build")]
        self.assertEqual(numbers(sort_rows(rows, "type", False)), ["03", "02", "01"])

    def test_a_column_with_no_sort_rule_keeps_the_given_order(self):
        rows = [row("02"), row("01")]
        self.assertEqual(numbers(sort_rows(rows, "no-such-column", False)), ["02", "01"])


class SortBySessionTest(unittest.TestCase):
    """Story 18 for the Session column: Tickets with a session first, by its title."""

    TITLES = {"02": "beta run", "04": "Alpha run", "05": None}

    def session_for(self, path):
        return self.TITLES.get(path.name.split("-")[0])

    def test_tickets_with_a_session_come_first_by_session_title(self):
        rows = [row("01"), row("02"), row("03"), row("04"), row("05")]
        self.assertEqual(numbers(sort_rows(rows, "session", False, self.session_for)),
                         ["04", "02", "01", "03", "05"])

    def test_a_second_click_reverses_it(self):
        rows = [row("01"), row("02"), row("04")]
        self.assertEqual(numbers(sort_rows(rows, "session", True, self.session_for)),
                         ["01", "02", "04"])

    def test_with_no_sessions_known_the_rows_keep_file_order(self):
        rows = [row("02"), row("01")]
        self.assertEqual(numbers(sort_rows(rows, "session", False)), ["02", "01"])


class HeaderClickTest(unittest.TestCase):
    def test_default_is_ticket_number_ascending(self):
        self.assertEqual(DEFAULT_SORT, ("num", False))

    def test_new_column_sorts_ascending_and_a_second_click_reverses(self):
        self.assertEqual(next_sort(("num", False), "updated"), ("updated", False))
        self.assertEqual(next_sort(("updated", False), "updated"), ("updated", True))
        self.assertEqual(next_sort(("updated", True), "updated"), ("updated", False))
        self.assertEqual(next_sort(("updated", True), "status"), ("status", False))


if __name__ == "__main__":
    unittest.main()
