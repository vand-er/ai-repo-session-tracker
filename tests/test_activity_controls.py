"""A Builder's Activity on its Ticket's row, driven through BoardController with the
stand-in window, a same-thread runner and a stand-in clock: what reaches the Board view as
the Builder works, and what is cleared when it stops. A click on an Activity, or on a
header Builder, is the Board view's `on_activity` / `on_builder` callback the controller set."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unittest import mock

from src.controller import BoardController
from src.model.detail import read_detail
from src.workspace import load_workspace
from tests.fakes import FakeClock, FakeWindow, write_workspace

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retro-2026-10-19"


def stamp(when):
    return when.astimezone().isoformat()


class ActivityControlsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Resolved, as a tab's folder is: a temp folder can hold an 8.3 short name or a
        # symlink (/var on macOS), and the transcripts must name the Tickets' own paths.
        root = Path(tmp.name).resolve()
        repo = root / "repo"
        effort = repo / ".scratch" / "retro"
        shutil.copytree(FIXTURE, effort)
        (effort / "progress.md").unlink()   # Ticket 02 is still being built
        self.ticket = next((effort / "issues").glob("02-*.md"))
        text = self.ticket.read_text(encoding="utf-8")
        self.ticket.write_text(text.replace("Status: resolved", "Status: claimed"),
                               encoding="utf-8")
        self.clock = FakeClock(datetime.now().astimezone())
        projects = root / "projects"
        self.orch = projects / "G--repo" / "orch.jsonl"
        self.subagents = self.orch.with_suffix("") / "subagents"
        self.subagents.mkdir(parents=True)
        self.write_lines(self.orch, [{
            "type": "user", "timestamp": stamp(self.clock.time - timedelta(minutes=20)),
            "message": {"role": "user", "content": f"/implement-spec {effort / 'spec.md'}"}}])
        self.meta = self.subagents / "agent-b02.meta.json"
        self.transcript = self.subagents / "agent-b02.jsonl"
        self.write_meta(finished=False)
        self.write_lines(self.transcript, [
            {"type": "user", "timestamp": stamp(self.clock.time - timedelta(minutes=10)),
             "message": {"role": "user", "content": f"Build {self.ticket}"}},
            self.tool_call("Edit", {"file_path": "G:\\repo\\shell.gd"}, seconds_ago=4)])
        self.window = FakeWindow()
        ws_file = write_workspace(root / "ws.json", projects)
        self.controller = BoardController(load_workspace(ws_file), ws_file, self.window,
                                          clock=self.clock)
        self.controller.start()
        self.controller.new_tab(repo)
        self.view = self.controller.front_tab().view

    def write_lines(self, path, records):
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        self.touch(path)

    def touch(self, path):
        when = self.clock.time.timestamp() - 1
        os.utime(path, (when, when))

    def write_meta(self, finished):
        meta = {"agentType": "general-purpose", "description": "Build ticket 02 warnings",
                "requestShape": "background"}
        if finished:
            meta["finished"] = True
        self.meta.write_text(json.dumps(meta), encoding="utf-8")
        self.touch(self.meta)

    def tool_call(self, name, args, seconds_ago):
        return {"type": "assistant",
                "timestamp": stamp(self.clock.time - timedelta(seconds=seconds_ago)),
                "message": {"role": "assistant",
                            "content": [{"type": "tool_use", "name": name, "input": args}]}}

    def append(self, record):
        with open(self.transcript, "a", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")
        self.touch(self.transcript)

    def told(self, name):
        return [args for call, args in self.view.told if call == name]

    def test_the_builders_activity_reaches_its_row(self):
        self.assertEqual(self.view.activity, {self.ticket: "Editing shell.gd · 4s"})

    def test_a_new_action_reaches_the_row_on_the_next_poll(self):
        self.clock.time += timedelta(seconds=10)
        self.append(self.tool_call("Bash", {"command": "python -m unittest discover"}, 1))
        self.window.tick()
        self.assertEqual(self.view.activity, {self.ticket: "Running tests · 1s"})

    def test_a_timestamp_with_no_offset_is_read_as_utc(self):
        """Story 31: Claude Code writes UTC; a line without the offset must not break the
        poll (an aware now less a naive time raises)."""
        when = (self.clock.time - timedelta(seconds=7)).astimezone(timezone.utc)
        record = self.tool_call("Read", {"file_path": "G:\\repo\\cart.gd"}, 0)
        record["timestamp"] = when.replace(tzinfo=None).isoformat()
        self.append(record)
        self.window.tick()
        self.assertEqual(self.view.activity, {self.ticket: "Reading cart.gd · 7s"})
        self.assertEqual(self.view.stalled, set())

    def test_the_age_moves_with_the_clock(self):
        self.clock.time += timedelta(minutes=2)
        self.window.tick()
        self.assertEqual(self.view.activity, {self.ticket: "Editing shell.gd · 2m"})

    def test_a_poll_with_nothing_changed_tells_the_view_nothing(self):
        self.view.told.clear()
        self.window.tick()
        self.assertEqual(self.view.told, [])

    def test_a_finished_builder_clears_the_activity_and_its_ticket_shows_finished(self):
        self.view.told.clear()
        self.write_meta(finished=True)
        self.window.tick()
        self.assertEqual(self.view.activity, {})
        snapshot = self.told("apply_changes")[-1][0]
        row = next(t for e in snapshot.efforts for t in e.tickets if t.ticket.path == self.ticket)
        self.assertEqual((row.mark, row.mark_word), ("Finished", "finished"))

    def test_a_ticket_the_progress_file_calls_landed_drops_its_activity(self):
        """Story 32: its Builder has not flagged itself finished, but the Ticket has
        stopped being built."""
        effort = self.ticket.parent.parent
        (effort / "progress.md").write_text(f"- {self.ticket.stem}: landed 1234abc\n",
                                            encoding="utf-8")
        self.window.tick()
        self.assertEqual(self.view.activity, {})

    def start_session_on(self, ticket):
        """A top-level Session (no orchestrator) whose first prompt names `ticket`."""
        session = self.orch.parent / "solo.jsonl"
        self.write_lines(session, [
            {"type": "user", "timestamp": stamp(self.clock.time - timedelta(minutes=3)),
             "message": {"role": "user", "content": f"Work {ticket}"}},
            self.tool_call("Edit", {"file_path": "G:\\repo\\hook.ps1"}, seconds_ago=5)])

    def test_a_top_level_session_shows_activity_on_a_ticket_being_built(self):
        other = next(self.ticket.parent.glob("03-*.md"))
        other.write_text(other.read_text(encoding="utf-8").replace(
            "Status: resolved", "Status: claimed"), encoding="utf-8")
        self.start_session_on(other)
        self.window.tick()
        self.assertEqual(self.view.activity.get(other), "Editing hook.ps1 · 5s")

    def test_a_top_level_session_on_a_resolved_ticket_shows_no_activity(self):
        other = next(self.ticket.parent.glob("03-*.md"))   # Status: resolved
        self.start_session_on(other)
        self.window.tick()
        self.assertNotIn(other, self.view.activity)

    def test_a_builder_quiet_for_longer_than_the_window_drops_its_activity(self):
        self.clock.time += timedelta(minutes=31)
        self.window.tick()
        self.assertEqual(self.view.activity, {})

    # ---------- clicking Activity (09) ----------
    def sessions_view(self):
        return self.controller.sessions.view

    def selected_title(self):
        view = self.sessions_view()
        return view.rows[view.selected][0] if view.selected is not None else None

    def test_clicking_a_rows_activity_fronts_the_sessions_tab_with_its_builder_selected(self):
        self.controller.front_tab().view.on_activity(self.ticket)
        self.assertIs(self.window.fronted, self.sessions_view())
        self.assertEqual(self.window.tabs, (["repo", "Sessions"], 1))
        self.assertEqual(self.selected_title(), "└ Build ticket 02 warnings")

    def test_clicking_activity_with_the_sessions_tab_open_behind_brings_it_forward(self):
        self.controller.open_sessions()
        self.controller.front(0)
        self.assertIsNone(self.sessions_view().selected)
        self.controller.front_tab().view.on_activity(self.ticket)
        self.assertIs(self.window.fronted, self.sessions_view())
        self.assertEqual(self.selected_title(), "└ Build ticket 02 warnings")

    def test_the_selection_stays_on_the_builders_row_as_the_sessions_tab_polls(self):
        self.controller.front_tab().view.on_activity(self.ticket)
        self.clock.time += timedelta(seconds=5)
        self.window.tick()
        self.assertEqual(self.selected_title(), "└ Build ticket 02 warnings")

    def test_clicking_a_row_with_no_activity_does_nothing(self):
        other = next(self.ticket.parent.glob("03-*.md"))
        self.controller.front_tab().view.on_activity(other)
        self.assertIsNone(self.sessions_view())
        self.assertIs(self.window.fronted, self.view)

    # ---------- Builders with no Ticket, in the Effort's header (09) ----------
    def start_loose_builder(self, finished=False):
        """A subagent fixing a code review's findings: it names no Ticket."""
        meta = {"description": "Fix the code review's findings"}
        if finished:
            meta["finished"] = True
        path = self.subagents / "agent-fix.meta.json"
        path.write_text(json.dumps(meta), encoding="utf-8")
        self.touch(path)
        transcript = self.subagents / "agent-fix.jsonl"
        if not transcript.exists():
            self.write_lines(transcript, [
                {"type": "user", "timestamp": stamp(self.clock.time - timedelta(minutes=2)),
                 "message": {"role": "user", "content": "Fix the code review's findings."}},
                self.tool_call("Bash", {"command": "git diff"}, seconds_ago=3)])
        return transcript

    def test_a_builder_with_no_ticket_shows_in_the_efforts_header_not_as_a_row(self):
        transcript = self.start_loose_builder()
        self.window.tick()
        effort = self.ticket.parent.parent
        self.assertEqual(self.view.builders,
                         {effort: ((transcript, "Fix the code review's findings · Running git · 3s"),)})
        self.assertEqual(self.view.activity, {self.ticket: "Editing shell.gd · 4s"})

    def test_clicking_a_header_builder_fronts_the_sessions_tab_with_its_session_selected(self):
        transcript = self.start_loose_builder()
        self.window.tick()
        self.view.on_builder(transcript)
        self.assertIs(self.window.fronted, self.sessions_view())
        self.assertEqual(self.selected_title(), "└ Fix the code review's findings")

    def test_a_header_builder_that_finishes_leaves_the_header(self):
        self.start_loose_builder()
        self.window.tick()
        self.start_loose_builder(finished=True)
        self.window.tick()
        self.assertEqual(self.view.builders, {})

    def test_a_theme_switch_keeps_the_view_and_its_activity(self):
        self.view.told.clear()
        self.controller.set_palette("paper")
        view = self.controller.front_tab().view
        self.assertIs(view, self.view)
        self.assertEqual(view.told, [])
        self.assertEqual(view.activity, {self.ticket: "Editing shell.gd · 4s"})


class StalledTest(ActivityControlsTest):
    """Stalled (08): a Builder whose transcript's last timestamped line is over 2 minutes
    old, while it is not finished. Its last line here is the tool call, 4s before setUp's
    clock. (Inherits ActivityControlsTest's setUp; its tests are not run twice, below.)"""

    def stalled(self):
        return self.view.stalled

    def test_a_last_line_2_minutes_and_1_second_old_is_stalled(self):
        self.clock.time += timedelta(seconds=121 - 4)
        self.window.tick()
        self.assertEqual(self.stalled(), {self.ticket})

    def test_a_last_line_1_minute_59_seconds_old_is_not_stalled(self):
        self.clock.time += timedelta(seconds=119 - 4)
        self.window.tick()
        self.assertEqual(self.stalled(), set())

    def test_a_finished_builder_is_never_stalled(self):
        self.write_meta(finished=True)
        self.clock.time += timedelta(minutes=10)
        self.window.tick()
        self.assertEqual(self.stalled(), set())

    def test_a_new_line_ends_stalled(self):
        self.clock.time += timedelta(minutes=5)
        self.window.tick()
        self.append(self.tool_call("Read", {"file_path": "G:\\repo\\cart.gd"}, seconds_ago=1))
        self.window.tick()
        self.assertEqual(self.stalled(), set())
        self.assertEqual(self.view.activity, {self.ticket: "Reading cart.gd · 1s"})

    def test_a_stalled_ticket_keeps_its_family_and_its_place_in_the_counts(self):
        before = self.controller.front_tab().snapshot
        self.view.told.clear()
        self.clock.time += timedelta(minutes=5)
        self.window.tick()
        self.assertEqual(self.stalled(), {self.ticket})
        self.assertEqual(self.told("apply_changes"), [])
        after = self.controller.front_tab().snapshot
        row = next(t for e in after.efforts for t in e.tickets if t.ticket.path == self.ticket)
        was = next(t for e in before.efforts for t in e.tickets if t.ticket.path == self.ticket)
        self.assertEqual((row.mark, row.ticket.family), (was.mark, was.ticket.family))
        self.assertEqual([e.counts for e in after.efforts], [e.counts for e in before.efforts])

    def test_a_rebuilt_view_shows_stalled_at_once(self):
        self.clock.time += timedelta(minutes=5)
        self.window.tick()
        self.controller.set_palette("paper")
        self.assertEqual(self.controller.front_tab().view.stalled, {self.ticket})


class LastMessageTest(ActivityControlsTest):
    """The detail pane of a Ticket being built carries its Builder's last message (08)."""

    def say(self, text, seconds_ago=1):
        self.append({"type": "assistant",
                     "timestamp": stamp(self.clock.time - timedelta(seconds=seconds_ago)),
                     "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})

    def detail_of(self, path):
        self.controller.select_file(self.controller.front_tab(), path)
        return self.told("show_detail")[-1][0]

    def test_the_detail_of_a_ticket_being_built_carries_its_builders_last_message(self):
        self.say("The cart total was off by one; fixing the loop.")
        self.window.tick()
        self.assertEqual(self.detail_of(self.ticket).last_message,
                         "The cart total was off by one; fixing the loop.")

    def test_the_detail_of_a_ticket_not_being_built_carries_none(self):
        self.say("Working on 02.")
        self.window.tick()
        other = next(p for p in self.ticket.parent.glob("*.md") if p != self.ticket)
        self.assertIsNone(self.detail_of(other).last_message)

    def test_a_finished_builders_ticket_is_not_being_built_and_carries_none(self):
        self.say("Done, handing back.")
        self.write_meta(finished=True)
        self.window.tick()
        self.assertIsNone(self.detail_of(self.ticket).last_message)

    def test_a_new_message_reaches_the_open_detail_on_the_next_poll(self):
        self.detail_of(self.ticket)
        self.say("Now the tests.")
        self.window.tick()
        self.assertEqual(self.told("show_detail")[-1][0].last_message, "Now the tests.")

    def test_a_new_message_reaches_the_open_detail_without_reading_the_ticket_again(self):
        """Story 9: the poll reads no Ticket file on the UI thread."""
        self.detail_of(self.ticket)
        self.say("Now the tests.")
        with mock.patch("src.controller.read_detail", wraps=read_detail) as read:
            self.window.tick()
        self.assertEqual(read.call_count, 0)
        detail = self.told("show_detail")[-1][0]
        self.assertEqual((detail.path, detail.last_message), (self.ticket, "Now the tests."))

    def test_a_poll_with_no_new_message_does_not_show_the_detail_again(self):
        self.say("Now the tests.")
        self.window.tick()
        self.detail_of(self.ticket)
        self.view.told.clear()
        self.window.tick()
        self.assertEqual(self.told("show_detail"), [])


# The subclasses' inherited tests are ActivityControlsTest's: run them once, there.
for _cls in (StalledTest, LastMessageTest):
    for _name in [n for n in dir(ActivityControlsTest) if n.startswith("test_")]:
        if _name not in _cls.__dict__:
            setattr(_cls, _name, None)


if __name__ == "__main__":
    unittest.main()
