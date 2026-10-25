import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.model.sessions import scan_sessions
from tests import FIXTURES

PROJECTS = FIXTURES / "sessions"
NOW = datetime(2026, 10, 21, 9, 15, tzinfo=timezone.utc)
WINDOW = timedelta(minutes=30)

ALPHA = PROJECTS / "G--proj-alpha" / "aaaa1111.jsonl"
BETA = PROJECTS / "G--proj-beta" / "bbbb2222.jsonl"
OLD = PROJECTS / "G--proj-old" / "cccc3333.jsonl"
BROKEN = PROJECTS / "G--proj-broken" / "dddd4444.jsonl"
SUBAGENT = PROJECTS / "G--proj-alpha" / "aaaa1111" / "subagents" / "agent-x.jsonl"


def set_mtime(path, when):
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def write_big_transcript(path):
    """A 50 MB transcript: title and Ticket prompt at the head, a newer title and the
    last message at the tail, plain assistant lines between. Built at test time, never committed."""
    def line(record):
        return (json.dumps(record) + "\n").encode("utf-8")

    filler = line({"type": "assistant", "timestamp": "2026-10-21T08:00:00Z", "cwd": "G:\\proj\\big",
                   "message": {"role": "assistant", "model": "claude-early",
                               "content": [{"type": "text", "text": "x" * 300}]}})
    path.parent.mkdir(parents=True)
    with open(path, "wb") as out:
        out.write(line({"type": "custom-title", "customTitle": "Early title"}))
        out.write(line({"type": "user", "timestamp": "2026-10-21T08:00:00Z", "cwd": "G:\\proj\\big",
                        "message": {"role": "user", "content": "/implement G:\\x\\.scratch\\e\\issues\\03-big.md"}}))
        out.write(filler * (50 * 1024 * 1024 // len(filler) + 1))
        out.write(line({"type": "custom-title", "customTitle": "Late title"}))
        out.write(line({"type": "assistant", "timestamp": "2026-10-21T09:14:00Z", "cwd": "G:\\proj\\big",
                        "message": {"role": "assistant", "model": "claude-late", "content": []}}))
    assert path.stat().st_size >= 50 * 1024 * 1024
    set_mtime(path, NOW)
    return path


class ScanOpensOnlyWhatItMustTest(unittest.TestCase):
    """A scan opens no transcript outside the window, and a rescan given the last scan's
    Sessions opens only the transcripts modified since."""

    def setUp(self):
        set_mtime(ALPHA, NOW - timedelta(minutes=2))
        set_mtime(BROKEN, NOW - timedelta(minutes=10))
        set_mtime(BETA, NOW - timedelta(minutes=20))
        set_mtime(OLD, NOW - timedelta(hours=2))
        set_mtime(SUBAGENT, NOW - timedelta(minutes=1))

    def scan_and_list_opened(self, *args):
        import builtins
        from unittest import mock
        opened, real_open = [], builtins.open

        def spying_open(file, *a, **k):
            opened.append(Path(file))
            return real_open(file, *a, **k)
        with mock.patch.object(builtins, "open", spying_open):
            sessions = scan_sessions(PROJECTS, NOW, WINDOW, *args)
        return sessions, opened

    def test_a_transcript_in_a_project_untouched_within_the_window_is_never_opened(self):
        sessions, opened = self.scan_and_list_opened()
        self.assertNotIn(OLD, opened)
        self.assertEqual(sorted(opened), sorted([ALPHA, BROKEN, BETA]))
        self.assertEqual([s.path for s in sessions], [ALPHA, BROKEN, BETA])

    def test_a_rescan_opens_only_the_transcripts_modified_since_the_last(self):
        first, _ = self.scan_and_list_opened()
        set_mtime(BETA, NOW - timedelta(minutes=1))
        again, opened = self.scan_and_list_opened(first)
        self.assertEqual(opened, [BETA])
        self.assertEqual([s.path for s in again], [BETA, ALPHA, BROKEN])
        self.assertEqual(again[0].modified, NOW - timedelta(minutes=1))
        self.assertEqual(again[1:], first[:2])


class ScanSessionsTest(unittest.TestCase):
    def setUp(self):
        set_mtime(ALPHA, NOW - timedelta(minutes=2))
        set_mtime(BROKEN, NOW - timedelta(minutes=10))
        set_mtime(BETA, NOW - timedelta(minutes=20))
        set_mtime(OLD, NOW - timedelta(hours=2))
        set_mtime(SUBAGENT, NOW - timedelta(minutes=1))

    def scan(self):
        return scan_sessions(PROJECTS, NOW, WINDOW)

    def by_folder(self, name):
        return next(s for s in self.scan() if s.path.parent.name == name)

    def test_recent_transcripts_come_back_newest_first(self):
        paths = [s.path for s in self.scan()]
        self.assertEqual(paths, [ALPHA, BROKEN, BETA])

    def test_fields_come_from_the_last_matching_lines(self):
        alpha = self.by_folder("G--proj-alpha")
        self.assertEqual(alpha.title, "Alpha: wayfinder 07")
        self.assertEqual(alpha.project, "alpha")
        self.assertEqual(alpha.last_message_at, datetime(2026, 10, 21, 9, 12, 30, tzinfo=timezone.utc))
        self.assertEqual(alpha.sender, "assistant")
        self.assertEqual(alpha.model, "claude-sonnet-4-5")

    def test_model_comes_from_last_assistant_even_when_user_spoke_last(self):
        beta = self.by_folder("G--proj-beta")
        self.assertEqual(beta.title, "Beta chores")
        self.assertEqual(beta.project, "beta")
        self.assertEqual(beta.last_message_at, datetime(2026, 10, 21, 8, 55, tzinfo=timezone.utc))
        self.assertEqual(beta.sender, "user")
        self.assertEqual(beta.model, "claude-haiku-4-5")

    def test_malformed_transcript_is_titled_by_its_folder_with_unknown_fields(self):
        broken = self.by_folder("G--proj-broken")
        self.assertEqual(broken.title, "G--proj-broken")
        self.assertIsNone(broken.project)
        self.assertIsNone(broken.last_message_at)
        self.assertIsNone(broken.sender)
        self.assertIsNone(broken.model)
        self.assertIsNone(broken.ticket)

    def test_first_prompt_naming_a_ticket_path_matches_it(self):
        alpha = self.by_folder("G--proj-alpha")
        self.assertEqual(alpha.ticket, Path(r"G:\x\.scratch\e\issues\07-foo.md"))

    def test_first_prompt_with_no_path_matches_nothing(self):
        self.assertIsNone(self.by_folder("G--proj-beta").ticket)

    def test_prompts_naming_a_map_or_a_spaced_path_match(self):
        cases = {
            "/wayfinder G:\\x\\.scratch\\e\\map.md": Path(r"G:\x\.scratch\e\map.md"),
            "/implement G:\\my projects\\board app\\.scratch\\wb\\issues\\09-scan-sessions.md please":
                Path(r"G:\my projects\board app\.scratch\wb\issues\09-scan-sessions.md"),
            "see /home/dev/r/.scratch/e/issues/12-bar.md": Path("/home/dev/r/.scratch/e/issues/12-bar.md"),
            "<command-args>G:\\x\\.scratch\\e\\map.md\\</command-args>": Path(r"G:\x\.scratch\e\map.md"),
            "/to-tickets G:\\x\\.scratch\\e\\spec.md": None,
        }
        for prompt, expected in cases.items():
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "G--case"
                folder.mkdir()
                path = folder / "ffff.jsonl"
                line = {"type": "user", "timestamp": "2026-10-21T09:00:00Z", "message": {"role": "user", "content": prompt}}
                path.write_text(json.dumps(line) + "\n", encoding="utf-8")
                set_mtime(path, NOW)
                [session] = scan_sessions(tmp, NOW, WINDOW)
                self.assertEqual(session.ticket, expected)

    def test_a_50_mb_transcript_scans_in_under_a_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_big_transcript(Path(tmp) / "G--proj-big" / "big.jsonl")
            start = time.perf_counter()
            [session] = scan_sessions(tmp, NOW, WINDOW)
            elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0)
        self.assertEqual(session.title, "Late title")
        self.assertEqual(session.project, "big")
        self.assertEqual(session.model, "claude-late")
        self.assertEqual(session.last_message_at, datetime(2026, 10, 21, 9, 14, tzinfo=timezone.utc))
        self.assertEqual(session.ticket, Path(r"G:\x\.scratch\e\issues\03-big.md"))

    def test_ten_long_sessions_scan_in_under_a_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = write_big_transcript(Path(tmp) / "G--proj-big0" / "big.jsonl")
            for n in range(1, 10):
                folder = Path(tmp) / f"G--proj-big{n}"
                folder.mkdir()
                os.link(big, folder / "big.jsonl")
            start = time.perf_counter()
            sessions = scan_sessions(tmp, NOW, WINDOW)
            elapsed = time.perf_counter() - start
        self.assertEqual(len(sessions), 10)
        self.assertEqual({s.title for s in sessions}, {"Late title"})
        self.assertLess(elapsed, 1.0)

    def test_project_is_the_launch_folder_even_after_a_cd(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "G--proj-gamma"
            folder.mkdir()
            path = folder / "gggg.jsonl"
            lines = [
                {"type": "user", "timestamp": "2026-10-21T09:00:00Z", "cwd": "G:\\proj\\gamma",
                 "message": {"role": "user", "content": "go"}},
                {"type": "assistant", "timestamp": "2026-10-21T09:01:00Z", "cwd": "G:\\proj\\gamma\\.scratch\\issues",
                 "message": {"role": "assistant", "model": "m", "content": []}},
            ]
            path.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
            set_mtime(path, NOW)
            [session] = scan_sessions(tmp, NOW, WINDOW)
        self.assertEqual(session.project, "gamma")

    def test_missing_projects_dir_gives_no_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(scan_sessions(Path(tmp) / "nope", NOW, WINDOW), [])

    def test_module_imports_no_gui(self):
        import subprocess
        import sys
        probe = "import sys, src.model.sessions; print('tkinter' in sys.modules or 'customtkinter' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                             cwd=Path(__file__).parent.parent, check=True).stdout.strip()
        self.assertEqual(out, "False")

    def test_unreadable_bytes_do_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "G--binary"
            folder.mkdir()
            path = folder / "eeee.jsonl"
            path.write_bytes(b"\xff\xfe\x00garbage\r\n\x80\x81{\r\n")
            set_mtime(path, NOW)
            [session] = scan_sessions(tmp, NOW, WINDOW)
        self.assertEqual(session.title, "G--binary")
        self.assertIsNone(session.sender)


if __name__ == "__main__":
    unittest.main()
