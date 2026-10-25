"""The background runner: work runs on its one worker thread, and each result comes back
through the toolkit's timer, so `done` runs on the thread that pumps the timer (the UI
thread), never on the worker."""

import contextlib
import io
import threading
import time
import unittest

from src.runner import BackgroundRunner, SameThreadRunner


class FakeTimer:
    """The toolkit's `after`: callbacks run only when the test pumps."""

    def __init__(self):
        self.pending = []

    def after(self, ms, fn):
        self.pending.append(fn)
        return fn

    def pump(self):
        pending, self.pending = self.pending, []
        for fn in pending:
            fn()


class BackgroundRunnerTest(unittest.TestCase):
    def setUp(self):
        self.timer = FakeTimer()
        self.runner = BackgroundRunner(self.timer.after)
        self.addCleanup(self.runner.stop)

    def pump_until(self, condition, seconds=5):
        end = time.monotonic() + seconds
        while not condition() and time.monotonic() < end:
            self.timer.pump()
            time.sleep(0.005)
        self.assertTrue(condition(), "the result never came back")

    def test_work_runs_on_a_worker_and_done_on_the_pumping_thread(self):
        seen = {}
        here = threading.get_ident()

        def work():
            seen["work"] = threading.get_ident()
            return 42

        def done(result):
            seen["done"], seen["result"] = threading.get_ident(), result
        self.runner.submit(work, done)
        self.pump_until(lambda: "done" in seen)
        self.assertNotEqual(seen["work"], here)
        self.assertEqual(seen["done"], here)
        self.assertEqual(seen["result"], 42)

    def test_done_waits_for_the_timer(self):
        finished = threading.Event()
        results = []
        self.runner.submit(lambda: finished.set() or "x", results.append)
        self.assertTrue(finished.wait(5))
        time.sleep(0.05)
        self.assertEqual(results, [])     # nothing until the UI thread pumps
        self.pump_until(lambda: results)
        self.assertEqual(results, ["x"])

    def test_results_come_back_in_the_order_submitted(self):
        results = []
        for n in range(5):
            self.runner.submit(lambda n=n: (time.sleep(0.01), n)[1], results.append)
        self.pump_until(lambda: len(results) == 5)
        self.assertEqual(results, [0, 1, 2, 3, 4])

    def test_one_worker_thread_runs_every_job(self):
        threads = set()
        results = []
        for _ in range(4):
            self.runner.submit(lambda: threads.add(threading.get_ident()), results.append)
        self.pump_until(lambda: len(results) == 4)
        self.assertEqual(len(threads), 1)

    def test_always_runs_on_the_pumping_thread_before_done(self):
        calls = []
        here = threading.get_ident()
        self.runner.submit(lambda: 7, lambda r: calls.append(("done", r)),
                           always=lambda: calls.append(("always", threading.get_ident())))
        self.pump_until(lambda: len(calls) == 2)
        self.assertEqual(calls, [("always", here), ("done", 7)])

    def test_work_that_raises_runs_always_then_failed_on_the_pumping_thread(self):
        calls = []
        here = threading.get_ident()

        def work():
            raise ValueError("unreadable")
        self.runner.submit(work, lambda r: calls.append("done"),
                           always=lambda: calls.append("always"),
                           failed=lambda err: calls.append((type(err), threading.get_ident())))
        self.pump_until(lambda: len(calls) == 2)   # pumping raised nothing
        self.assertEqual(calls, ["always", (ValueError, here)])

    def test_an_error_in_work_does_not_raise_out_of_the_timer_callback(self):
        results = []

        def work():
            raise ValueError("unreadable")
        self.runner.submit(work, results.append)   # no `failed`: reported, not raised
        self.runner.submit(lambda: "next", results.append)
        with contextlib.redirect_stderr(io.StringIO()) as report:
            self.pump_until(lambda: results)
        self.assertEqual(results, ["next"])
        self.assertIn("ValueError: unreadable", report.getvalue())

    def test_an_error_in_done_goes_to_failed_and_the_next_result_still_lands(self):
        calls = []

        def done(result):
            raise KeyError("draw")
        self.runner.submit(lambda: 1, done, failed=lambda err: calls.append(type(err)))
        self.runner.submit(lambda: 2, calls.append)
        self.pump_until(lambda: len(calls) == 2)
        self.assertEqual(calls, [KeyError, 2])


class SameThreadRunnerTest(unittest.TestCase):
    def test_always_runs_before_done(self):
        calls = []
        SameThreadRunner().submit(lambda: 3, lambda r: calls.append(("done", r)),
                                  always=lambda: calls.append("always"))
        self.assertEqual(calls, ["always", ("done", 3)])

    def test_work_that_raises_runs_always_and_raises(self):
        calls = []

        def work():
            raise ValueError("unreadable")
        with self.assertRaises(ValueError):
            SameThreadRunner().submit(work, lambda r: calls.append("done"),
                                      always=lambda: calls.append("always"))
        self.assertEqual(calls, ["always"])

    def test_work_that_raises_runs_always_then_failed(self):
        calls = []

        def work():
            raise ValueError("unreadable")
        SameThreadRunner().submit(work, lambda r: calls.append("done"),
                                  always=lambda: calls.append("always"),
                                  failed=lambda err: calls.append(type(err)))
        self.assertEqual(calls, ["always", ValueError])


if __name__ == "__main__":
    unittest.main()
