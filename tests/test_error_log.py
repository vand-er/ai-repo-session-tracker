"""The error log on its own: it keeps the newest entries and drops the oldest past its
size limit, whole entries at a time."""

import contextlib
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.error_log import ErrorLog


def raised(message):
    try:
        raise RuntimeError(message)
    except RuntimeError as err:
        return err


class ErrorLogTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "error.log"

    def test_past_its_size_limit_the_log_drops_its_oldest_entries(self):
        log = ErrorLog(self.path, limit=1500)
        for n in range(20):
            log.write(datetime(2026, 10, 24, 9, 0, n), f"folder-{n:02}", raised(f"error {n:02}"))
        text = self.path.read_text(encoding="utf-8")
        self.assertLessEqual(len(text.encode("utf-8")), 1500)
        self.assertIn("folder-19", text)            # the newest is kept
        self.assertIn("RuntimeError: error 19", text)
        self.assertNotIn("folder-00", text)         # the oldest is dropped
        self.assertTrue(text.startswith("=== "))    # whole entries only
        kept = [n for n in range(20) if f"folder-{n:02}" in text]
        self.assertEqual(kept, list(range(kept[0], 20)))   # the newest run, unbroken

    def test_under_its_limit_every_entry_is_kept(self):
        log = ErrorLog(self.path)
        for n in range(3):
            log.write(datetime(2026, 10, 24, 9, 0, n), f"folder-{n:02}", raised("x"))
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual([f"folder-{n:02}" in text for n in range(3)], [True] * 3)

    def test_a_log_that_cannot_be_written_says_so_once_on_stderr_and_raises_nothing(self):
        self.path.mkdir()   # a folder where the file should be: every write fails
        log = ErrorLog(self.path)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            for n in range(3):
                log.write(datetime(2026, 10, 24, 9, 0, n), "folder", raised("x"))
        lines = err.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("can't write the error log", lines[0])
        self.assertIn(str(self.path), lines[0])


if __name__ == "__main__":
    unittest.main()
