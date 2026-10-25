"""The Sessions tab's pure parts: matching Sessions to Ticket paths, the "3m ago" text,
and the sessions settings read from the Workspace. No GUI here."""

import json
import os
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

from src.model.sessions import Session, scan_sessions
from src.model.sessions_tab import ago, match_sessions, session_row, sessions_settings
from src.workspace import Workspace

NOW = datetime(2026, 10, 21, 9, 15, tzinfo=timezone.utc)
TICKET = Path(r"G:\my projects\board app\.scratch\wayfinder-board\issues\10-sessions-tab.md")


def session(ticket, title="t", minutes_ago=1):
    when = NOW - timedelta(minutes=minutes_ago)
    return Session(path=Path(f"{title}.jsonl"), modified=when, title=title, project="p",
                   last_message_at=when, sender="assistant", model="m",
                   mentions=() if ticket is None else (Path(ticket),))


class MatchSessionsTest(unittest.TestCase):
    def test_a_session_naming_the_ticket_path_matches_it(self):
        match = match_sessions([session(str(TICKET), "on ten")])
        self.assertEqual(match(TICKET).title, "on ten")

    def test_case_and_mixed_separators_do_not_stop_a_match_on_windows(self):
        raw = r"g:/My Projects\board app/.scratch\WAYFINDER-board/issues/10-sessions-tab.md"
        match = match_sessions([session(raw, "shouty")], windows=True)
        self.assertEqual(match(TICKET).title, "shouty")

    def test_case_matters_off_windows(self):
        match = match_sessions([session("/home/x/issues/10-a.md")], windows=False)
        self.assertIsNone(match(Path("/home/x/issues/10-A.md")))
        self.assertIsNotNone(match(Path("/home/x/issues/10-a.md")))

    def test_dot_segments_are_folded(self):
        raw = r"G:\my projects\board app\.scratch\wayfinder-board\issues\..\issues\10-sessions-tab.md"
        match = match_sessions([session(raw, "dotted")], windows=True)
        self.assertEqual(match(TICKET).title, "dotted")

    def test_other_tickets_and_sessions_without_a_ticket_do_not_match(self):
        other = TICKET.with_name("09-scan-sessions.md")
        match = match_sessions([session(str(other)), session(None)], windows=True)
        self.assertIsNone(match(TICKET))

    def test_the_newest_session_wins_when_two_name_the_same_ticket(self):
        older, newer = session(str(TICKET), "older", 9), session(str(TICKET), "newer", 2)
        match = match_sessions([older, newer], windows=True)
        self.assertEqual(match(TICKET).title, "newer")


class TicketInFirstPromptTest(unittest.TestCase):
    """Story 33: a Ticket is matched when its path appears anywhere in a session's first
    prompt. Scanned from a real transcript file, then looked up as the Board does."""

    def match(self, prompt, path=TICKET):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "G--case"
            folder.mkdir()
            transcript = folder / "ffff.jsonl"
            line = {"type": "user", "timestamp": "2026-10-21T09:00:00Z",
                    "message": {"role": "user", "content": prompt}}
            transcript.write_text(json.dumps(line) + "\n", encoding="utf-8")
            stamp = NOW.timestamp()
            os.utime(transcript, (stamp, stamp))
            sessions = scan_sessions(tmp, NOW, timedelta(minutes=30))
        return match_sessions(sessions, windows=True)(path)

    def test_a_ticket_named_after_a_map_path_matches(self):
        prompt = (r"/wayfinder G:\my projects\board app\.scratch\wayfinder-board\map.md"
                  f" then build {TICKET}")
        self.assertIsNotNone(self.match(prompt))

    def test_a_path_ending_a_sentence_matches(self):
        self.assertIsNotNone(self.match(f"Please build {TICKET}. Thanks"))
        self.assertIsNotNone(self.match(f"Please build {TICKET}."))

    def test_a_relative_scratch_path_matches_the_ticket_it_ends(self):
        self.assertIsNotNone(self.match("/implement .scratch/wayfinder-board/issues/10-sessions-tab.md"))
        self.assertIsNotNone(self.match(r"see .scratch\Wayfinder-Board\issues\10-sessions-tab.md."))

    def test_a_relative_path_into_another_effort_does_not_match(self):
        self.assertIsNone(self.match("/implement .scratch/other-effort/issues/10-sessions-tab.md"))


class AgoTest(unittest.TestCase):
    def test_whole_minutes_read_as_minutes_ago(self):
        self.assertEqual(ago(NOW - timedelta(minutes=3, seconds=40), NOW), "3m ago")

    def test_under_a_minute_reads_in_seconds(self):
        self.assertEqual(ago(NOW - timedelta(seconds=12), NOW), "12s ago")

    def test_an_hour_or_more_reads_in_hours_then_days(self):
        self.assertEqual(ago(NOW - timedelta(minutes=125), NOW), "2h ago")
        self.assertEqual(ago(NOW - timedelta(hours=50), NOW), "2d ago")

    def test_a_time_just_ahead_of_now_reads_as_zero_seconds(self):
        self.assertEqual(ago(NOW + timedelta(seconds=2), NOW), "0s ago")

    def test_no_time_reads_unknown(self):
        self.assertEqual(ago(None, NOW), "Unknown")


class SessionRowTest(unittest.TestCase):
    def test_a_row_reads_title_project_ago_sender_model_and_the_tickets_effort_and_file(self):
        row = session_row(session(str(TICKET), "on ten", minutes_ago=3), NOW)
        self.assertEqual(row, ("on ten", "p", "3m ago", "assistant", "m",
                               "wayfinder-board/10-sessions-tab.md"))

    def test_a_map_reads_with_its_effort(self):
        row = session_row(session(r"G:\r\.scratch\guide\map.md"), NOW)
        self.assertEqual(row[5], "guide/map.md")

    def test_missing_fields_read_unknown_and_no_ticket_reads_a_dash(self):
        s = Session(path=Path("x.jsonl"), modified=NOW, title="x", project=None,
                    last_message_at=None, sender=None, model=None)
        self.assertEqual(session_row(s, NOW), ("x", "Unknown", "Unknown", "Unknown", "Unknown", "—"))


class SessionsSettingsTest(unittest.TestCase):
    def test_defaults_are_thirty_minutes_and_the_claude_projects_folder(self):
        projects_dir, window = sessions_settings(Workspace())
        self.assertEqual(window, timedelta(minutes=30))
        self.assertEqual(projects_dir, Path.home() / ".claude" / "projects")

    def test_the_workspace_file_sets_the_window_and_the_folder(self):
        ws = Workspace(settings={"sessions_window_minutes": 1, "claude_projects_dir": r"D:\elsewhere"})
        projects_dir, window = sessions_settings(ws)
        self.assertEqual(window, timedelta(minutes=1))
        self.assertEqual(projects_dir, Path(r"D:\elsewhere"))

    def test_a_folder_under_home_may_start_with_a_tilde(self):
        projects_dir, _ = sessions_settings(Workspace(settings={"claude_projects_dir": "~/cc/projects"}))
        self.assertEqual(projects_dir, Path.home() / "cc" / "projects")

    def test_a_bad_window_falls_back_to_thirty_minutes(self):
        for bad in (0, -5, "ten", True, None):
            _, window = sessions_settings(Workspace(settings={"sessions_window_minutes": bad}))
            self.assertEqual(window, timedelta(minutes=30), bad)

    def test_a_bad_folder_falls_back_to_the_default(self):
        for bad in ("", 7, None):
            projects_dir, _ = sessions_settings(Workspace(settings={"claude_projects_dir": bad}))
            self.assertEqual(projects_dir, Path.home() / ".claude" / "projects", bad)


class ClaudeConfigDirTest(unittest.TestCase):
    """`CLAUDE_CONFIG_DIR` moves Claude Code's own folder, and its projects folder with it,
    on every system. An explicit Workspace setting still wins."""

    def setUp(self):
        self.config = Path(tempfile.gettempdir()) / "elsewhere" / "claude-config"
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.config)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_variable_moves_the_projects_folder(self):
        projects_dir, _ = sessions_settings(Workspace())
        self.assertEqual(projects_dir, self.config / "projects")

    def test_an_explicit_workspace_folder_wins_over_the_variable(self):
        ws = Workspace(settings={"claude_projects_dir": r"D:\elsewhere"})
        projects_dir, _ = sessions_settings(ws)
        self.assertEqual(projects_dir, Path(r"D:\elsewhere"))

    def test_an_empty_variable_is_no_variable(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": ""}):
            projects_dir, _ = sessions_settings(Workspace())
        self.assertEqual(projects_dir, Path.home() / ".claude" / "projects")


if __name__ == "__main__":
    unittest.main()
