"""Runners: where the controller's scans run. Imports no GUI toolkit.

    runner.submit(work, done)    # work() runs off the UI thread, done(result) back on it
    runner.submit(work, done, always=clear_flag)   # always() first, even if work raised
    runner.submit(work, done, failed=show_error)   # failed(err) when work or done raised

If `work` raises, `done` does not run: `failed(err)` runs on the UI thread instead. An
error raised by `done` goes to `failed` too. `always`, when given, runs on the UI thread
as the work comes back, before `done` or `failed`, so the caller's clean-up never depends
on the work succeeding. The background runner never raises an error out of the
toolkit's timer callback: with no `failed`, the error is reported on stderr and the next
result still lands.

A runner is an adapter passed to the controller, like the window's timer.
`BackgroundRunner` is the app's: one worker thread, results handed back through the
toolkit's timer, so no widget is ever touched off the UI thread. `SameThreadRunner`
runs the work at once, on the caller's thread: the controller's default, for tests and
scripts. Both hand a result back the one way, `Job.hand_back`.
"""


import queue
import sys
import threading
import traceback
from dataclasses import dataclass

CHECK_MS = 5   # how often the UI thread looks for finished work while some is out


def report(err):
    """The fallback for an error with no `failed`: its traceback, on stderr."""
    traceback.print_exception(type(err), err, err.__traceback__, file=sys.stderr)


@dataclass(frozen=True)
class Job:
    """One piece of work handed to a runner, with what runs when it comes back."""
    work: object
    done: object
    always: object = None
    failed: object = None

    def hand_back(self, result, error, unhandled=report):
        """On the UI thread: always(), then done(result), or failed(error) when the work
        or done raised. With no `failed`, the error goes to `unhandled`, or is raised when
        that is None. An error in `always` or `failed` itself is reported, not raised."""
        try:
            if self.always is not None:
                self.always()
            if error is None:
                self.done(result)
                return
        except Exception as err:
            error = err
        if self.failed is None and unhandled is None:
            raise error
        try:
            (self.failed or unhandled)(error)
        except Exception as err:
            report(err)


class BackgroundRunner:
    """One worker thread runs each `work()` in the order submitted. Its result waits in a
    queue until the UI thread, woken by the toolkit's timer `after(ms, fn)`, hands it to
    `done`. The timer runs only while work is out, so an idle app does nothing.

    Call `submit` from the UI thread only. If `work` or `done` raises, the error goes to
    `failed` on the UI thread (else to stderr), never out of the timer callback; `always`
    runs either way."""

    def __init__(self, after, check_ms=CHECK_MS):
        self._after, self._check_ms = after, check_ms
        self._jobs, self._results = queue.Queue(), queue.Queue()
        self._out = 0            # submitted, not yet handed to done (UI thread only)
        self._checking = False
        self._worker = None

    def submit(self, work, done, always=None, failed=None):
        if self._worker is None:
            self._worker = threading.Thread(target=self._work, name="board-scan", daemon=True)
            self._worker.start()
        self._out += 1
        self._jobs.put(Job(work, done, always, failed))
        if not self._checking:
            self._checking = True
            self._after(self._check_ms, self._check)

    def stop(self):
        """End the worker thread once it finishes what it holds (it is a daemon anyway)."""
        if self._worker is not None:
            self._jobs.put(None)
            self._worker = None

    def _work(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._results.put((job, job.work(), None))
            except BaseException as err:   # handed to the UI thread, given to `failed` there
                self._results.put((job, None, err))

    def _check(self):
        """On the UI thread: hand every finished result to its `done`, or its error to
        its `failed`."""
        self._checking = False
        try:
            while True:
                try:
                    job, result, error = self._results.get_nowait()
                except queue.Empty:
                    break
                self._out -= 1
                job.hand_back(result, error)
        finally:
            if self._out and not self._checking:
                self._checking = True
                self._after(self._check_ms, self._check)


class SameThreadRunner:
    """Runs `work()` now and hands its result straight to `done`. With no `failed`, an
    error in `work` or `done` is raised to the caller, as tests and scripts want."""

    def submit(self, work, done, always=None, failed=None):
        job = Job(work, done, always, failed)
        try:
            result, error = work(), None
        except Exception as err:
            result, error = None, err
        job.hand_back(result, error, unhandled=None)
