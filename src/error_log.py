"""The error log: every unexpected error caught at the work boundary, written to
`error.log` beside the Workspace file. Imports no GUI toolkit.

    log = ErrorLog(workspace_file.parent / "error.log")
    log.write(when, where, err)    # time, Source folder (or other place) and traceback

Each entry starts with a header line, `=== <time>  <where>`, and holds the error's
traceback. The log stays small: past `limit` bytes, the oldest entries are dropped and the
newest kept. It is local only: nothing here sends anything anywhere. Writing never raises:
a log that cannot be written is skipped, so it never adds an error of its own, and the
first such failure is said once on stderr.
"""

import sys
import traceback
from pathlib import Path

LIMIT = 64 * 1024   # bytes kept, newest entries first
HEADER = "=== "


class ErrorLog:
    def __init__(self, path, limit=LIMIT):
        self.path, self.limit = Path(path), limit
        self._said = False   # whether a failed write has been reported on stderr

    def write(self, when, where, err):
        trace = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        entry = f"{HEADER}{when:%Y-%m-%d %H:%M:%S}  {where}\n{trace.rstrip()}\n\n"
        try:
            try:
                old = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                old = ""
            self.path.write_text(self._trimmed(old + entry), encoding="utf-8")
        except (OSError, UnicodeError) as failed:
            if not self._said:
                self._said = True
                print(f"wayfinder-board: can't write the error log {self.path}: {failed}",
                      file=sys.stderr)

    def _trimmed(self, text):
        """`text` less its oldest entries, until it fits in `limit` bytes. The newest entry
        is always kept."""
        while len(text.encode("utf-8")) > self.limit:
            cut = text.find("\n" + HEADER, 1)
            if cut < 0:
                break
            text = text[cut + 1:]
        return text
