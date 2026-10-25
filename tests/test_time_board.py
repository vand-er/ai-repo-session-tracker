"""The timing harness's queue, load marks, `--only` and exit line, through its public
functions, with a fake clock and fake load. No test here opens a window or times anything
for real."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools import time_board


class FakeTime:
    """A monotonic clock that only moves when the harness sleeps."""

    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def dead_pid():
    """The pid of a process that has exited."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


class LockTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.lock = Path(self.dir.name) / "timing.lock"

    def test_a_live_run_holding_the_lock_is_waited_for_then_given_up_on_after_30_minutes(self):
        live = os.getpid()
        self.lock.write_text(str(live), encoding="utf-8")
        fake, said = FakeTime(), []
        with self.assertRaises(time_board.LockTimeout):
            time_board.acquire_lock(self.lock, pid=live + 1, clock=fake.clock, sleep=fake.sleep,
                                    out=said.append)
        self.assertEqual(said[0], f"waiting for run {live}")
        self.assertGreaterEqual(fake.now, 30 * 60)
        self.assertLess(fake.now, 31 * 60)
        self.assertEqual(self.lock.read_text(encoding="utf-8").strip(), str(live))

    def test_a_lock_naming_a_dead_pid_is_taken_over_without_waiting(self):
        self.lock.write_text(str(dead_pid()), encoding="utf-8")
        fake, said = FakeTime(), []
        time_board.acquire_lock(self.lock, pid=4242, clock=fake.clock, sleep=fake.sleep,
                                out=said.append)
        self.assertEqual(self.lock.read_text(encoding="utf-8").strip(), "4242")
        self.assertEqual((said, fake.now), ([], 0.0))

    def test_a_lock_whose_pid_is_not_written_yet_is_waited_for_not_deleted(self):
        """The race: another run has created the lock file and is writing its pid."""
        live = os.getpid()
        self.lock.write_text("", encoding="utf-8")
        fake, said = FakeTime(), []

        def sleep(seconds):   # the other run's pid lands while this one waits
            if not self.lock.read_text(encoding="utf-8"):
                self.lock.write_text(str(live), encoding="utf-8")
            fake.sleep(seconds)
        with self.assertRaises(time_board.LockTimeout):
            time_board.acquire_lock(self.lock, pid=live + 1, clock=fake.clock, sleep=sleep,
                                    out=said.append, timeout_s=60)
        self.assertEqual(self.lock.read_text(encoding="utf-8").strip(), str(live))
        self.assertIn(f"waiting for run {live}", said)

    def test_a_lock_left_empty_past_the_grace_is_taken_over(self):
        self.lock.write_text("", encoding="utf-8")
        fake = FakeTime()
        time_board.acquire_lock(self.lock, pid=4242, clock=fake.clock, sleep=fake.sleep,
                                out=lambda *_a: None)
        self.assertEqual(self.lock.read_text(encoding="utf-8").strip(), "4242")
        self.assertGreaterEqual(fake.now, time_board.LOCK_EMPTY_GRACE_S)
        self.assertLess(fake.now, time_board.LOCK_TIMEOUT_S)

    def test_the_lock_file_holds_the_whole_pid_from_the_moment_it_exists(self):
        seen = []
        real_link = os.link

        def link(source, target):   # what any other run could read the instant it exists
            real_link(source, target)
            seen.append(Path(target).read_text(encoding="utf-8"))
        with mock.patch.object(time_board.os, "link", link):
            time_board.acquire_lock(self.lock, pid=4242, clock=FakeTime().clock)
        self.assertEqual(seen, ["4242"])
        self.assertEqual(sorted(p.name for p in self.lock.parent.iterdir()), [self.lock.name])


def fake_load(percents):
    """A load meter reading the next of `percents` over each row, in the order rows are timed."""
    readings = iter(percents)
    return lambda: (lambda: next(readings))


ARGS = SimpleNamespace(repeats=9, minimum=3, budget=20.0, startup_runs=5)


def table_row(table, title):
    return next(line for line in table.splitlines() if line.startswith(f"| {title} |"))


class LoadTest(unittest.TestCase):
    def test_a_row_timed_above_40_percent_load_is_written_and_marked_unreliable(self):
        recorder = time_board.Recorder(load=fake_load([55, 12]), out=lambda *a, **k: None)
        recorder.record("sort", lambda: [5.0, 6.0, 7.0])
        recorder.record("theme", lambda: [8.0, 9.0, 10.0])
        table = time_board.render("check", {"here": ("~/code/here", recorder.data())}, ARGS)
        sort, theme = table_row(table, "Sort by a column"), table_row(table, "Switch theme")
        self.assertIn("6.0 ms (n=3)", sort)
        self.assertIn("unreliable", sort)
        self.assertIn("55%", sort)
        self.assertIn("9.0 ms (n=3)", theme)
        self.assertNotIn("unreliable", theme)


class CpuMeterTest(unittest.TestCase):
    """One meter, `cpu_meter`, read from fake system and process times (100 ns units)."""

    @staticmethod
    def meter(system, own):
        systems, owns = iter(system), iter(own)
        return time_board.cpu_meter(system_times=lambda: next(systems),
                                    own_cpu_s=lambda: next(owns))

    def test_the_load_is_the_machines_busy_share_less_this_process_own_work(self):
        # 1000 units pass, 600 idle: 40% busy, of which this process's 200 units are 20%.
        since = self.meter([(0, 0), (600, 1000)], [0.0, 200e-7])
        self.assertAlmostEqual(since(), 20.0)

    def test_a_process_doing_all_the_work_leaves_no_load(self):
        since = self.meter([(0, 0), (500, 1000)], [0.0, 600e-7])
        self.assertEqual(since(), 0.0)

    def test_the_run_table_gives_the_load_over_the_whole_run_from_the_same_meter(self):
        table = time_board.render("check", {}, ARGS, load=37.4)
        self.assertIn("37%", table)
        self.assertEqual(time_board.render("check", {}, ARGS, load=None).count("could not be read"), 1)

    def test_help_says_which_readings_include_the_harness_own_work(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            time_board.main(["--help"])
        text = " ".join(out.getvalue().split())
        self.assertIn("machine-wide", text)
        self.assertIn("own work", text)


class OnlyTest(unittest.TestCase):
    def test_only_the_named_rows_are_timed_and_shown(self):
        timed = []

        def measure(key):
            return lambda: timed.append(key) or [4.0]
        recorder = time_board.Recorder(only=time_board.parse_only("sort,theme"),
                                       load=fake_load([0, 0]), out=lambda *a, **k: None)
        for key in ("row_select", "sort", "toggle_area", "theme", "scroll"):
            recorder.record(key, measure(key))
        self.assertEqual(timed, ["sort", "theme"])
        table = time_board.render("check", {"here": ("~/code/here", recorder.data())}, ARGS,
                                  only=recorder.only)
        rows = [line for line in table.splitlines() if line.startswith("| ") and "---" not in line]
        self.assertEqual([r.split(" | ")[0] for r in rows[1:]],
                         ["| Sort by a column", "| Switch theme"])

    def test_an_unknown_row_name_is_an_error(self):
        with self.assertRaises(ValueError) as caught:
            time_board.parse_only("sort,sortt")
        self.assertIn("sortt", str(caught.exception))


class ExitLineTest(unittest.TestCase):
    """The parent's run ends with one `exit=<code>` line. The child window processes are
    faked at `time_folder`, the harness's boundary to them, so nothing is timed."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.source = Path(self.dir.name) / "source"
        (self.source / ".scratch").mkdir(parents=True)
        self.lock = Path(self.dir.name) / "timing.lock"
        for name, fake in (("cpu_meter", lambda: (lambda: 5.0)),
                           ("time_folder", self.fake_time_folder)):
            patcher = mock.patch.object(time_board, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.broken = False

    def fake_time_folder(self, label, folder, poll_folder, temp, args, tag):
        if self.broken:
            raise RuntimeError("the window would not open")
        return {"results": {"sort": [5.0]}, "load": {"sort": 10.0}, "info": {}}

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = time_board.main([str(self.source), "--no-generated", *argv],
                                   lock_file=self.lock)
        return code, out.getvalue().splitlines()

    def test_a_run_that_works_ends_with_exit_0(self):
        code, lines = self.run_main("--only", "sort")
        self.assertEqual((code, lines[-1]), (0, "exit=0"))
        self.assertEqual(sum(line.startswith("exit=") for line in lines), 1)
        self.assertFalse(self.lock.exists())

    def test_a_run_that_fails_ends_with_its_non_zero_code(self):
        self.broken = True
        code, lines = self.run_main()
        self.assertNotEqual(code, 0)
        self.assertEqual(lines[-1], f"exit={code}")
        self.assertFalse(self.lock.exists())

    def test_an_unknown_row_ends_with_a_non_zero_code(self):
        code, lines = self.run_main("--only", "nope")
        self.assertNotEqual(code, 0)
        self.assertEqual(lines[-1], f"exit={code}")


class HelpTest(unittest.TestCase):
    def test_help_says_when_to_use_quick_and_when_only(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            time_board.main(["--help"])
        text = " ".join(out.getvalue().split())
        self.assertIn("Use --quick", text)
        self.assertIn("Use --only", text)
