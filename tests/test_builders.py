"""Builders and their Activity, read from Claude Code's own files (ADR 0002): the sessions
seam, `scan_builders` over the builders fixture, a copy of the real layout
(`<project>/<session>.jsonl`, `<project>/<session>/subagents/agent-<id>.meta.json` and
`agent-<id>.jsonl`), anonymised. Mtimes are set relative to a fixed `NOW`."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.model.builders import match_builders, scan_builders
from src.model.sessions import scan_sessions
from src.model.sessions_tab import match_sessions
from src.model.ticket import Ticket
from tests import FIXTURES

PROJECTS = FIXTURES / "sessions" / "builders"
ORCH = PROJECTS / "G--repo" / "orch1111.jsonl"
SOLO = PROJECTS / "G--repo" / "solo2222.jsonl"
SUBAGENTS = PROJECTS / "G--repo" / "orch1111" / "subagents"
NOW = datetime(2026, 10, 21, 9, 15, tzinfo=timezone.utc)
WINDOW = timedelta(minutes=30)
SHOP = Path("G:\\repo\\.scratch\\shop")


def set_mtime(path, when):
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def ticket(number, slug, effort=SHOP):
    return Ticket(path=effort / "issues" / f"{number}-{slug}.md", number=number, title=slug,
                  status="ready-for-agent", family="Ready", type="AFK", area="", blockers=(),
                  mtime=0.0, parsed=True)


def fresh_fixture():
    """Every fixture file modified a few seconds before NOW, but agent-a18 two hours before."""
    for path in [ORCH, SOLO, *SUBAGENTS.iterdir()]:
        set_mtime(path, NOW - timedelta(seconds=4))
    for path in SUBAGENTS.glob("agent-a18.*"):
        set_mtime(path, NOW - timedelta(hours=2))


def scan(previous=()):
    sessions = scan_sessions(PROJECTS, NOW, WINDOW)
    return scan_builders(PROJECTS, NOW, WINDOW, sessions, previous)


class SubagentBuildersTest(unittest.TestCase):
    def setUp(self):
        fresh_fixture()
        self.builder_for = match_builders(scan())

    def test_metadata_naming_build_ticket_11_gives_a_builder_for_ticket_11(self):
        builder = self.builder_for(ticket("11", "cart"))
        self.assertIsNotNone(builder)
        self.assertEqual(builder.description, "Build ticket 11 cart")
        self.assertEqual(builder.transcript, SUBAGENTS / "agent-a11.jsonl")
        self.assertEqual(builder.session, ORCH)

    def test_ticket_11_of_another_effort_has_no_builder(self):
        self.assertIsNone(self.builder_for(ticket("11", "cart", Path("G:\\other\\.scratch\\shop"))))

    def test_a_subagent_naming_no_ticket_is_a_builder_on_no_ticket(self):
        builders = scan()
        loose = [b for b in builders if b.description == "Map the shop codebase"]
        self.assertEqual(len(loose), 1)
        self.assertIsNone(loose[0].number)

    def test_an_unfinished_subagent_quiet_for_longer_than_the_window_is_no_builder(self):
        self.assertIsNone(self.builder_for(ticket("18", "old-work")))

    def test_a_top_level_session_whose_first_prompt_names_the_ticket_is_its_builder(self):
        builder = self.builder_for(ticket("17", "checkout-page"))
        self.assertEqual(builder.session, SOLO)
        self.assertIsNone(builder.description)


class ActivityTest(unittest.TestCase):
    """A Builder's Activity: its latest tool call in plain words, and its age."""

    def setUp(self):
        fresh_fixture()
        self.builder_for = match_builders(scan())

    def activity(self, number, slug, now=NOW):
        builder = self.builder_for(ticket(number, slug))
        return builder.activity.text(now) if builder.activity else None

    def test_a_tail_ending_in_a_tool_call_gives_that_call_in_plain_words_with_its_age(self):
        self.assertEqual(self.activity("11", "cart"), "Editing shell.gd · 4s")

    def test_the_age_is_told_against_the_clock_it_is_given(self):
        self.assertEqual(self.activity("11", "cart", NOW + timedelta(minutes=3)),
                         "Editing shell.gd · 3m")

    def test_a_tail_of_only_bookkeeping_lines_falls_back_to_the_last_real_action(self):
        self.assertEqual(self.activity("12", "checkout"), "Running tests · 1m")

    def test_a_half_written_last_line_is_skipped(self):
        self.assertEqual(self.activity("13", "gamemanager"), "Reading 13-gamemanager.md · 10s")

    def test_a_missing_transcript_gives_no_activity(self):
        builder = self.builder_for(ticket("14", "inventory"))
        self.assertIsNotNone(builder)
        self.assertIsNone(builder.activity)

    def test_a_top_level_builder_has_activity_too(self):
        self.assertEqual(self.activity("17", "checkout-page"), "Writing checkout.gd · 2m")

    def test_the_finished_flag_marks_the_builder_finished_and_its_row_shows_no_activity(self):
        builder = self.builder_for(ticket("15", "save-game"))
        self.assertTrue(builder.finished)
        self.assertIsNone(builder.activity_text(NOW))
        self.assertFalse(self.builder_for(ticket("11", "cart")).finished)

    def test_the_last_timestamped_line_is_kept_for_stalled(self):
        builder = self.builder_for(ticket("12", "checkout"))
        self.assertEqual(builder.last_line_at, datetime(2026, 10, 21, 9, 14, 42, tzinfo=timezone.utc))


class LastMessageTest(unittest.TestCase):
    """A Builder's last message (08): its most recent assistant text, from the same tail."""

    def setUp(self):
        fresh_fixture()
        self.builder_for = match_builders(scan())

    def test_the_most_recent_assistant_text_is_the_last_message(self):
        builder = self.builder_for(ticket("12", "checkout"))
        self.assertEqual(builder.last_message, "Running the suite now.")

    def test_a_tail_with_no_assistant_text_gives_none_and_a_request_blob_is_not_one(self):
        # agent-a11's only text is an api-request-blob's, which is bookkeeping.
        self.assertIsNone(self.builder_for(ticket("11", "cart")).last_message)

    def test_a_missing_transcript_gives_no_last_message(self):
        self.assertIsNone(self.builder_for(ticket("14", "inventory")).last_message)


class TailOnlyTest(unittest.TestCase):
    """A long transcript costs only its tail: the Activity is found without reading the
    whole file."""

    def test_only_the_tail_of_a_long_transcript_is_read(self):
        import builtins
        import json
        import tempfile
        from unittest import mock

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        projects = Path(tmp.name)
        orch = projects / "G--big" / "orch.jsonl"
        subagents = orch.with_suffix("") / "subagents"
        subagents.mkdir(parents=True)
        orch.write_text(json.dumps({"type": "user", "timestamp": "2026-10-21T08:00:00Z",
                                    "message": {"role": "user",
                                                "content": "/implement-spec G:\\big\\.scratch\\e\\spec.md"}})
                        + "\n", encoding="utf-8")
        (subagents / "agent-b.meta.json").write_text(
            json.dumps({"description": "Build ticket 03 big"}), encoding="utf-8")
        filler = (json.dumps({"type": "assistant", "timestamp": "2026-10-21T08:30:00Z",
                              "message": {"role": "assistant",
                                          "content": [{"type": "text", "text": "x" * 500}]}})
                  + "\n").encode("utf-8")
        last = json.dumps({"type": "assistant", "timestamp": "2026-10-21T09:14:58Z",
                           "message": {"role": "assistant", "content": [
                               {"type": "tool_use", "name": "Read",
                                "input": {"file_path": "G:\\big\\main.gd"}}]}}) + "\n"
        transcript = subagents / "agent-b.jsonl"
        with open(transcript, "wb") as out:
            out.write(filler * (8 * 1024 * 1024 // len(filler)))
            out.write(last.encode("utf-8"))
        size = transcript.stat().st_size
        for path in (orch, transcript, subagents / "agent-b.meta.json"):
            set_mtime(path, NOW - timedelta(seconds=2))

        read = {}
        real_open = builtins.open

        def spying_open(file, *a, **k):
            handle = real_open(file, *a, **k)
            if Path(file) == transcript:
                real_read = handle.read

                def counting_read(n=-1):
                    data = real_read(n)
                    read["bytes"] = read.get("bytes", 0) + len(data)
                    return data
                handle.read = counting_read
            return handle
        with mock.patch.object(builtins, "open", spying_open):
            builders = scan_builders(projects, NOW, WINDOW)
        big = Ticket(path=Path("G:\\big\\.scratch\\e\\issues\\03-big.md"), number="03",
                     title="", status="", family="Ready", type="", area="", blockers=(),
                     mtime=0.0, parsed=True)
        builder = match_builders(builders)(big)
        self.assertEqual(builder.activity.text(NOW), "Reading main.gd · 2s")
        self.assertLessEqual(read["bytes"], 256 * 1024)
        self.assertGreater(size, 30 * read["bytes"])


POSIX_PROJECTS = FIXTURES / "sessions" / "posix"
POSIX_PROJECT = POSIX_PROJECTS / "-home-dev-code-my-repo"
POSIX_SHOP = Path("/home/dev/code/my-repo/.scratch/shop")
OTHER_SHOP = Path("/home/dev/code/other-repo/.scratch/shop")


class PosixPathsTest(unittest.TestCase):
    """Transcripts from a macOS or Linux machine, whose prompts name POSIX absolute paths
    (`/home/dev/code/my-repo/.scratch/shop/...`): their Builders and Sessions link to the
    Tickets those paths name, and not to a same-named Effort in another repo."""

    def setUp(self):
        for path in POSIX_PROJECT.rglob("*.json*"):
            set_mtime(path, NOW - timedelta(seconds=4))
        self.sessions = scan_sessions(POSIX_PROJECTS, NOW, WINDOW)
        self.builder_for = match_builders(
            scan_builders(POSIX_PROJECTS, NOW, WINDOW, self.sessions))

    def test_a_subagent_of_an_orchestrator_naming_a_posix_spec_builds_its_ticket(self):
        builder = self.builder_for(ticket("03", "basket", POSIX_SHOP))
        self.assertEqual(builder.description, "Build ticket 03 basket")
        self.assertEqual(builder.session, POSIX_PROJECT / "orch3333.jsonl")
        self.assertEqual(builder.activity.text(NOW), "Editing basket.py · 10s")

    def test_a_subagent_whose_own_prompt_names_the_posix_ticket_builds_it(self):
        builder = self.builder_for(ticket("05", "receipts", POSIX_SHOP))
        self.assertEqual(builder.description, "Build ticket 05 receipts")
        self.assertEqual(builder.session, POSIX_PROJECT / "orch4444.jsonl")

    def test_a_top_level_session_naming_a_posix_ticket_is_its_builder(self):
        builder = self.builder_for(ticket("04", "payment", POSIX_SHOP))
        self.assertEqual(builder.session, POSIX_PROJECT / "solo5555.jsonl")
        self.assertIsNone(builder.description)

    def test_the_session_column_links_a_posix_ticket_to_its_session(self):
        session = match_sessions(self.sessions)(ticket("04", "payment", POSIX_SHOP).path)
        self.assertEqual(session.title, "Payment page")

    def test_the_same_effort_in_another_repo_has_no_builder_or_session(self):
        for number, slug in (("03", "basket"), ("04", "payment"), ("05", "receipts")):
            other = ticket(number, slug, OTHER_SHOP)
            self.assertIsNone(self.builder_for(other), number)
            self.assertIsNone(match_sessions(self.sessions)(other.path), number)


if __name__ == "__main__":
    unittest.main()
