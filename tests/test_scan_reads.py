"""A scan reads only the header lines it needs: no file is read past its first `##` heading,
so Ticket bodies are read only when the detail pane asks for one."""

import builtins
import io
import unittest
from pathlib import Path
from unittest import mock

from src.model.effort import scan
from tests import FIXTURES


def header_length(path):
    """Bytes up to and including the first line that starts with `##` (the whole file if none)."""
    data = Path(path).read_bytes()
    offset = 0
    for line in data.splitlines(keepends=True):
        offset += len(line)
        if line.startswith(b"##"):
            return offset
    return len(data)


class _Spy:
    """A file object that counts the bytes it hands out."""

    def __init__(self, inner, delivered, key):
        self._inner, self._delivered, self._key = inner, delivered, key

    def _count(self, data):
        if data:
            size = len(data.encode("utf-8")) if isinstance(data, str) else len(data)
            self._delivered[self._key] = self._delivered.get(self._key, 0) + size
        return data

    def read(self, *args):
        return self._count(self._inner.read(*args))

    def readline(self, *args):
        return self._count(self._inner.readline(*args))

    def readlines(self, *args):
        lines = self._inner.readlines(*args)
        for line in lines:
            self._count(line)
        return lines

    def readinto(self, buffer):
        n = self._inner.readinto(buffer)
        self._delivered[self._key] = self._delivered.get(self._key, 0) + (n or 0)
        return n

    def __iter__(self):
        return self

    def __next__(self):
        line = self._inner.readline()
        if not line:
            raise StopIteration
        return self._count(line)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


class SpyingScan:
    def scan_and_count(self, folder, previous=None):
        delivered = {}
        real_open = io.open

        def spying_open(file, *args, **kwargs):
            inner = real_open(file, *args, **kwargs)
            if isinstance(file, (str, Path)) and str(file).endswith(".md"):
                return _Spy(inner, delivered, Path(file).resolve())
            return inner

        def spying_path_open(self, mode="r", *args, **kwargs):
            return spying_open(self, mode, *args, **kwargs)

        # Every route a file is opened by in Python: open(), io.open() and Path.open()
        # (which Path.read_text and Path.read_bytes use).
        with mock.patch.object(io, "open", spying_open), \
                mock.patch.object(builtins, "open", spying_open), \
                mock.patch.object(Path, "open", spying_path_open):
            self.scanned = scan(folder, previous) if previous else scan(folder)
        return delivered


class ScanReadsOnlyHeadersTest(SpyingScan, unittest.TestCase):
    def check(self, folder):
        delivered = self.scan_and_count(folder)
        self.assertTrue(delivered, "the scan read no files at all")
        for path, size in delivered.items():
            if path.name == "progress.md":
                continue   # the Progress file is read whole, by design (fast-live-board 05)
            with self.subTest(path=path.name):
                self.assertLessEqual(size, header_length(path))

    def test_a_wayfinder_effort_is_scanned_from_headers_only(self):
        self.check(FIXTURES / "field-guide-rebuild")

    def test_a_build_effort_is_scanned_from_headers_only(self):
        self.check(FIXTURES / "retro-2026-10-19")

    def test_a_body_after_the_header_is_never_read(self):
        """A ticket whose body is not even text still scans: the scan stops at `##`."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "effort"
            (folder / "issues").mkdir(parents=True)
            (folder / "spec.md").write_bytes(b"# S\nStatus: open\n")
            (folder / "issues" / "01-a.md").write_bytes(
                b"# 01: A\nStatus: ready-for-agent\nBlocked by: none\n\n## What to build\n"
                + b"\xff\xfe not text \xe9\n" * 5000)
            ticket = scan(folder).efforts[0].tickets[0].ticket
            self.assertTrue(ticket.parsed)
            self.assertEqual(ticket.status, "ready-for-agent")
            self.check(folder)


class RescanSkipsUnchangedTicketsTest(SpyingScan, unittest.TestCase):
    """A rescan given the last Snapshot re-reads only the Ticket files whose modification
    time changed since it; the rest come from that Snapshot."""

    def test_an_unchanged_ticket_is_not_read_again_and_a_changed_one_is(self):
        import os
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "retro"
            shutil.copytree(FIXTURES / "retro-2026-10-19", folder)
            first = scan(folder)
            changed = next((folder / "issues").glob("02-*.md"))
            unchanged = next((folder / "issues").glob("03-*.md"))
            text = changed.read_text(encoding="utf-8")
            status = next(line for line in text.splitlines() if line.startswith("Status:"))
            changed.write_text(text.replace(status, "Status: claimed"), encoding="utf-8")
            later = changed.stat().st_mtime + 5
            os.utime(changed, (later, later))

            delivered = self.scan_and_count(folder, first)
            read = {path.name for path in delivered}
            self.assertIn(changed.name, read)
            self.assertNotIn(unchanged.name, read)
            tickets = {t.ticket.path.name: t.ticket for t in self.scanned.efforts[0].tickets}
            self.assertEqual(tickets[changed.name].status, "claimed")
            self.assertEqual(tickets[unchanged.name].status, "resolved")
            # The Progress file says 02 landed, which is further along than claimed.
            self.assertEqual(self.scanned.efforts[0].counts["Done"], 7)

    def test_an_unchanged_progress_file_is_not_read_again_and_a_changed_one_is(self):
        import os
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "marks"
            shutil.copytree(FIXTURES / "progress-marks", folder)
            progress = folder / "progress.md"
            first = scan(folder)
            delivered = self.scan_and_count(folder, first)
            self.assertNotIn("progress.md", {path.name for path in delivered})

            text = progress.read_text(encoding="utf-8")
            progress.write_text(text.replace("- 03-running: running", "- 03-running: finished"),
                                encoding="utf-8")
            later = progress.stat().st_mtime + 5
            os.utime(progress, (later, later))
            delivered = self.scan_and_count(folder, self.scanned)
            self.assertIn("progress.md", {path.name for path in delivered})
            self.assertEqual(self.scanned.efforts[0].counts["Finished"], 3)


if __name__ == "__main__":
    unittest.main()
